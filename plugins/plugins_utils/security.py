# install/plugins/plugins_utils/security.py
#!/usr/bin/env python3
"""
Module utilitaire pour les tâches de sécurité courantes.
Gestion des clés SSH, permissions, propriétaires, interaction fail2ban.
"""

from .plugin_utils_base import PluginUtilsBase
import os
import pwd # Pour trouver le home directory d'un utilisateur
import grp # Pour trouver le groupe d'un utilisateur
import stat # Pour interpréter les modes de permission
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple

class SecurityCommands(PluginUtilsBase):
    """
    Classe pour effectuer des opérations de sécurité courantes.
    Hérite de PluginUtilsBase pour l'exécution de commandes.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire de sécurité."""
        super().__init__(logger, target_ip)
        self._check_commands()

    def _check_commands(self):
        """Vérifie si les commandes nécessaires sont disponibles."""
        cmds = ['ssh-keygen', 'chmod', 'chown', 'fail2ban-client', 'getent', 'mkdir', 'touch', 'cat', 'grep', 'sed']
        missing = []
        for cmd in cmds:
            success, _, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
            if not success:
                missing.append(cmd)
        if missing:
            self.log_warning(f"Commandes potentiellement manquantes: {', '.join(missing)}. "
                             f"Installer 'openssh-client', 'coreutils', 'fail2ban', 'libc-bin'.")

    def _get_user_home_ssh_dir(self, username: str) -> Optional[Path]:
        """Trouve le chemin du dossier .ssh pour un utilisateur."""
        try:
            user_info = pwd.getpwnam(username)
            home_dir = Path(user_info.pw_dir)
            ssh_dir = home_dir / ".ssh"
            return ssh_dir
        except KeyError:
            self.log_error(f"Utilisateur '{username}' non trouvé.")
            return None
        except Exception as e:
            self.log_error(f"Erreur lors de la récupération du dossier .ssh pour {username}: {e}")
            return None

    def _ensure_ssh_dir(self, username: str, ssh_dir: Path) -> bool:
        """S'assure que le dossier .ssh existe avec les bonnes permissions (700)."""
        try:
            user_info = pwd.getpwnam(username)
            uid = user_info.pw_uid
            gid = user_info.pw_gid

            if not ssh_dir.exists():
                self.log_info(f"Création du dossier {ssh_dir}")
                # Utiliser mkdir et chown/chmod via self.run pour gérer sudo
                success_mkdir, _, err_mkdir = self.run(['mkdir', '-p', str(ssh_dir)], needs_sudo=True)
                if not success_mkdir:
                     self.log_error(f"Impossible de créer {ssh_dir}. Stderr: {err_mkdir}")
                     return False
            else:
                 self.log_debug(f"Le dossier {ssh_dir} existe déjà.")

            # Définir propriétaire et permissions (même si existe déjà, pour être sûr)
            success_chown, _, err_chown = self.run(['chown', f"{uid}:{gid}", str(ssh_dir)], needs_sudo=True)
            success_chmod, _, err_chmod = self.run(['chmod', '700', str(ssh_dir)], needs_sudo=True)

            if not success_chown or not success_chmod:
                 self.log_error(f"Échec de la définition des permissions/propriétaire pour {ssh_dir}. Chown stderr: {err_chown}, Chmod stderr: {err_chmod}")
                 return False

            return True

        except KeyError:
            self.log_error(f"Utilisateur '{username}' non trouvé lors de la configuration de {ssh_dir}.")
            return False
        except Exception as e:
            self.log_error(f"Erreur lors de la configuration de {ssh_dir}: {e}", exc_info=True)
            return False

    def generate_ssh_key(self,
                         key_path: Union[str, Path],
                         key_type: str = 'rsa',
                         bits: int = 4096,
                         passphrase: str = '', # Vide pour pas de passphrase
                         comment: str = '',
                         overwrite: bool = False) -> bool:
        """
        Génère une nouvelle paire de clés SSH via ssh-keygen.

        Args:
            key_path: Chemin où enregistrer la clé privée (ex: /home/user/.ssh/id_rsa).
                      La clé publique sera enregistrée avec l'extension .pub.
            key_type: Type de clé (rsa, ed25519, ecdsa, dsa).
            bits: Nombre de bits pour la clé (pertinent pour RSA/DSA).
            passphrase: Phrase de passe pour protéger la clé privée (vide pour aucune).
            comment: Commentaire à ajouter à la clé publique.
            overwrite: Si True, écrase les clés existantes sans demander.

        Returns:
            bool: True si la génération a réussi.
        """
        key_path_obj = Path(key_path)
        key_pub_path = key_path_obj.with_suffix('.pub')
        self.log_info(f"Génération de la clé SSH ({key_type}, {bits} bits) vers: {key_path_obj}")

        if key_path_obj.exists() and not overwrite:
            self.log_error(f"Le fichier de clé privée {key_path_obj} existe déjà. Utiliser overwrite=True pour écraser.")
            return False
        elif key_path_obj.exists() or key_pub_path.exists():
             self.log_warning(f"Écrasement des fichiers de clé existants: {key_path_obj} / {key_pub_path}")
             # Supprimer les anciens fichiers avant de générer
             try:
                  if key_path_obj.exists(): key_path_obj.unlink()
                  if key_pub_path.exists(): key_pub_path.unlink()
             except Exception as e_del:
                  self.log_error(f"Impossible de supprimer les anciennes clés: {e_del}")
                  return False # Ne pas continuer si on ne peut pas écraser

        # Créer le dossier parent si nécessaire (ex: .ssh)
        try:
            key_path_obj.parent.mkdir(parents=True, exist_ok=True)
            # Idéalement, définir les bonnes permissions sur le dossier parent ici aussi
            # Mais on ne connaît pas forcément l'utilisateur prévu à ce stade
        except Exception as e_mkdir:
            self.log_error(f"Impossible de créer le dossier parent {key_path_obj.parent}: {e_mkdir}")
            return False

        cmd = [
            'ssh-keygen',
            '-t', key_type,
            '-b', str(bits),
            '-f', str(key_path_obj), # Chemin de sortie
            '-N', passphrase,      # Passphrase (vide si '')
            '-C', comment          # Commentaire
        ]

        # ssh-keygen peut demander confirmation s'il doit écraser, même si on a supprimé avant.
        # On utilise 'yes' pour répondre automatiquement, bien que la suppression préalable devrait suffire.
        # Note: Cela suppose que ssh-keygen ne pose pas d'autres questions.
        yes_cmd = ['yes', 'y', '|'] + cmd # Envoyer 'y' sur stdin
        success, stdout, stderr = self.run(" ".join(yes_cmd), shell=True, check=False)

        if success and key_path_obj.exists() and key_pub_path.exists():
            self.log_success(f"Clé SSH générée avec succès: {key_path_obj}")
            # Définir les permissions restrictives sur la clé privée
            self.set_permissions(key_path_obj, mode="600")
            return True
        else:
            self.log_error(f"Échec de la génération de la clé SSH. Stderr: {stderr}")
            if stdout: self.log_info(f"Sortie ssh-keygen (échec):\n{stdout}")
            # Nettoyer les fichiers potentiellement créés
            if key_path_obj.exists(): key_path_obj.unlink()
            if key_pub_path.exists(): key_pub_path.unlink()
            return False

    def add_authorized_key(self, username: str, public_key_content: str) -> bool:
        """
        Ajoute une clé publique au fichier authorized_keys d'un utilisateur.
        Gère la création du dossier .ssh et les permissions. Nécessite root.

        Args:
            username: Nom de l'utilisateur cible.
            public_key_content: Contenu complet de la clé publique à ajouter.

        Returns:
            bool: True si la clé a été ajoutée avec succès.
        """
        self.log_info(f"Ajout d'une clé publique autorisée pour l'utilisateur: {username}")
        ssh_dir = self._get_user_home_ssh_dir(username)
        if not ssh_dir: return False # Erreur déjà logguée

        # S'assurer que le dossier .ssh existe avec les bonnes perms (700)
        if not self._ensure_ssh_dir(username, ssh_dir): return False

        auth_keys_path = ssh_dir / "authorized_keys"
        key_to_add = public_key_content.strip()

        # Vérifier si la clé existe déjà pour éviter les doublons
        key_exists = False
        if auth_keys_path.exists():
            try:
                # Lire avec sudo car le fichier appartient à l'utilisateur
                cmd_grep = ['grep', '-qFx', key_to_add, str(auth_keys_path)]
                # check=False, le code retour indique si trouvé (0) ou non (1)
                success_grep, _, _ = self.run(cmd_grep, check=False, needs_sudo=True, no_output=True)
                key_exists = success_grep
            except Exception as e_grep:
                 self.log_warning(f"Erreur lors de la vérification de l'existence de la clé: {e_grep}")
                 # Continuer et essayer d'ajouter quand même

        if key_exists:
            self.log_info(f"La clé publique existe déjà dans {auth_keys_path}.")
            return True

        # Ajouter la clé au fichier (avec sudo)
        # Utiliser tee -a pour ajouter en fin de fichier
        self.log_info(f"Ajout de la clé à {auth_keys_path}")
        cmd_add = ['tee', '-a', str(auth_keys_path)]
        success_add, _, stderr_add = self.run(cmd_add, input_data=key_to_add + "\n", check=False, needs_sudo=True)

        if not success_add:
            self.log_error(f"Échec de l'ajout de la clé à {auth_keys_path}. Stderr: {stderr_add}")
            return False

        # Définir les permissions sur authorized_keys (600) et le propriétaire
        try:
            user_info = pwd.getpwnam(username)
            uid = user_info.pw_uid
            gid = user_info.pw_gid
            success_chown, _, err_chown = self.run(['chown', f"{uid}:{gid}", str(auth_keys_path)], needs_sudo=True)
            success_chmod, _, err_chmod = self.run(['chmod', '600', str(auth_keys_path)], needs_sudo=True)
            if not success_chown or not success_chmod:
                 self.log_error(f"Échec de la définition des permissions/propriétaire pour {auth_keys_path}. Chown stderr: {err_chown}, Chmod stderr: {err_chmod}")
                 return False # L'ajout a réussi mais les perms sont mauvaises
            self.log_success(f"Clé publique ajoutée et permissions définies pour {username}.")
            return True
        except KeyError:
             self.log_error(f"Utilisateur '{username}' non trouvé lors de la définition des permissions finales.")
             return False
        except Exception as e_perm:
             self.log_error(f"Erreur lors de la définition des permissions finales: {e_perm}")
             return False

    def remove_authorized_key(self, username: str, key_identifier: str) -> bool:
        """
        Supprime une clé publique du fichier authorized_keys d'un utilisateur.

        Args:
            username: Nom de l'utilisateur cible.
            key_identifier: Contenu complet de la clé publique OU le commentaire de la clé.

        Returns:
            bool: True si la clé a été supprimée ou n'existait pas.
        """
        self.log_info(f"Suppression de la clé publique autorisée pour '{username}' identifiée par '{key_identifier[:30]}...'")
        ssh_dir = self._get_user_home_ssh_dir(username)
        if not ssh_dir: return False

        auth_keys_path = ssh_dir / "authorized_keys"

        if not auth_keys_path.exists():
            self.log_warning(f"Le fichier {auth_keys_path} n'existe pas.")
            return True # Clé non présente = succès

        # Utiliser sed pour supprimer la ligne correspondante (plus sûr que lire/écrire)
        # Échapper les caractères spéciaux pour sed
        escaped_identifier = key_identifier.replace('/', '\\/').replace('&', '\\&').replace('"', '\\"').replace("'", "\\'")
        # Commande sed pour supprimer les lignes contenant l'identifiant
        # Utiliser -i pour modifier sur place (avec sudo)
        cmd_sed = ['sed', '-i', f"/{escaped_identifier}/d", str(auth_keys_path)]

        self.log_debug(f"Exécution de sed pour supprimer la clé: {' '.join(cmd_sed)}")
        success, stdout, stderr = self.run(cmd_sed, check=False, needs_sudo=True)

        if success:
            # Vérifier si quelque chose a été supprimé (difficile avec sed -i)
            # On pourrait relire le fichier et comparer, mais c'est lourd.
            # On suppose que si sed réussit, c'est bon.
            self.log_success(f"Clé(s) correspondant à '{key_identifier[:30]}...' supprimée(s) de {auth_keys_path} (si elle existait).")
            return True
        else:
            self.log_error(f"Échec de la suppression de la clé dans {auth_keys_path}. Stderr: {stderr}")
            return False

    def set_permissions(self, path: Union[str, Path], mode: Union[str, int], recursive: bool = False) -> bool:
        """
        Modifie les permissions d'un fichier ou d'un dossier.

        Args:
            path: Chemin du fichier ou dossier.
            mode: Mode octal (ex: 755, 600) ou symbolique (ex: u+x, g-w).
            recursive: Appliquer récursivement aux sous-dossiers/fichiers (-R).

        Returns:
            bool: True si succès.
        """
        target_path = Path(path)
        mode_str = str(mode) # chmod accepte les deux formats
        self.log_info(f"Modification des permissions de {target_path} en {mode_str}{' (récursif)' if recursive else ''}")

        if not target_path.exists():
             self.log_error(f"Le chemin n'existe pas: {target_path}")
             return False

        cmd = ['chmod']
        if recursive:
            cmd.append('-R')
        cmd.append(mode_str)
        cmd.append(str(target_path))

        # chmod peut nécessiter root selon le fichier/dossier
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)

        if success:
            self.log_success(f"Permissions de {target_path} mises à jour.")
            return True
        else:
            self.log_error(f"Échec de chmod sur {target_path}. Stderr: {stderr}")
            return False

    def set_ownership(self, path: Union[str, Path], user: Optional[str] = None, group: Optional[str] = None, recursive: bool = False) -> bool:
        """
        Modifie le propriétaire et/ou le groupe d'un fichier ou dossier. Nécessite root.

        Args:
            path: Chemin du fichier ou dossier.
            user: Nouveau nom d'utilisateur propriétaire (ou UID). Si None, ne change pas.
            group: Nouveau nom de groupe propriétaire (ou GID). Si None, ne change pas.
            recursive: Appliquer récursivement (-R).

        Returns:
            bool: True si succès.
        """
        target_path = Path(path)
        if not user and not group:
            self.log_warning("Aucun utilisateur ou groupe spécifié pour set_ownership.")
            return True # Rien à faire

        owner_spec = ""
        if user: owner_spec += str(user)
        if group: owner_spec += f":{str(group)}"
        elif user: owner_spec += ":" # Ex: chown user: file (change le groupe au groupe principal de user)

        if not owner_spec or owner_spec == ":":
             self.log_error("Spécification propriétaire/groupe invalide.")
             return False

        self.log_info(f"Modification du propriétaire/groupe de {target_path} en {owner_spec}{' (récursif)' if recursive else ''}")

        if not target_path.exists():
             self.log_error(f"Le chemin n'existe pas: {target_path}")
             return False

        cmd = ['chown']
        if recursive:
            cmd.append('-R')
        cmd.append(owner_spec)
        cmd.append(str(target_path))

        # chown nécessite root
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)

        if success:
            self.log_success(f"Propriétaire/groupe de {target_path} mis à jour.")
            return True
        else:
            self.log_error(f"Échec de chown sur {target_path}. Stderr: {stderr}")
            return False

    # --- Fonctions Fail2Ban (simples wrappers) ---

    def fail2ban_ban_ip(self, jail: str, ip_address: str) -> bool:
        """Bannit une IP dans une jail fail2ban."""
        self.log_info(f"Bannissement de l'IP {ip_address} dans la jail '{jail}' (fail2ban)")
        cmd = ['fail2ban-client', 'set', jail, 'banip', ip_address]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            # stdout contient souvent le nombre d'IPs bannies (1)
            if stdout: self.log_info(f"Sortie fail2ban-client: {stdout.strip()}")
            self.log_success(f"IP {ip_address} bannie dans la jail '{jail}'.")
            return True
        else:
            self.log_error(f"Échec du bannissement de {ip_address}. Stderr: {stderr}")
            return False

    def fail2ban_unban_ip(self, jail: str, ip_address: str) -> bool:
        """Débannit une IP d'une jail fail2ban."""
        self.log_info(f"Débannissement de l'IP {ip_address} de la jail '{jail}' (fail2ban)")
        cmd = ['fail2ban-client', 'set', jail, 'unbanip', ip_address]
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True)
        if success:
            # stdout contient souvent le nombre d'IPs débannies (1) ou 0 si pas bannie
            if stdout: self.log_info(f"Sortie fail2ban-client: {stdout.strip()}")
            self.log_success(f"IP {ip_address} débannie de la jail '{jail}'.")
            return True
        else:
            self.log_error(f"Échec du débannissement de {ip_address}. Stderr: {stderr}")
            return False

    def fail2ban_status(self, jail: Optional[str] = None) -> Optional[str]:
        """Récupère le statut de fail2ban ou d'une jail spécifique."""
        target = f"de la jail '{jail}'" if jail else "global"
        self.log_info(f"Récupération du statut fail2ban {target}")
        cmd = ['fail2ban-client', 'status']
        if jail:
            cmd.append(jail)
        success, stdout, stderr = self.run(cmd, check=False, needs_sudo=True) # Status peut nécessiter sudo
        if success:
            self.log_debug(f"Statut fail2ban ({target}):\n{stdout}")
            return stdout
        else:
            self.log_error(f"Échec de la récupération du statut fail2ban {target}. Stderr: {stderr}")
            return None

