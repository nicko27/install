# install/plugins/plugins_utils/selinux_apparmor.py
#!/usr/bin/env python3
"""
Module utilitaire pour interagir avec les systèmes de contrôle d'accès mandatoires
SELinux et AppArmor via leurs commandes système respectives.
"""

from .plugin_utils_base import PluginUtilsBase
import os
import re
from typing import Union, Optional, List, Dict, Any, Tuple

class MandatoryAccessControl(PluginUtilsBase):
    """
    Classe pour interagir avec SELinux et AppArmor.
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    MAC_SYSTEM_UNKNOWN = "unknown"
    MAC_SYSTEM_SELINUX = "selinux"
    MAC_SYSTEM_APPARMOR = "apparmor"
    MAC_SYSTEM_NONE = "none"

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire MAC."""
        super().__init__(logger, target_ip)
        self._mac_system = None # Cache pour le système détecté
        self._check_commands()

    def _check_commands(self):
        """Vérifie si les commandes nécessaires sont disponibles."""
        # Ne loggue que des avertissements si les commandes ne sont pas trouvées,
        # car un seul des deux systèmes (ou aucun) peut être présent.
        cmds = ['sestatus', 'getsebool', 'setsebool', 'restorecon', 'aa-status', 'aa-complain', 'aa-enforce']
        found_selinux = False
        found_apparmor = False
        for cmd in cmds:
            success, _, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
            if success:
                if cmd.startswith('se') or cmd == 'restorecon':
                    found_selinux = True
                elif cmd.startswith('aa-'):
                    found_apparmor = True
        if not found_selinux:
            self.log_debug("Commandes SELinux (sestatus, setsebool...) non trouvées.")
        if not found_apparmor:
            self.log_debug("Commandes AppArmor (aa-status...) non trouvées.")

    def detect_mac_system(self) -> str:
        """
        Tente de détecter quel système MAC (SELinux ou AppArmor) est actif.

        Returns:
            'selinux', 'apparmor', 'none', ou 'unknown' si la détection échoue.
        """
        if self._mac_system:
            return self._mac_system

        # 1. Vérifier SELinux via sestatus
        sestatus_success, sestatus_stdout, _ = self.run(['sestatus'], check=False, no_output=True, error_as_warning=True)
        if sestatus_success and "SELinux status:" in sestatus_stdout:
            if "enabled" in sestatus_stdout:
                 self.log_info("SELinux détecté et activé.")
                 self._mac_system = self.MAC_SYSTEM_SELINUX
                 return self._mac_system
            elif "disabled" in sestatus_stdout:
                 self.log_info("SELinux détecté mais désactivé.")
                 # Continuer pour voir si AppArmor est actif

        # 2. Vérifier AppArmor via aa-status
        aa_status_success, aa_status_stdout, _ = self.run(['aa-status'], check=False, no_output=True, error_as_warning=True, needs_sudo=True) # aa-status nécessite souvent sudo
        if aa_status_success and "apparmor module is loaded" in aa_status_stdout.lower():
             # Vérifier s'il y a des profils chargés
             if "profiles are loaded" in aa_status_stdout.lower() and "0 profiles are loaded" not in aa_status_stdout.lower():
                  self.log_info("AppArmor détecté et actif (profils chargés).")
                  self._mac_system = self.MAC_SYSTEM_APPARMOR
                  return self._mac_system
             else:
                  self.log_info("AppArmor détecté mais aucun profil chargé activement.")
                  # Considérer comme inactif s'il n'y a pas de profils ? Ou actif mais vide?
                  # On retourne AppArmor mais l'appelant devra vérifier les profils.
                  self._mac_system = self.MAC_SYSTEM_APPARMOR
                  return self._mac_system

        # 3. Si SELinux était désactivé et AppArmor non trouvé/inactif
        if sestatus_success and "disabled" in sestatus_stdout:
             self.log_info("SELinux est désactivé et AppArmor n'est pas actif.")
             self._mac_system = self.MAC_SYSTEM_NONE
             return self._mac_system

        # 4. Si aucune commande n'a fonctionné ou n'a donné d'info claire
        self.log_warning("Impossible de déterminer clairement le système MAC actif (SELinux/AppArmor).")
        self._mac_system = self.MAC_SYSTEM_UNKNOWN
        return self._mac_system

    # --- Fonctions SELinux ---

    def get_selinux_status(self) -> Optional[Dict[str, str]]:
        """
        Récupère le statut de SELinux via sestatus.

        Returns:
            Dictionnaire avec les informations (status, mode, policy, etc.) ou None si erreur.
        """
        self.log_info("Récupération du statut SELinux (sestatus)")
        success, stdout, stderr = self.run(['sestatus'], check=False, no_output=True)
        if not success:
            # Vérifier si l'erreur est due à SELinux non installé/disponible
            if "command not found" in stderr.lower() or "not enabled" in stderr.lower():
                 self.log_info("SELinux n'est pas installé ou activé sur ce système.")
                 return {'selinux_status': 'disabled'} # Retourner un statut clair
            self.log_error(f"Échec de la commande sestatus. Stderr: {stderr}")
            return None

        status_info: Dict[str, str] = {}
        # Format: Key: Value
        for line in stdout.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                key_norm = key.strip().lower().replace(' ', '_').replace('/', '_')
                status_info[key_norm] = value.strip()

        self.log_debug(f"Statut SELinux: {status_info}")
        return status_info

    def set_selinux_mode_runtime(self, enforcing: bool) -> bool:
        """
        Change le mode SELinux (Enforcing/Permissive) pour la session courante.
        Nécessite root. Ne persiste pas après redémarrage.

        Args:
            enforcing: True pour passer en mode Enforcing, False pour Permissive.

        Returns:
            bool: True si succès.
        """
        mode_int = 1 if enforcing else 0
        mode_str = "Enforcing" if enforcing else "Permissive"
        self.log_info(f"Changement du mode SELinux (runtime) en: {mode_str}")
        cmd = ['setenforce', str(mode_int)]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            self.log_success(f"Mode SELinux (runtime) changé en {mode_str}.")
            return True
        else:
            self.log_error(f"Échec du changement de mode SELinux (runtime). Stderr: {stderr}")
            return False

    def set_selinux_mode_persistent(self, mode: str) -> bool:
        """
        Change le mode SELinux de manière persistante dans /etc/selinux/config.
        Nécessite root et un redémarrage pour être effectif.

        Args:
            mode: 'enforcing', 'permissive', ou 'disabled'.

        Returns:
            bool: True si succès.
        """
        valid_modes = ['enforcing', 'permissive', 'disabled']
        mode_lower = mode.lower()
        if mode_lower not in valid_modes:
            self.log_error(f"Mode SELinux invalide: {mode}. Choisir parmi {valid_modes}.")
            return False

        config_path = "/etc/selinux/config"
        self.log_info(f"Configuration du mode SELinux persistant à '{mode_lower}' dans {config_path}")
        self.log_warning("Cette modification nécessite un redémarrage pour prendre effet.")

        if not os.path.exists(config_path):
             # Tenter /etc/sysconfig/selinux pour les anciens systèmes RHEL/CentOS
             alt_config_path = "/etc/sysconfig/selinux"
             if os.path.exists(alt_config_path):
                  config_path = alt_config_path
             else:
                  self.log_error(f"Fichier de configuration SELinux introuvable ({config_path} ou {alt_config_path}).")
                  return False

        # Utiliser sed pour modifier la ligne SELINUX=...
        # sed -i 's/^SELINUX=.*/SELINUX=new_mode/' /path/to/config
        # L'option -i nécessite des précautions avec sudo. Il est plus sûr de lire, modifier, et écrire.
        try:
            # Lire le fichier (nécessite potentiellement root)
            read_success, current_content, read_stderr = self.run(['cat', config_path], check=False, needs_sudo=True)
            if not read_success:
                 self.log_error(f"Impossible de lire {config_path}. Stderr: {read_stderr}")
                 return False

            new_lines = []
            found = False
            for line in current_content.splitlines():
                line_strip = line.strip()
                if line_strip.startswith('SELINUX=') and not line_strip.startswith('#'):
                    new_lines.append(f'SELINUX={mode_lower}')
                    found = True
                else:
                    new_lines.append(line) # Garder la ligne originale

            # Si la ligne n'a pas été trouvée, l'ajouter (moins courant)
            if not found:
                 self.log_warning(f"Ligne 'SELINUX=' non trouvée dans {config_path}, ajout en fin de fichier.")
                 new_lines.append(f'SELINUX={mode_lower}')

            new_content = "\n".join(new_lines) + "\n"

            # Écrire le nouveau contenu via un fichier temporaire et tee/cp
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".selinux.conf.tmp") as tf:
                tf.write(new_content)
                tmp_file = tf.name

            # Utiliser cp pour préserver le contexte SELinux potentiel du fichier original
            cmd_cp = ['cp', tmp_file, config_path]
            success_cp, _, stderr_cp = self.run(cmd_cp, check=False, needs_sudo=True)
            os.unlink(tmp_file) # Nettoyer le temporaire

            if success_cp:
                self.log_success(f"Mode SELinux persistant configuré à '{mode_lower}' dans {config_path}.")
                return True
            else:
                self.log_error(f"Échec de la mise à jour de {config_path}. Stderr: {stderr_cp}")
                return False

        except Exception as e:
            self.log_error(f"Erreur lors de la modification de {config_path}: {e}", exc_info=True)
            return False

    def get_selinux_boolean(self, boolean_name: str) -> Optional[bool]:
        """Récupère la valeur actuelle d'un booléen SELinux."""
        self.log_debug(f"Récupération du booléen SELinux: {boolean_name}")
        # getsebool retourne "boolean --> on|off" ou une erreur si inconnu
        success, stdout, stderr = self.run(['getsebool', boolean_name], check=False, no_output=True)
        if not success:
            if "invalid boolean" in stderr.lower() or "no such file or directory" in stderr.lower():
                 self.log_warning(f"Booléen SELinux inconnu: {boolean_name}")
            else:
                 self.log_error(f"Échec de getsebool pour {boolean_name}. Stderr: {stderr}")
            return None

        try:
            # Format: httpd_can_network_connect --> on
            value_str = stdout.split('-->')[1].strip().lower()
            return value_str == 'on'
        except IndexError:
            self.log_warning(f"Format de sortie inattendu de getsebool: {stdout}")
            return None

    def set_selinux_boolean(self, boolean_name: str, value: bool, persistent: bool = True) -> bool:
        """
        Définit la valeur d'un booléen SELinux. Nécessite root pour persistent=True.

        Args:
            boolean_name: Nom du booléen.
            value: Nouvelle valeur (True pour 'on', False pour 'off').
            persistent: Si True, rend le changement persistant après redémarrage (-P).

        Returns:
            bool: True si succès.
        """
        value_str = 'on' if value else 'off'
        persistence_log = " (persistent)" if persistent else " (runtime)"
        self.log_info(f"Définition du booléen SELinux: {boolean_name} = {value_str}{persistence_log}")

        cmd = ['setsebool']
        if persistent:
            cmd.append('-P') # Nécessite root
        cmd.extend([boolean_name, value_str])

        # setsebool -P peut prendre du temps
        timeout = 120 if persistent else 30
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=persistent, timeout=timeout)

        if success:
            self.log_success(f"Booléen SELinux '{boolean_name}' mis à '{value_str}'{persistence_log}.")
            return True
        else:
            self.log_error(f"Échec de setsebool pour {boolean_name}. Stderr: {stderr}")
            return False

    def restorecon(self, path: Union[str, Path], recursive: bool = False, force: bool = False) -> bool:
        """
        Restaure le contexte de sécurité SELinux par défaut pour un fichier/dossier.
        Nécessite root.

        Args:
            path: Chemin du fichier ou dossier.
            recursive: Appliquer récursivement (-R).
            force: Forcer la restauration même si le contexte semble correct (-F).

        Returns:
            bool: True si succès.
        """
        target_path = Path(path)
        self.log_info(f"Restauration du contexte SELinux pour: {target_path}{' (récursif)' if recursive else ''}")

        if not target_path.exists():
            self.log_error(f"Le chemin n'existe pas: {target_path}")
            return False

        cmd = ['restorecon']
        if recursive: cmd.append('-R')
        if force: cmd.append('-F')
        cmd.append('-v') # Verbose pour voir les changements
        cmd.append(str(target_path))

        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if stdout: self.log_info(f"Sortie restorecon:\n{stdout}") # Afficher les changements

        if success:
            self.log_success(f"Contexte SELinux restauré pour {target_path}.")
            return True
        else:
            self.log_error(f"Échec de restorecon pour {target_path}. Stderr: {stderr}")
            return False

    # --- Fonctions AppArmor ---

    def get_apparmor_status(self) -> Optional[Dict[str, Any]]:
        """
        Récupère le statut d'AppArmor via aa-status. Nécessite root.

        Returns:
            Dictionnaire avec les informations (module loaded, profiles loaded,
            enforce count, complain count, processes profiled) ou None si erreur.
        """
        self.log_info("Récupération du statut AppArmor (aa-status)")
        success, stdout, stderr = self.run(['aa-status'], check=False, no_output=True, needs_sudo=True)

        if not success:
            if "command not found" in stderr.lower():
                 self.log_info("AppArmor n'est pas installé ou activé sur ce système.")
                 return {'apparmor_status': 'disabled'}
            self.log_error(f"Échec de la commande aa-status. Stderr: {stderr}")
            return None

        status_info: Dict[str, Any] = {'apparmor_status': 'enabled'}
        try:
            status_info['module_loaded'] = "apparmor module is loaded" in stdout.lower()

            match = re.search(r'(\d+)\s+profiles? are loaded', stdout)
            status_info['profiles_loaded'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+profiles? are in enforce mode', stdout)
            status_info['enforce_mode_count'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+profiles? are in complain mode', stdout)
            status_info['complain_mode_count'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+processes? have profiles defined', stdout)
            status_info['processes_defined_count'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+processes? are in enforce mode', stdout)
            status_info['processes_enforce_count'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+processes? are in complain mode', stdout)
            status_info['processes_complain_count'] = int(match.group(1)) if match else 0

            match = re.search(r'(\d+)\s+processes? are unconfined', stdout)
            status_info['processes_unconfined_count'] = int(match.group(1)) if match else 0

            self.log_debug(f"Statut AppArmor: {status_info}")
            return status_info

        except Exception as e:
             self.log_error(f"Erreur lors du parsing de la sortie aa-status: {e}", exc_info=True)
             self.log_debug(f"Sortie aa-status brute:\n{stdout}")
             return None # Retourner None si le parsing échoue

    def set_apparmor_profile_mode(self, profile_name: str, mode: str) -> bool:
        """
        Change le mode d'un profil AppArmor (complain ou enforce). Nécessite root.

        Args:
            profile_name: Nom du profil (ou chemin du fichier de profil).
            mode: 'complain' ou 'enforce'.

        Returns:
            bool: True si succès.
        """
        mode_lower = mode.lower()
        if mode_lower not in ['complain', 'enforce']:
            self.log_error(f"Mode AppArmor invalide: {mode}. Utiliser 'complain' ou 'enforce'.")
            return False

        cmd_action = f"aa-{mode_lower}" # aa-complain ou aa-enforce
        self.log_info(f"Passage du profil AppArmor '{profile_name}' en mode {mode_lower} ({cmd_action})")
        cmd = [cmd_action, profile_name]

        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)

        if success:
            self.log_success(f"Profil AppArmor '{profile_name}' passé en mode {mode_lower}.")
            if stdout: self.log_info(f"Sortie {cmd_action}:\n{stdout}")
            return True
        else:
            self.log_error(f"Échec du passage du profil '{profile_name}' en mode {mode_lower}. Stderr: {stderr}")
            return False

