# install/plugins/plugins_utils/users_groups.py
#!/usr/bin/env python3
"""
Module utilitaire pour la gestion des utilisateurs et groupes locaux sous Linux.
Utilise les commandes système standard (useradd, usermod, userdel, groupadd, etc.).
"""

from plugins_utils.plugins_utils_base import PluginsUtilsBase
import os
import re
import crypt # Pour gérer les mots de passe cryptés
from typing import Union, Optional, List, Dict, Any, Tuple

class UserGroupCommands(PluginsUtilsBase):
    """
    Classe pour gérer les utilisateurs et groupes locaux.
    Hérite de PluginUtilsBase pour l'exécution de commandes et la progression.
    """

    def __init__(self, logger=None, target_ip=None):
        """Initialise le gestionnaire d'utilisateurs et groupes."""
        super().__init__(logger, target_ip)
        # Vérifier la présence des commandes nécessaires
        self._check_commands()

    def _check_commands(self):
        """Vérifie si les commandes de gestion sont disponibles."""
        cmds = ['useradd', 'usermod', 'userdel', 'groupadd', 'groupmod', 'groupdel', 'chpasswd', 'gpasswd', 'getent']
        missing = []
        for cmd in cmds:
            success, _, _ = self.run(['which', cmd], check=False, no_output=True, error_as_warning=True)
            if not success:
                missing.append(cmd)
        if missing:
            self.log_warning(f"Commandes potentiellement manquantes: {', '.join(missing)}. "
                             f"Installer 'passwd', 'shadow-utils', 'util-linux' ou équivalent.")

    # --- Fonctions de Vérification ---

    def user_exists(self, username: str) -> bool:
        """Vérifie si un utilisateur local existe."""
        self.log_debug(f"Vérification de l'existence de l'utilisateur: {username}")
        # getent passwd <username> retourne 0 si l'utilisateur existe, 2 sinon
        success, _, _ = self.run(['getent', 'passwd', username], check=False, no_output=True)
        exists = success # Le code de retour 0 indique l'existence
        self.log_debug(f"Utilisateur '{username}' existe: {exists}")
        return exists

    def group_exists(self, groupname: str) -> bool:
        """Vérifie si un groupe local existe."""
        self.log_debug(f"Vérification de l'existence du groupe: {groupname}")
        # getent group <groupname> retourne 0 si le groupe existe, 2 sinon
        success, _, _ = self.run(['getent', 'group', groupname], check=False, no_output=True)
        exists = success
        self.log_debug(f"Groupe '{groupname}' existe: {exists}")
        return exists

    # --- Gestion des Utilisateurs ---

    def add_user(self,
                 username: str,
                 password: Optional[str] = None,
                 encrypted_password: Optional[str] = None,
                 uid: Optional[int] = None,
                 gid: Optional[Union[int, str]] = None,
                 gecos: Optional[str] = None, # Commentaire/Nom complet
                 home_dir: Optional[str] = None, # Chemin ou 'no' pour ne pas créer
                 create_home: bool = True, # Utiliser -m ou -M
                 shell: Optional[str] = '/bin/bash',
                 primary_group: Optional[str] = None, # Utiliser -g (gid ou nom)
                 secondary_groups: Optional[List[str]] = None, # Utiliser -G
                 system_user: bool = False, # Utiliser -r
                 no_user_group: bool = False, # Utiliser -n
                 no_log_init: bool = False # Utiliser -l (ne pas ajouter au lastlog)
                 ) -> bool:
        """
        Ajoute un nouvel utilisateur local.

        Args:
            username: Nom de l'utilisateur.
            password: Mot de passe en clair (sera crypté via chpasswd).
            encrypted_password: Mot de passe déjà crypté (format compatible /etc/shadow).
            uid: UID spécifique (optionnel).
            gid: GID ou nom du groupe principal (optionnel, useradd crée souvent un groupe privé sinon).
            gecos: Informations GECOS (ex: "Nom Complet,,,,").
            home_dir: Chemin du répertoire personnel. Si None, utilise le défaut système. Si 'no', utilise -M.
            create_home: Si True (défaut), crée le home directory (-m). Si False et home_dir!='no', ne le crée pas (-M).
            shell: Shell de connexion.
            primary_group: Nom ou GID du groupe principal (-g).
            secondary_groups: Liste des noms de groupes secondaires (-G).
            system_user: Créer un utilisateur système (-r).
            no_user_group: Ne pas créer de groupe privé pour l'utilisateur (-n).
            no_log_init: Ne pas ajouter l'utilisateur au fichier lastlog (-l).

        Returns:
            bool: True si l'ajout a réussi.
        """
        if self.user_exists(username):
            self.log_error(f"L'utilisateur '{username}' existe déjà.")
            return False

        self.log_info(f"Ajout de l'utilisateur: {username}")
        cmd = ['useradd']

        if system_user: cmd.append('-r')
        if uid is not None: cmd.extend(['-u', str(uid)])
        if gid is not None: cmd.extend(['-g', str(gid)]) # Groupe principal initial
        if gecos: cmd.extend(['-c', gecos])

        # Gestion du home directory
        if home_dir == 'no':
            cmd.append('-M') # Ne pas créer le home
            self.log_info("  - Ne créera pas de répertoire personnel.")
        elif home_dir:
            cmd.extend(['-d', home_dir])
            cmd.append('-m' if create_home else '-M')
            self.log_info(f"  - Répertoire personnel: {home_dir} (création: {create_home})")
        elif create_home:
             cmd.append('-m') # Créer le home par défaut
             self.log_info("  - Créera le répertoire personnel par défaut.")
        else:
             cmd.append('-M') # Ne pas créer le home par défaut
             self.log_info("  - Ne créera pas le répertoire personnel par défaut.")

        if shell: cmd.extend(['-s', shell])
        if no_user_group: cmd.append('-n')
        if no_log_init: cmd.append('-l')

        # Gestion des groupes (primaire vs secondaire)
        # Note: -g définit le groupe principal initial, -G les groupes supplémentaires.
        # Si primary_group est fourni, il remplace l'option -g précédente si gid était aussi fourni.
        if primary_group:
            # Retirer l'option -g précédente si elle existe
            try: idx = cmd.index('-g'); cmd.pop(idx); cmd.pop(idx)
            except ValueError: pass
            cmd.extend(['-g', primary_group])
            self.log_info(f"  - Groupe principal: {primary_group}")

        if secondary_groups:
            cmd.extend(['-G', ','.join(secondary_groups)])
            self.log_info(f"  - Groupes secondaires: {', '.join(secondary_groups)}")

        # Mot de passe crypté (option -p de useradd)
        if encrypted_password:
             cmd.extend(['-p', encrypted_password])
             self.log_info("  - Mot de passe (crypté) fourni via useradd.")
             # Le mot de passe en clair sera ignoré si un crypté est fourni
             password = None

        cmd.append(username)

        # Exécuter useradd
        success, stdout, stderr = self.run(cmd, check=False)

        if not success:
            self.log_error(f"Échec de la commande useradd pour '{username}'. Stderr: {stderr}")
            return False

        self.log_success(f"Utilisateur '{username}' ajouté avec succès.")

        # Définir le mot de passe en clair si fourni (après création)
        if password:
            return self.set_password(username, password)

        return True

    def delete_user(self, username: str, remove_home: bool = False) -> bool:
        """Supprime un utilisateur local."""
        if not self.user_exists(username):
            self.log_warning(f"L'utilisateur '{username}' n'existe pas, suppression ignorée.")
            return True # Considérer comme succès si déjà supprimé

        self.log_info(f"Suppression de l'utilisateur: {username}{' (avec répertoire personnel)' if remove_home else ''}")
        cmd = ['userdel']
        if remove_home:
            cmd.append('-r')
        cmd.append(username)

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            self.log_success(f"Utilisateur '{username}' supprimé avec succès.")
            return True
        else:
            self.log_error(f"Échec de la suppression de l'utilisateur '{username}'. Stderr: {stderr}")
            return False

    def modify_user(self,
                    username: str,
                    new_username: Optional[str] = None,
                    uid: Optional[int] = None,
                    gid: Optional[Union[int, str]] = None, # Nouveau groupe principal
                    gecos: Optional[str] = None,
                    home_dir: Optional[str] = None,
                    move_home: bool = False, # Utiliser avec home_dir
                    shell: Optional[str] = None,
                    append_groups: Optional[List[str]] = None, # Ajouter aux groupes secondaires (-a -G)
                    set_groups: Optional[List[str]] = None, # Remplacer les groupes secondaires (-G)
                    lock: bool = False,
                    unlock: bool = False,
                    expire_date: Optional[str] = None # YYYY-MM-DD
                    ) -> bool:
        """Modifie un utilisateur existant."""
        if not self.user_exists(username):
            self.log_error(f"L'utilisateur '{username}' n'existe pas, modification impossible.")
            return False

        self.log_info(f"Modification de l'utilisateur: {username}")
        cmd = ['usermod']
        options_added = False

        if new_username: cmd.extend(['-l', new_username]); options_added = True; self.log_info(f"  - Nouveau nom: {new_username}")
        if uid is not None: cmd.extend(['-u', str(uid)]); options_added = True; self.log_info(f"  - Nouvel UID: {uid}")
        if gid is not None: cmd.extend(['-g', str(gid)]); options_added = True; self.log_info(f"  - Nouveau GID/Groupe principal: {gid}")
        if gecos: cmd.extend(['-c', gecos]); options_added = True; self.log_info(f"  - Nouveau GECOS: {gecos}")
        if home_dir:
             cmd.extend(['-d', home_dir])
             if move_home: cmd.append('-m')
             options_added = True
             self.log_info(f"  - Nouveau Home: {home_dir} (déplacer: {move_home})")
        if shell: cmd.extend(['-s', shell]); options_added = True; self.log_info(f"  - Nouveau Shell: {shell}")
        if append_groups: cmd.extend(['-a', '-G', ','.join(append_groups)]); options_added = True; self.log_info(f"  - Ajout aux groupes: {', '.join(append_groups)}")
        if set_groups is not None: # Permet de définir une liste vide
             cmd.extend(['-G', ','.join(set_groups)]); options_added = True; self.log_info(f"  - Définition des groupes: {', '.join(set_groups)}")
        if lock: cmd.append('-L'); options_added = True; self.log_info("  - Verrouillage du compte")
        if unlock: cmd.append('-U'); options_added = True; self.log_info("  - Déverrouillage du compte")
        if expire_date: cmd.extend(['-e', expire_date]); options_added = True; self.log_info(f"  - Date d'expiration: {expire_date}")

        if not options_added:
            self.log_warning("Aucune modification spécifiée pour usermod.")
            return True # Aucune action à faire = succès

        cmd.append(username) # L'utilisateur à modifier

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            self.log_success(f"Utilisateur '{username}' modifié avec succès.")
            return True
        else:
            self.log_error(f"Échec de la modification de l'utilisateur '{username}'. Stderr: {stderr}")
            return False

    def set_password(self, username: str, password: str, is_encrypted: bool = False) -> bool:
        """Définit ou met à jour le mot de passe d'un utilisateur via chpasswd."""
        if not self.user_exists(username):
            self.log_error(f"L'utilisateur '{username}' n'existe pas, impossible de définir le mot de passe.")
            return False

        self.log_info(f"Définition/Mise à jour du mot de passe pour: {username}")
        cmd = ['chpasswd']
        if is_encrypted:
            cmd.append('-e')
            self.log_info("  - Utilisation d'un mot de passe déjà crypté.")

        # chpasswd lit depuis stdin au format "username:password"
        input_str = f"{username}:{password}\n"

        success, stdout, stderr = self.run(cmd, input_data=input_str, check=False)
        if success:
            self.log_success(f"Mot de passe pour '{username}' mis à jour avec succès.")
            return True
        else:
            self.log_error(f"Échec de la mise à jour du mot de passe pour '{username}'. Stderr: {stderr}")
            return False

    # --- Gestion des Groupes ---

    def add_group(self, groupname: str, gid: Optional[int] = None, system: bool = False) -> bool:
        """Ajoute un nouveau groupe local."""
        if self.group_exists(groupname):
            self.log_error(f"Le groupe '{groupname}' existe déjà.")
            return False

        self.log_info(f"Ajout du groupe: {groupname}")
        cmd = ['groupadd']
        if system: cmd.append('-r')
        if gid is not None: cmd.extend(['-g', str(gid)])
        cmd.append(groupname)

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            self.log_success(f"Groupe '{groupname}' ajouté avec succès.")
            return True
        else:
            self.log_error(f"Échec de l'ajout du groupe '{groupname}'. Stderr: {stderr}")
            return False

    def delete_group(self, groupname: str) -> bool:
        """Supprime un groupe local."""
        if not self.group_exists(groupname):
            self.log_warning(f"Le groupe '{groupname}' n'existe pas, suppression ignorée.")
            return True

        self.log_info(f"Suppression du groupe: {groupname}")
        cmd = ['groupdel', groupname]

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            self.log_success(f"Groupe '{groupname}' supprimé avec succès.")
            return True
        else:
            self.log_error(f"Échec de la suppression du groupe '{groupname}'. Stderr: {stderr}")
            return False

    def modify_group(self, groupname: str, new_name: Optional[str] = None, new_gid: Optional[int] = None) -> bool:
        """Modifie un groupe existant (nom ou GID)."""
        if not self.group_exists(groupname):
            self.log_error(f"Le groupe '{groupname}' n'existe pas, modification impossible.")
            return False

        self.log_info(f"Modification du groupe: {groupname}")
        cmd = ['groupmod']
        options_added = False

        if new_name: cmd.extend(['-n', new_name]); options_added = True; self.log_info(f"  - Nouveau nom: {new_name}")
        if new_gid is not None: cmd.extend(['-g', str(new_gid)]); options_added = True; self.log_info(f"  - Nouveau GID: {new_gid}")

        if not options_added:
            self.log_warning("Aucune modification spécifiée pour groupmod.")
            return True

        cmd.append(groupname) # Le groupe à modifier

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            self.log_success(f"Groupe '{groupname}' modifié avec succès.")
            return True
        else:
            self.log_error(f"Échec de la modification du groupe '{groupname}'. Stderr: {stderr}")
            return False

    def add_user_to_group(self, username: str, groupname: str) -> bool:
        """Ajoute un utilisateur à un groupe secondaire."""
        if not self.user_exists(username):
            self.log_error(f"L'utilisateur '{username}' n'existe pas.")
            return False
        if not self.group_exists(groupname):
            self.log_error(f"Le groupe '{groupname}' n'existe pas.")
            return False

        self.log_info(f"Ajout de l'utilisateur '{username}' au groupe '{groupname}'")
        # Utiliser gpasswd est généralement plus sûr que usermod -a -G
        cmd = ['gpasswd', '-a', username, groupname]

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            # gpasswd peut afficher un message même en cas de succès
            if stdout: self.log_info(f"Sortie gpasswd: {stdout.strip()}")
            self.log_success(f"Utilisateur '{username}' ajouté au groupe '{groupname}'.")
            return True
        else:
             # Vérifier si l'utilisateur est déjà membre
             if "is already a member of group" in stderr:
                  self.log_info(f"L'utilisateur '{username}' est déjà membre du groupe '{groupname}'.")
                  return True
             self.log_error(f"Échec de l'ajout de '{username}' au groupe '{groupname}'. Stderr: {stderr}")
             return False

    def remove_user_from_group(self, username: str, groupname: str) -> bool:
        """Retire un utilisateur d'un groupe secondaire."""
        if not self.user_exists(username):
            self.log_warning(f"L'utilisateur '{username}' n'existe pas, retrait ignoré.")
            return True
        if not self.group_exists(groupname):
            self.log_warning(f"Le groupe '{groupname}' n'existe pas, retrait ignoré.")
            return True

        self.log_info(f"Retrait de l'utilisateur '{username}' du groupe '{groupname}'")
        cmd = ['gpasswd', '-d', username, groupname]

        success, stdout, stderr = self.run(cmd, check=False)
        if success:
            if stdout: self.log_info(f"Sortie gpasswd: {stdout.strip()}")
            self.log_success(f"Utilisateur '{username}' retiré du groupe '{groupname}'.")
            return True
        else:
             # Vérifier si l'utilisateur n'était pas membre
             if "is not a member of group" in stderr:
                  self.log_info(f"L'utilisateur '{username}' n'était pas membre du groupe '{groupname}'.")
                  return True
             self.log_error(f"Échec du retrait de '{username}' du groupe '{groupname}'. Stderr: {stderr}")
             return False

    # --- Fonctions d'Information ---

    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un utilisateur via getent."""
        self.log_debug(f"Récupération des informations pour l'utilisateur: {username}")
        success, stdout, _ = self.run(['getent', 'passwd', username], check=False, no_output=True)
        if not success:
            self.log_debug(f"Utilisateur '{username}' non trouvé par getent.")
            return None

        # Format passwd: name:password:UID:GID:GECOS:home:shell
        fields = ['username', 'password_placeholder', 'uid', 'gid', 'gecos', 'home_dir', 'shell']
        values = stdout.strip().split(':')
        if len(values) == len(fields):
            info = dict(zip(fields, values))
            # Convertir UID/GID en int
            try: info['uid'] = int(info['uid'])
            except ValueError: pass
            try: info['gid'] = int(info['gid'])
            except ValueError: pass
            return info
        else:
            self.log_warning(f"Format de sortie inattendu de getent passwd pour '{username}': {stdout}")
            return None

    def get_group_info(self, groupname: str) -> Optional[Dict[str, Any]]:
        """Récupère les informations d'un groupe via getent."""
        self.log_debug(f"Récupération des informations pour le groupe: {groupname}")
        success, stdout, _ = self.run(['getent', 'group', groupname], check=False, no_output=True)
        if not success:
            self.log_debug(f"Groupe '{groupname}' non trouvé par getent.")
            return None

        # Format group: name:password:GID:members
        fields = ['groupname', 'password_placeholder', 'gid', 'members']
        values = stdout.strip().split(':')
        if len(values) == len(fields):
            info = dict(zip(fields, values))
            try: info['gid'] = int(info['gid'])
            except ValueError: pass
            info['members'] = info['members'].split(',') if info['members'] else []
            return info
        else:
            self.log_warning(f"Format de sortie inattendu de getent group pour '{groupname}': {stdout}")
            return None

    def get_user_groups(self, username: str) -> Optional[List[str]]:
        """Récupère la liste des groupes auxquels un utilisateur appartient."""
        if not self.user_exists(username):
            self.log_error(f"L'utilisateur '{username}' n'existe pas.")
            return None

        self.log_debug(f"Récupération des groupes pour l'utilisateur: {username}")
        # La commande 'groups' est simple et fiable
        success, stdout, stderr = self.run(['groups', username], check=False, no_output=True)
        if not success:
            self.log_error(f"Impossible de récupérer les groupes pour '{username}'. Stderr: {stderr}")
            return None

        # Format: username : group1 group2 ...
        try:
            groups_str = stdout.split(':', 1)[1].strip()
            groups = groups_str.split()
            self.log_debug(f"Groupes pour '{username}': {groups}")
            return groups
        except IndexError:
            self.log_warning(f"Format de sortie inattendu de la commande 'groups' pour '{username}': {stdout}")
            return [] # Retourner liste vide si format inattendu

