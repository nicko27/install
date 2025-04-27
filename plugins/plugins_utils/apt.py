# install/plugins/plugins_utils/apt.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour la gestion complète des paquets Debian/Ubuntu avec apt.
Offre des fonctionnalités avancées pour installer, désinstaller, rechercher et gérer
les paquets et dépôts du système.
"""

# Import de la classe de base et des types
from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import time
from pathlib import Path
import shlex
from typing import Union, Optional, List, Dict, Any, Tuple, Set

# Import conditionnel pour ConfigFileCommands (utilisé dans add_repository)
try:
    from .config_files import ConfigFileCommands
    CONFIG_FILES_AVAILABLE = True
except ImportError:
    CONFIG_FILES_AVAILABLE = False
    class ConfigFileCommands: pass # Factice

class AptCommands(PluginsUtilsBase):
    """
    Classe avancée pour gérer les paquets via apt/apt-get.
    Hérite de PluginUtilsBase pour l'exécution de commandes et la progression.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise le gestionnaire de commandes apt.

        Args:
            logger: Instance de PluginLogger (optionnel).
            target_ip: IP cible pour les logs (optionnel).
        """
        super().__init__(logger, target_ip)
        # Environnement standard pour les commandes apt pour éviter les prompts interactifs
        self._apt_env = os.environ.copy()
        self._apt_env["DEBIAN_FRONTEND"] = "noninteractive"
        # Pas de stockage de task_id ici

    def update(self, allow_fail: bool = False, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Met à jour la liste des paquets disponibles via apt-get update.
        Cette méthode gère sa propre barre de progression interne via self.run.

        Args:
            allow_fail: Si True, renvoie True même si des erreurs non critiques surviennent.
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.

        Returns:
            bool: True si la mise à jour a réussi.
        """
        self.log_info("Mise à jour de la liste des paquets (apt update)", log_levels=log_levels)

        cmd = ['apt-get', 'update']
        success, stdout, stderr = self.run(cmd,
                                           check=False,
                                           env=self._apt_env,
                                           real_time_output=True,
                                           show_progress=True,
                                           error_as_warning=allow_fail, # Passe l'info à run
                                           log_levels=log_levels # Passe les niveaux de log à run
                                           )

        warning_issued = False
        final_success = success
        if not success and allow_fail:
            if "NO_PUBKEY" in stderr or "KEYEXPIRED" in stderr:
                self.log_warning("Problèmes de clés GPG détectés, mais continuer.", log_levels=log_levels)
                warning_issued = True
                final_success = True
            elif re.search(r'(Failed to fetch|Unable to fetch|Could not resolve)', stderr, re.IGNORECASE):
                self.log_warning("Certains dépôts n'ont pas pu être atteints, mais continuer.", log_levels=log_levels)
                warning_issued = True
                final_success = True
        elif not success:
             self.log_error(f"Échec critique de 'apt-get update'. Stderr:\n{stderr}", log_levels=log_levels)

        final_message = "Mise à jour des sources terminée"
        if final_success and not warning_issued:
             final_message += " avec succès."
             self.log_success(final_message, log_levels=log_levels)
        elif warning_issued:
             final_message += " avec des avertissements."
             self.log_warning(final_message, log_levels=log_levels)
        else: # final_success = False
             final_message += " avec échec critique."

        return final_success

    def upgrade(self,
                dist_upgrade: bool = False,
                full_upgrade: bool = False,
                simulate: bool = False,
                autoremove: bool = True,
                log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Met à jour les paquets installés.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        if dist_upgrade:
             upgrade_type_log = "complète (dist-upgrade)"
             cmd_verb = "dist-upgrade"
             apt_cmd = 'apt-get'
        elif full_upgrade:
             upgrade_type_log = "complète (full-upgrade)"
             cmd_verb = "full-upgrade"
             apt_cmd = 'apt'
        else:
             upgrade_type_log = "standard (upgrade)"
             cmd_verb = "upgrade"
             apt_cmd = 'apt-get'

        action_log = "Simulation" if simulate else "Exécution"
        log_prefix = f"{action_log} de la mise à jour {upgrade_type_log}"
        self.log_info(log_prefix, log_levels=log_levels)

        self.log_info(f"{log_prefix} - Étape 1: Mise à jour sources", log_levels=log_levels)
        update_success = self.update(allow_fail=True, log_levels=log_levels)
        if not update_success:
            self.log_error("Échec critique de la mise à jour des sources. Annulation.", log_levels=log_levels)
            return False

        self.log_info(f"{log_prefix} - Étape 2: Exécution {cmd_verb}", log_levels=log_levels)
        cmd = [apt_cmd, cmd_verb]
        cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
        cmd.append('-y')
        if simulate: cmd.append('--simulate')

        upgrade_success, stdout, stderr = self.run(cmd,
                                                   env=self._apt_env,
                                                   check=False,
                                                   timeout=3600,
                                                   real_time_output=True,
                                                   show_progress=True,
                                                   log_levels=log_levels
                                                   )
        if not upgrade_success:
            self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}", log_levels=log_levels)
            return False

        autoremove_success = True
        if not simulate and autoremove:
            self.log_info(f"{log_prefix} - Étape 3: Nettoyage (autoremove)", log_levels=log_levels)
            autoremove_success = self.autoremove(simulate=simulate, log_levels=log_levels)
            if not autoremove_success:
                self.log_warning("Échec de l'étape autoremove.", log_levels=log_levels)
        else:
            self.log_info(f"{log_prefix} - Terminé (autoremove ignoré)", log_levels=log_levels)

        final_success = upgrade_success
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        if final_success: self.log_success(final_message, log_levels=log_levels)

        return final_success

    def install(self,
                package_names: Union[str, List[str]],
                version: Optional[str] = None,
                reinstall: bool = False,
                auto_fix: bool = True,
                no_recommends: bool = False,
                simulate: bool = False,
                force_conf: bool = True,
                log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Installe un ou plusieurs paquets.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        if isinstance(package_names, str): packages = [package_names]
        else: packages = list(package_names)
        if not packages:
             self.log_warning("Aucun paquet spécifié pour l'installation.", log_levels=log_levels)
             return True

        action = "Simulation d'installation" if simulate else "Installation"
        package_str = ", ".join(packages)
        log_prefix = f"{action} de: {package_str}"
        self.log_info(log_prefix, log_levels=log_levels)

        target_packages = []
        if version and len(packages) == 1:
             self.log_info(f"Version spécifiée: {version}", log_levels=log_levels)
             target_packages.append(f"{packages[0]}={version}")
        elif version:
             self.log_warning("Spec version supportée pour 1 paquet/fois.", log_levels=log_levels)
             target_packages = packages
        else:
             target_packages = packages

        self.log_info(f"{log_prefix} - Étape 1: Tentative initiale", log_levels=log_levels)
        cmd = ['apt-get', 'install', '-y']
        if force_conf: cmd.extend(['-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold'])
        if reinstall: cmd.append('--reinstall')
        if no_recommends: cmd.append('--no-install-recommends')
        if simulate: cmd.append('--simulate')
        cmd.extend(target_packages)

        install_success, stdout, stderr = self.run(cmd,
                                                   env=self._apt_env,
                                                   check=False,
                                                   real_time_output=True,
                                                   show_progress=True,
                                                   timeout=3600,
                                                   log_levels=log_levels)

        if not install_success and not simulate and auto_fix:
            if re.search(r'(unmet depend|broken package|held broken)', stderr, re.IGNORECASE):
                self.log_info(f"{log_prefix} - Étape 2: Tentative de réparation", log_levels=log_levels)
                self.log_warning("Problème dépendances, tentative réparation...", log_levels=log_levels)

                fix_success = self.fix_broken(simulate=simulate, log_levels=log_levels)
                if fix_success:
                    self.log_info("Réparation réussie, nouvelle tentative...", log_levels=log_levels)
                    install_success, stdout, stderr = self.run(cmd,
                                                               env=self._apt_env,
                                                               check=False,
                                                               real_time_output=True,
                                                               show_progress=True,
                                                               timeout=3600,
                                                               log_levels=log_levels)
                else:
                     self.log_error("Échec de la réparation des dépendances.", log_levels=log_levels)
                     install_success = False
            else:
                 self.log_info(f"{log_prefix} - Étape 2: Réparation non nécessaire", log_levels=log_levels)
        elif not simulate and auto_fix:
             self.log_info(f"{log_prefix} - Étape 2: Réparation non nécessaire", log_levels=log_levels)

        final_message = f"{log_prefix} {'réussie' if install_success else 'échouée'}"
        if not install_success:
            self.log_error(f"Échec final de '{' '.join(cmd)}'.", log_levels=log_levels)
            if stderr: self.log_error(f"Dernier Stderr:\n{stderr}", log_levels=log_levels)
            if stdout: self.log_info(f"Dernier Stdout:\n{stdout}", log_levels=log_levels)
        else:
            self.log_success(final_message, log_levels=log_levels)

        return install_success

    def uninstall(self,
                  package_names: Union[str, List[str]],
                  purge: bool = False,
                  auto_remove: bool = True,
                  simulate: bool = False,
                  log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Désinstalle un ou plusieurs paquets.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        if isinstance(package_names, str): packages = [package_names]
        else: packages = list(package_names)
        if not packages:
             self.log_warning("Aucun paquet spécifié pour la désinstallation.", log_levels=log_levels)
             return True

        action = "Simulation" if simulate else "Exécution"
        action_type = "complète (purge)" if purge else "standard"
        package_str = ", ".join(packages)
        log_prefix = f"{action} désinstallation {action_type} de {package_str}"
        self.log_info(log_prefix, log_levels=log_levels)

        self.log_info(f"{log_prefix} - Étape 1: Désinstallation", log_levels=log_levels)
        cmd = ['apt-get']
        cmd.append('purge' if purge else 'remove')
        cmd.append('-y')
        if simulate: cmd.append('--simulate')
        cmd.extend(packages)

        remove_success, stdout, stderr = self.run(cmd,
                                                  env=self._apt_env,
                                                  check=False,
                                                  real_time_output=True,
                                                  show_progress=True,
                                                  log_levels=log_levels
                                                  )

        if not remove_success:
             self.log_error(f"Échec de '{' '.join(cmd)}'. Stderr:\n{stderr}", log_levels=log_levels)
             return False

        autoremove_success = True
        if not simulate and auto_remove:
            self.log_info(f"{log_prefix} - Étape 2: Nettoyage (autoremove)", log_levels=log_levels)
            autoremove_success = self.autoremove(simulate=simulate, log_levels=log_levels)
            if not autoremove_success:
                self.log_warning("Échec de l'étape autoremove.", log_levels=log_levels)
        else:
            self.log_info(f"{log_prefix} - Terminé (autoremove ignoré)", log_levels=log_levels)

        final_success = remove_success
        final_message = f"{log_prefix} {'terminée' if final_success else 'échouée'}"
        if final_success: self.log_success(final_message, log_levels=log_levels)

        return final_success

    def autoremove(self, purge: bool = False, simulate: bool = False, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Supprime les paquets inutilisés.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        cmd = ['apt-get', 'autoremove', '-y']
        if purge: cmd.append('--purge')
        if simulate: cmd.append('--simulate')

        action = "Simulation" if simulate else "Exécution"
        log_prefix = f"{action} nettoyage paquets inutilisés (autoremove)"
        self.log_info(log_prefix, log_levels=log_levels)

        success, stdout, stderr = self.run(cmd,
                                           env=self._apt_env,
                                           check=False,
                                           real_time_output=True,
                                           show_progress=True,
                                           log_levels=log_levels
                                           )

        final_message = log_prefix
        if success:
            if not simulate:
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout):
                     final_message += ": Aucun paquet à supprimer."
                     self.log_info(final_message, log_levels=log_levels)
                else:
                     final_message += " réussi."
                     self.log_success(final_message, log_levels=log_levels)
            else:
                 final_message += " terminé."
                 self.log_info(final_message, log_levels=log_levels)
                 self.log_info(f"Simulation stdout:\n{stdout}", log_levels=log_levels)
        else:
             final_message += " échoué."
             self.log_error(final_message, log_levels=log_levels)
             self.log_error(f"Stderr:\n{stderr}", log_levels=log_levels)

        return success

    def clean(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Nettoie le cache apt.

        Args:
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        self.log_info("Nettoyage du cache apt (apt-get clean)", log_levels=log_levels)
        success, _, stderr = self.run(['apt-get', 'clean'], env=self._apt_env, check=False, log_levels=log_levels)
        final_message = "Nettoyage cache apt"
        if success:
             final_message += " réussi."
             self.log_success(final_message, log_levels=log_levels)
        else:
             final_message += " échoué."
             self.log_error(f"{final_message}. Stderr:\n{stderr}", log_levels=log_levels)
        return success

    def autoclean(self, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Nettoie le cache apt des paquets obsolètes.

        Args:
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        self.log_info("Nettoyage paquets obsolètes cache apt (apt-get autoclean)", log_levels=log_levels)
        success, _, stderr = self.run(['apt-get', 'autoclean'], env=self._apt_env, check=False, log_levels=log_levels)
        final_message = "Nettoyage autoclean cache apt"
        if success:
             final_message += " réussi."
             self.log_success(final_message, log_levels=log_levels)
        else:
             final_message += " échoué."
             self.log_error(f"{final_message}. Stderr:\n{stderr}", log_levels=log_levels)
        return success

    def fix_broken(self, simulate: bool = False, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Tente de réparer les dépendances cassées.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        cmd = ['apt-get', 'install', '--fix-broken', '-y']
        if simulate: cmd.append('--simulate')

        action = "Simulation" if simulate else "Exécution"
        log_prefix = f"{action} réparation dépendances cassées"
        self.log_info(f"{log_prefix} (apt --fix-broken install)", log_levels=log_levels)

        success, stdout, stderr = self.run(cmd,
                                           env=self._apt_env,
                                           check=False,
                                           real_time_output=True,
                                           show_progress=True,
                                           timeout=1800,
                                           log_levels=log_levels)

        final_message = log_prefix
        if success:
            if not simulate:
                if re.search(r'0 upgraded, 0 newly installed, 0 to remove', stdout) and \
                   re.search(r'0 not upgraded', stdout):
                     final_message += ": Aucune dépendance cassée trouvée."
                     self.log_info(final_message, log_levels=log_levels)
                else:
                     final_message += " réussie."
                     self.log_success(final_message, log_levels=log_levels)
            else:
                 final_message += " terminée."
                 self.log_info(final_message, log_levels=log_levels)
                 self.log_info(f"Simulation stdout:\n{stdout}", log_levels=log_levels)
        else:
             final_message += " échouée."
             self.log_error(final_message, log_levels=log_levels)
             self.log_error(f"Stderr:\n{stderr}", log_levels=log_levels)

        return success

    def add_repository(self, repo_line: str, key_url: Optional[str] = None,
                       keyring_path: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Ajoute un dépôt APT et sa clé GPG.

        Args:
            [...]
            log_levels: Dictionnaire optionnel pour spécifier les niveaux de log.
        """
        self.log_info(f"Ajout du dépôt: {repo_line}", log_levels=log_levels)

        key_options = ""
        actual_keyring_path = None
        if key_url:
            if keyring_path:
                 actual_keyring_path = Path(keyring_path)
                 if not actual_keyring_path.is_absolute():
                      self.log_error(f"keyring_path doit être absolu: {keyring_path}", log_levels=log_levels)
                      return False
            else:
                try:
                    domain = key_url.split('//')[1].split('/')[0].replace('.', '-')
                    default_keyring_dir = Path("/etc/apt/keyrings")
                    actual_keyring_path = default_keyring_dir / f"{domain}.gpg"
                except IndexError:
                     self.log_error(f"URL de clé invalide: {key_url}", log_levels=log_levels)
                     return False

            self.log_info(f"Téléchargement clé GPG {key_url} -> {actual_keyring_path}", log_levels=log_levels)
            keyring_dir = actual_keyring_path.parent
            if not keyring_dir.exists():
                 self.log_info(f"Création dossier keyring: {keyring_dir}", log_levels=log_levels)
                 mkdir_success, _, mkdir_stderr = self.run(['mkdir', '-p', str(keyring_dir)], check=False, needs_sudo=True, log_levels=log_levels)
                 if not mkdir_success:
                      self.log_error(f"Impossible créer {keyring_dir}: {mkdir_stderr}", log_levels=log_levels)
                      return False

            cmd_curl = ['curl', '-fsSL', key_url]
            success_curl, key_data, stderr_curl = self.run(cmd_curl, check=False, no_output=True, log_levels=log_levels)
            if not success_curl:
                 self.log_error(f"Échec téléchargement clé GPG {key_url}. Stderr: {stderr_curl}", log_levels=log_levels)
                 return False

            quoted_keyring_path = shlex.quote(str(actual_keyring_path))
            cmd_gpg_tee_str = f"gpg --dearmor --yes -o /dev/stdout | tee {quoted_keyring_path} > /dev/null"
            success_gpg, _, stderr_gpg = self.run(cmd_gpg_tee_str, input_data=key_data, shell=True, check=False, needs_sudo=True, log_levels=log_levels)

            if not success_gpg:
                self.log_error(f"Échec traitement/écriture clé GPG -> {actual_keyring_path}. Stderr: {stderr_gpg}", log_levels=log_levels)
                self.run(['rm', '-f', str(actual_keyring_path)], check=False, needs_sudo=True, log_levels=log_levels)
                return False

            self.run(['chmod', '644', str(actual_keyring_path)], check=False, needs_sudo=True, log_levels=log_levels)
            key_options = f"[signed-by={str(actual_keyring_path)}]"
            self.log_success(f"Clé GPG ajoutée: {actual_keyring_path}", log_levels=log_levels)
        else:
            self.log_info("Aucune clé GPG spécifiée.", log_levels=log_levels)

        self.log_info("Configuration fichier source...", log_levels=log_levels)
        repo_parts = repo_line.split()
        repo_name_base = "custom-repo"
        for part in repo_parts:
            if part.startswith(('http://', 'https://')):
                try:
                    repo_name_base = part.split('//')[1].split('/')[0].replace('.', '-').replace(':','-')
                    break
                except IndexError: pass
        arch_part = next((p for p in repo_parts if p.startswith('[') and 'arch=' in p), None)
        if arch_part:
             arch_match = re.search(r'arch=(\S+)', arch_part)
             if arch_match: repo_name_base += f"-{arch_match.group(1).rstrip(']')}"
        source_file_path = Path(f"/etc/apt/sources.list.d/{repo_name_base}.list")

        repo_line_parts = repo_line.split(None, 1)
        final_repo_line = repo_line
        if key_options:
            if len(repo_line_parts) == 2 and repo_line_parts[0].startswith("deb"):
                final_repo_line = f"{repo_line_parts[0]} {key_options} {repo_line_parts[1]}"
            else:
                 self.log_warning("Format ligne dépôt inconnu, ajout [signed-by] au début.", log_levels=log_levels)
                 final_repo_line = f"{key_options} {repo_line}"

        self.log_info(f"Ajout ligne au fichier: {source_file_path}", log_levels=log_levels)
        if not CONFIG_FILES_AVAILABLE:
             self.log_error("Impossible écrire fichier source: ConfigFileCommands indisponible.", log_levels=log_levels)
             return False

        cfg_writer = ConfigFileCommands(self.logger, self.target_ip)
        # Passer log_levels à _write_file_content si la méthode le supporte
        # Note: _write_file_content appelle self.run qui utilise déjà log_levels
        success_add = cfg_writer._write_file_content(source_file_path, final_repo_line + "\n", backup=True)

        if not success_add:
            self.log_error(f"Échec ajout ligne dépôt à {source_file_path}.", log_levels=log_levels)
            return False

        self.log_success(f"Dépôt ajouté dans {source_file_path}", log_levels=log_levels)

        self.log_info("Mise à jour sources après ajout dépôt...", log_levels=log_levels)
        update_ok = self.update(allow_fail=True, log_levels=log_levels)

        final_message = f"Ajout dépôt {repo_name_base} {'terminé' if update_ok else 'terminé avec erreurs update'}"

        return update_ok

    # --- Méthodes is_installed, get_version, get_candidate_version ---
    # Elles n'ont pas besoin de log_levels car elles logguent peu et ne font pas d'actions modifiantes majeures.
    # Si besoin, on pourrait les ajouter.

    def is_installed(self, package_name: str, min_version: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> bool:
        """
        Vérifie si un paquet est installé.
        """
        self.log_debug(f"Vérification installation paquet: {package_name}", log_levels=log_levels)
        cmd = ['dpkg-query', '--show', '--showformat=${db:Status-Status}', package_name]
        # error_as_warning=True car dpkg-query échoue si le paquet n'est pas connu
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, error_as_warning=True, log_levels=log_levels)
        is_installed = success and stdout.strip() == 'installed'
        if not is_installed:
            self.log_debug(f"Paquet '{package_name}' non installé.", log_levels=log_levels)
            return False

        if min_version:
            installed_version = self.get_version(package_name, log_levels=log_levels)
            if not installed_version:
                 self.log_warning(f"Paquet '{package_name}' installé mais version inconnue.", log_levels=log_levels)
                 return is_installed # Retourner True car installé, mais avertissement
            self.log_debug(f"Comparaison version: {installed_version} >= {min_version}", log_levels=log_levels)
            cmd_compare = ['dpkg', '--compare-versions', installed_version, 'ge', min_version]
            success_cmp, _, _ = self.run(cmd_compare, check=False, no_output=True, error_as_warning=True, log_levels=log_levels)
            if not success_cmp:
                 self.log_warning(f"Paquet '{package_name}' ({installed_version}) < version min ({min_version}).", log_levels=log_levels)
                 return False
            self.log_info(f"Paquet '{package_name}' ({installed_version}) >= version min ({min_version}).", log_levels=log_levels)
        else:
            self.log_info(f"Paquet '{package_name}' est installé.", log_levels=log_levels)
        return True

    def get_version(self, package_name: str, log_levels: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Obtient la version installée d'un paquet."""
        self.log_debug(f"Récupération version installée de: {package_name}", log_levels=log_levels)
        cmd = ['dpkg-query', '--show', '--showformat=${Version}', package_name]
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, error_as_warning=True, log_levels=log_levels)
        if success and stdout.strip():
            version = stdout.strip()
            self.log_debug(f"Version installée de {package_name}: {version}", log_levels=log_levels)
            return version
        else:
             # Ne pas logguer en warning si c'est juste "package not found"
             if "no packages found matching" not in stderr.lower():
                  self.log_warning(f"Impossible d'obtenir la version de {package_name}. Stderr: {stderr}", log_levels=log_levels)
             else:
                  self.log_debug(f"Paquet '{package_name}' non trouvé par dpkg-query.", log_levels=log_levels)
             return None

    def get_candidate_version(self, package_name: str, log_levels: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Obtient la version candidate via `apt-cache policy`."""
        self.log_debug(f"Récupération version candidate de: {package_name}", log_levels=log_levels)
        cmd = ['apt-cache', 'policy', package_name]
        # error_as_warning=True car apt-cache échoue si paquet inconnu
        success, stdout, stderr = self.run(cmd, check=False, no_output=True, error_as_warning=True, log_levels=log_levels)
        if not success:
             if "unable to locate package" not in stderr.lower():
                  self.log_warning(f"Impossible obtenir policy apt pour {package_name}. Stderr: {stderr}", log_levels=log_levels)
             else:
                  self.log_debug(f"Paquet '{package_name}' non trouvé dans les sources apt.", log_levels=log_levels)
             return None

        candidate_version = None
        for line in stdout.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("Candidate:"):
                version_part = line_strip.split(":", 1)[1].strip()
                if version_part != '(none)': candidate_version = version_part
                break
        self.log_debug(f"Version candidate de {package_name}: {candidate_version}", log_levels=log_levels)
        return candidate_version