#!/usr/bin/env python3
"""
Module utilitaire pour manipuler les fichiers de configuration Dovecot.
Hérite de ConfigFileCommands pour réutiliser les fonctionnalités de gestion de fichiers.
Implémente un modèle cohérent "lire, modifier, écrire" pour les configurations Dovecot.
"""

from plugins_utils.config_files import ConfigFileCommands
from pathlib import Path
import os
from typing import Union, Optional, Dict, Any, List, Tuple
import re

class DovecotCommands(ConfigFileCommands):
    """
    Classe pour manipuler les fichiers de configuration Dovecot.
    Hérite de ConfigFileCommands pour réutiliser les fonctionnalités de gestion de fichiers.
    Permet une manipulation cohérente des configurations avec le modèle "lire, modifier, écrire".
    """

    # Chemins par défaut pour les fichiers de configuration
    DEFAULT_CONFIG_PATHS = {
        'main': '/etc/dovecot/dovecot.conf',
        'mail': '/etc/dovecot/conf.d/10-mail.conf',
        'auth': '/etc/dovecot/conf.d/10-auth.conf',
        'master': '/etc/dovecot/conf.d/10-master.conf',
        'ssl': '/etc/dovecot/conf.d/10-ssl.conf',
        'quota': '/etc/dovecot/conf.d/90-quota.conf',
        'acl': '/etc/dovecot/dovecot-acl',
        'sieve': '/etc/dovecot/conf.d/90-sieve.conf',
    }

    def __init__(self, logger=None, target_ip=None, config_dir='/etc/dovecot'):
        """
        Initialise le gestionnaire de fichiers de configuration Dovecot.

        Args:
            logger: Logger à utiliser
            target_ip: IP cible (pour les opérations à distance)
            config_dir: Répertoire de base des configurations Dovecot
        """
        super().__init__(logger, target_ip)
        self.config_dir = Path(config_dir)
        self.loaded_configs = {}  # Cache pour les configurations chargées

    def get_config_path(self, config_type: str) -> Path:
        """
        Obtient le chemin complet d'un fichier de configuration spécifique.

        Args:
            config_type: Type de configuration ('main', 'mail', 'auth', etc.)

        Returns:
            Path: Chemin complet du fichier de configuration
        """
        if config_type in self.DEFAULT_CONFIG_PATHS:
            return Path(self.DEFAULT_CONFIG_PATHS[config_type])

        # Si c'est un chemin direct ou un fichier spécifique dans conf.d
        if os.path.sep in config_type:
            return Path(config_type)

        # Chercher dans conf.d
        return self.config_dir / 'conf.d' / config_type

    def read_config(self, config_type: str, force_reload: bool = False) -> Optional[Dict]:
        """
        Lit un fichier de configuration Dovecot.
        Utilise un cache pour éviter de relire les fichiers inutilement.

        Args:
            config_type: Type de configuration ('main', 'mail', 'auth', etc.) ou chemin
            force_reload: Si True, force la relecture même si déjà en cache

        Returns:
            dict: Structure de configuration parsée ou None en cas d'erreur
        """
        config_path = self.get_config_path(config_type)

        # Utiliser le cache sauf si force_reload est True
        if not force_reload and str(config_path) in self.loaded_configs:
            self.log_debug(f"Utilisation de la configuration en cache pour {config_path}")
            return self.loaded_configs[str(config_path)]

        self.log_debug(f"Lecture de la configuration Dovecot: {config_path}")
        with open(config_path,"r+") as fd:
            config_content=fd.read()
        config = self._parse_dovecot_config(config_content)

        if config is not None:
            # Mettre en cache
            self.loaded_configs[str(config_path)] = config

        return config


    def _parse_dovecot_config(self, content: str) -> dict:
        """
        Parse un fichier de configuration Dovecot en utilisant une approche lexicale
        et une structure de données arborescente.

        Args:
            content: Contenu du fichier à parser

        Returns:
            dict: Structure hiérarchique représentant la configuration
        """

        self.log_debug("Parsing d'un fichier de configuration Dovecot (refonte)")

        config = {}
        stack = [config]  # Pile pour suivre les dictionnaires imbriqués
        namespace_pattern = re.compile(r'namespace\s+(\S+)\s*{')
        assignment_pattern = re.compile(r'(\S+)\s*=\s*(.+?)(?:$|;|\s+#)', re.DOTALL)
        block_start_pattern = re.compile(r'(\S+)\s*{')
        block_end_pattern = re.compile(r'}')

        lines = content.splitlines()
        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            if not line or line.startswith('#'):
                continue

            # Fin de bloc
            if block_end_pattern.match(line):
                if len(stack) > 1:
                    stack.pop()
                continue

            # Début de namespace
            namespace_match = namespace_pattern.match(line)
            if namespace_match:
                namespace_name = namespace_match.group(1)
                current_dict = stack[-1]
                current_dict.setdefault('namespace', {}).setdefault(namespace_name, {})
                stack.append(current_dict['namespace'][namespace_name])
                continue

            # Début de bloc
            block_match = block_start_pattern.match(line)
            if block_match:
                block_name = block_match.group(1)
                current_dict = stack[-1]
                current_dict[block_name] = {}
                stack.append(current_dict[block_name])
                continue

            # Assignation
            assignment_match = assignment_pattern.match(line)
            if assignment_match:
                key, value = assignment_match.groups()
                current_dict = stack[-1]
                current_dict[key.strip()] = value.strip()
                continue

            # Autre (ligne non reconnue)
            self.log_warning(f"Ligne non reconnue à la ligne {line_num}: {line}")

        return config


    def _parse_block_content(self, content: List[str]) -> dict:
        """
        Parse le contenu d'un bloc (namespace ou autre).

        Args:
            content: Liste des lignes de contenu du bloc

        Returns:
            dict: Dictionnaire représentant le contenu du bloc
        """
        block_dict = {}
        assignment_pattern = re.compile(r'(\S+)\s*=\s*(.+?)(?:$|;|\s+#)', re.DOTALL)

        for content_line in content:
            content_line = content_line.strip()
            if not content_line or content_line.startswith('#'):
                continue

            match = assignment_pattern.match(content_line)
            if match:
                key, value = match.groups()
                block_dict[key.strip()] = value.strip()

        return block_dict


    def write_config(self, config_type: str, config: Dict, backup: bool = True) -> bool:
        """
        Écrit une structure de configuration Dovecot dans un fichier.
        Met également à jour le cache.

        Args:
            config_type: Type de configuration ('main', 'mail', 'auth', etc.) ou chemin
            config: Structure de configuration à écrire
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'écriture réussit, False sinon
        """
        config_path = self.get_config_path(config_type)
        self.log_debug(f"Écriture de la configuration Dovecot: {config_path}")

        success = self.write_block_config_file(config_path, config, backup=backup)

        if success:
            # Mettre à jour le cache
            self.loaded_configs[str(config_path)] = config
            self.log_success(f"Configuration Dovecot {config_path} mise à jour avec succès")
        else:
            self.log_error(f"Échec de l'écriture de la configuration Dovecot {config_path}")

        return success

    def clear_cache(self, config_type: Optional[str] = None) -> None:
        """
        Vide le cache de configurations.

        Args:
            config_type: Type de configuration spécifique à vider, ou None pour tout vider
        """
        if config_type is None:
            self.loaded_configs = {}
            self.log_debug("Cache de configurations vidé")
        else:
            config_path = str(self.get_config_path(config_type))
            if config_path in self.loaded_configs:
                del self.loaded_configs[config_path]
                self.log_debug(f"Cache vidé pour {config_path}")

    def get_global_setting(self, setting_name: str, default: Any = None) -> Any:
        """
        Récupère un paramètre global dans la configuration principale.

        Args:
            setting_name: Nom du paramètre à récupérer
            default: Valeur par défaut si le paramètre n'existe pas

        Returns:
            Any: Valeur du paramètre ou valeur par défaut
        """
        config = self.read_config('main')
        if config is None:
            return default

        return config.get(setting_name, default)

    def set_global_setting(self, setting_name: str, value: Any, backup: bool = True) -> bool:
        """
        Définit un paramètre global dans la configuration principale.

        Args:
            setting_name: Nom du paramètre à définir
            value: Nouvelle valeur du paramètre
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        config = self.read_config('main')
        if config is None:
            self.log_error("Impossible de lire la configuration principale")
            return False

        # Mettre à jour le paramètre
        config[setting_name] = value

        # Écrire la configuration mise à jour
        return self.write_config('main', config, backup=backup)

    def get_mail_setting(self, setting_name: str, default: Any = None) -> Any:
        """
        Récupère un paramètre dans la configuration mail.

        Args:
            setting_name: Nom du paramètre à récupérer
            default: Valeur par défaut si le paramètre n'existe pas

        Returns:
            Any: Valeur du paramètre ou valeur par défaut
        """
        config = self.read_config('mail')
        if config is None:
            return default

        return config.get(setting_name, default)

    def set_mail_setting(self, setting_name: str, value: Any, backup: bool = True) -> bool:
        """
        Définit un paramètre dans la configuration mail.

        Args:
            setting_name: Nom du paramètre à définir
            value: Nouvelle valeur du paramètre
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        config = self.read_config('mail')
        if config is None:
            self.log_error("Impossible de lire la configuration mail")
            return False

        # Mettre à jour le paramètre
        config[setting_name] = value

        # Écrire la configuration mise à jour
        return self.write_config('mail', config, backup=backup)

    def get_mail_plugins(self) -> List[str]:
        """
        Récupère la liste des plugins mail activés.

        Returns:
            List[str]: Liste des plugins activés
        """
        plugins_str = self.get_mail_setting('mail_plugins', '')
        if not plugins_str:
            return []

        return [p.strip() for p in str(plugins_str).split()]

    def set_mail_plugins(self, plugins: List[str], backup: bool = True) -> bool:
        """
        Définit la liste des plugins mail activés.

        Args:
            plugins: Liste des plugins à activer
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        plugins_str = ' '.join(plugins)
        return self.set_mail_setting('mail_plugins', plugins_str, backup=backup)

    def add_mail_plugin(self, plugin_name: str, backup: bool = True) -> bool:
        """
        Ajoute un plugin mail s'il n'est pas déjà activé.

        Args:
            plugin_name: Nom du plugin à ajouter
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        plugins = self.get_mail_plugins()
        if plugin_name in plugins:
            self.log_debug(f"Le plugin {plugin_name} est déjà activé")
            return True

        plugins.append(plugin_name)
        return self.set_mail_plugins(plugins, backup=backup)

    def remove_mail_plugin(self, plugin_name: str, backup: bool = True) -> bool:
        """
        Supprime un plugin mail s'il est activé.

        Args:
            plugin_name: Nom du plugin à supprimer
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        plugins = self.get_mail_plugins()
        if plugin_name not in plugins:
            self.log_debug(f"Le plugin {plugin_name} n'est pas activé")
            return True

        plugins.remove(plugin_name)
        return self.set_mail_plugins(plugins, backup=backup)

    def get_plugin_setting(self, plugin_type: str, setting_name: str, default: Any = None) -> Any:
        """
        Récupère un paramètre dans la configuration d'un plugin.

        Args:
            plugin_type: Type de plugin ('quota', 'acl', 'sieve', etc.)
            setting_name: Nom du paramètre à récupérer
            default: Valeur par défaut si le paramètre n'existe pas

        Returns:
            Any: Valeur du paramètre ou valeur par défaut
        """
        config = self.read_config(plugin_type)
        if config is None:
            return default

        plugin_settings = config.get('plugin', {})
        return plugin_settings.get(setting_name, default)

    def set_plugin_setting(self, plugin_type: str, setting_name: str, value: Any, backup: bool = True) -> bool:
        """
        Définit un paramètre dans la configuration d'un plugin.

        Args:
            plugin_type: Type de plugin ('quota', 'acl', 'sieve', etc.)
            setting_name: Nom du paramètre à définir
            value: Nouvelle valeur du paramètre
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        config = self.read_config(plugin_type)
        if config is None:
            self.log_error(f"Impossible de lire la configuration du plugin {plugin_type}")
            return False

        # Créer la section 'plugin' si elle n'existe pas
        if 'plugin' not in config:
            config['plugin'] = {}

        # Mettre à jour le paramètre
        config['plugin'][setting_name] = value

        # Écrire la configuration mise à jour
        return self.write_config(plugin_type, config, backup=backup)

    def get_service_setting(self, service_name: str, setting_path: str, default: Any = None) -> Any:
        """
        Récupère un paramètre d'un service dans la configuration master.

        Args:
            service_name: Nom du service ('imap', 'pop3', 'auth', etc.)
            setting_path: Chemin du paramètre (ex: 'inet_listener imap/port')
            default: Valeur par défaut si le paramètre n'existe pas

        Returns:
            Any: Valeur du paramètre ou valeur par défaut
        """
        config = self.read_config('master')
        if config is None:
            return default

        # Vérifier si le service existe
        service_key = f"service {service_name}"
        if service_key not in config:
            return default

        # Naviguer dans le chemin du paramètre
        current = config[service_key]
        path_parts = setting_path.split('/')

        for part in path_parts[:-1]:  # Tous sauf le dernier
            if part not in current:
                return default
            current = current[part]

        # Récupérer le paramètre final
        last_part = path_parts[-1]
        return current.get(last_part, default)

    def set_service_setting(self, service_name: str, setting_path: str, value: Any, backup: bool = True) -> bool:
        """
        Définit un paramètre d'un service dans la configuration master.

        Args:
            service_name: Nom du service ('imap', 'pop3', 'auth', etc.)
            setting_path: Chemin du paramètre (ex: 'inet_listener imap/port')
            value: Nouvelle valeur du paramètre
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        config = self.read_config('master')
        if config is None:
            self.log_error("Impossible de lire la configuration master")
            return False

        # Créer le service s'il n'existe pas
        service_key = f"service {service_name}"
        if service_key not in config:
            config[service_key] = {}

        # Naviguer et créer le chemin du paramètre
        current = config[service_key]
        path_parts = setting_path.split('/')

        for part in path_parts[:-1]:  # Tous sauf le dernier
            if part not in current:
                current[part] = {}
            current = current[part]

        # Définir le paramètre final
        last_part = path_parts[-1]
        current[last_part] = value

        # Écrire la configuration mise à jour
        return self.write_config('master', config, backup=backup)

    def get_quota_rule(self, rule_name: str = 'quota_rule', default: Any = None) -> Any:
        """
        Récupère une règle de quota.

        Args:
            rule_name: Nom de la règle ('quota_rule', 'quota_rule2', etc.)
            default: Valeur par défaut si la règle n'existe pas

        Returns:
            Any: Valeur de la règle ou valeur par défaut
        """
        return self.get_plugin_setting('quota', rule_name, default)

    def set_quota_rule(self, rule_value: str, rule_name: str = 'quota_rule', backup: bool = True) -> bool:
        """
        Définit une règle de quota.

        Args:
            rule_value: Valeur de la règle (ex: '*:storage=1G')
            rule_name: Nom de la règle ('quota_rule', 'quota_rule2', etc.)
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        return self.set_plugin_setting('quota', rule_name, rule_value, backup=backup)

    def enable_quota(self, backup: bool = True) -> bool:
        """
        Active le plugin de quota.

        Args:
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'activation réussit, False sinon
        """
        return self.add_mail_plugin('quota', backup=backup)

    # Méthodes pour manipuler les namespaces

    def list_namespaces(self, config_path: Optional[str] = None) -> Dict[str, Dict]:
        """
        Liste tous les namespaces dans un fichier de configuration.

        Args:
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut

        Returns:
            dict: Dictionnaire {nom_namespace: config_namespace}
        """
        if config_path is None:
            config = self.read_config('mail')
        else:
            config = self.read_config(config_path)

        if not config:
            self.log_error(f"Impossible de lire la configuration pour lister les namespaces")
            return {}

        namespaces = {}
        for key, value in config.items():
            if key.startswith("namespace "):
                namespace_name = key.split(" ", 1)[1]
                namespaces[namespace_name] = value

        return namespaces

    def get_namespace(self, namespace_name: str, config_path: Optional[str] = None) -> Optional[Dict]:
        """
        Récupère la configuration d'un namespace spécifique.

        Args:
            namespace_name: Nom du namespace à récupérer
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut

        Returns:
            dict: Configuration du namespace ou None s'il n'existe pas
        """
        if config_path is None:
            config = self.read_config('mail')
        else:
            config = self.read_config(config_path)

        if not config:
            self.log_error(f"Impossible de lire la configuration pour récupérer le namespace {namespace_name}")
            return None

        namespace_key = f"namespace {namespace_name}"
        return config.get(namespace_key)

    def add_namespace(self, namespace_name: str, namespace_config: Dict, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Ajoute un nouveau namespace à la configuration.

        Args:
            namespace_name: Nom du namespace à ajouter (sans le préfixe "namespace ")
            namespace_config: Dictionnaire de configuration du namespace
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'ajout réussit, False sinon
        """
        if config_path is None:
            config = self.read_config('mail')
            config_type = 'mail'
        else:
            config = self.read_config(config_path)
            config_type = config_path

        if not config:
            self.log_error(f"Impossible de lire la configuration pour ajouter le namespace {namespace_name}")
            return False

        namespace_key = f"namespace {namespace_name}"

        # Vérifier si le namespace existe déjà
        if namespace_key in config:
            self.log_warning(f"Le namespace '{namespace_name}' existe déjà")
            return False

        # Ajouter le nouveau namespace
        config[namespace_key] = namespace_config

        # Écrire la configuration mise à jour
        return self.write_config(config_type, config, backup=backup)

    def update_namespace(self, namespace_name: str, updated_config: Dict, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Met à jour un namespace existant.

        Args:
            namespace_name: Nom du namespace à mettre à jour (sans le préfixe "namespace ")
            updated_config: Dictionnaire de configuration mis à jour
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        if config_path is None:
            config = self.read_config('mail')
            config_type = 'mail'
        else:
            config = self.read_config(config_path)
            config_type = config_path

        if not config:
            self.log_error(f"Impossible de lire la configuration pour mettre à jour le namespace {namespace_name}")
            return False

        namespace_key = f"namespace {namespace_name}"

        # Vérifier si le namespace existe
        if namespace_key not in config:
            self.log_warning(f"Le namespace '{namespace_name}' n'existe pas")
            return False

        # Mettre à jour le namespace
        config[namespace_key] = updated_config

        # Écrire la configuration mise à jour
        return self.write_config(config_type, config, backup=backup)

    def delete_namespace(self, namespace_name: str, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Supprime un namespace existant.

        Args:
            namespace_name: Nom du namespace à supprimer (sans le préfixe "namespace ")
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la suppression réussit, False sinon
        """
        if config_path is None:
            config = self.read_config('mail')
            config_type = 'mail'
        else:
            config = self.read_config(config_path)
            config_type = config_path

        if not config:
            self.log_error(f"Impossible de lire la configuration pour supprimer le namespace {namespace_name}")
            return False

        namespace_key = f"namespace {namespace_name}"

        # Vérifier si le namespace existe
        if namespace_key not in config:
            self.log_warning(f"Le namespace '{namespace_name}' n'existe pas")
            return False

        # Supprimer le namespace
        del config[namespace_key]

        # Écrire la configuration mise à jour
        return self.write_config(config_type, config, backup=backup)

    def uncomment_namespace(self, namespace_pattern: str, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Décommente un namespace commenté.
        Cette méthode manipule directement le contenu du fichier plutôt que la structure parsée.

        Args:
            namespace_pattern: Motif pour identifier le namespace (ex: "PUBLIC_FINANCE")
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si le décommentage réussit, False sinon
        """
        if config_path is None:
            config_path = self.get_config_path('mail')
        else:
            config_path = self.get_config_path(config_path)

        # Lire le contenu du fichier
        success_read, content, stderr_read = self.run(['cat', str(config_path)],
                                                    check=False, needs_sudo=True,
                                                    no_output=True, error_as_warning=True)
        if not success_read:
            self.log_error(f"Impossible de lire le fichier {config_path}. Stderr: {stderr_read}")
            return False

        # Identifier le début du namespace commenté
        import re
        pattern = rf"^#namespace\s+{namespace_pattern}\s*\{{"

        # Rechercher le bloc de namespace commenté
        lines = content.splitlines()
        new_lines = []
        in_commented_namespace = False
        namespace_found = False

        for line in lines:
            # Détecter le début du namespace commenté
            if not in_commented_namespace and re.match(pattern, line.strip()):
                in_commented_namespace = True
                namespace_found = True
                # Décommenter la ligne de début
                new_lines.append(line.replace('#', '', 1))
                continue

            # Décommenter les lignes dans le namespace
            if in_commented_namespace:
                # Détecter la fin du bloc commenté
                stripped = line.strip()
                if stripped == '#}':
                    in_commented_namespace = False
                    new_lines.append(line.replace('#', '', 1))
                    continue

                # Si la ligne est commentée, la décommenter
                if stripped.startswith('#'):
                    new_lines.append(line.replace('#', '', 1))
                else:
                    # Ligne déjà non commentée à l'intérieur du bloc
                    new_lines.append(line)
            else:
                # Lignes en dehors du namespace commenté
                new_lines.append(line)

        if not namespace_found:
            self.log_warning(f"Namespace '{namespace_pattern}' commenté non trouvé dans {config_path}")
            return False

        # Écrire le contenu mis à jour
        new_content = '\n'.join(new_lines)
        success = self._write_file_content(config_path, new_content, backup=backup)

        # Vider le cache pour ce fichier
        if success:
            self.clear_cache(str(config_path))

        return success

    def comment_namespace(self, namespace_name: str, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Commente un namespace existant.
        Cette méthode manipule directement le contenu du fichier plutôt que la structure parsée.

        Args:
            namespace_name: Nom du namespace à commenter (ex: "PUBLIC_FINANCE")
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si le commentage réussit, False sinon
        """
        if config_path is None:
            config_path = self.get_config_path('mail')
        else:
            config_path = self.get_config_path(config_path)

        # Lire le contenu du fichier
        success_read, content, stderr_read = self.run(['cat', str(config_path)],
                                                    check=False, needs_sudo=True,
                                                    no_output=True, error_as_warning=True)
        if not success_read:
            self.log_error(f"Impossible de lire le fichier {config_path}. Stderr: {stderr_read}")
            return False

        # Identifier le début du namespace
        import re
        pattern = rf"^namespace\s+{namespace_name}\s*\{{"

        # Rechercher le bloc de namespace
        lines = content.splitlines()
        new_lines = []
        in_namespace = False
        namespace_found = False

        for line in lines:
            # Détecter le début du namespace
            if not in_namespace and re.match(pattern, line.strip()):
                in_namespace = True
                namespace_found = True
                # Commenter la ligne de début
                new_lines.append('#' + line)
                continue

            # Commenter les lignes dans le namespace
            if in_namespace:
                # Détecter la fin du bloc
                if line.strip() == '}':
                    in_namespace = False
                    new_lines.append('#' + line)
                    continue

                # Commenter la ligne
                new_lines.append('#' + line)
            else:
                # Lignes en dehors du namespace
                new_lines.append(line)

        if not namespace_found:
            self.log_warning(f"Namespace '{namespace_name}' non trouvé dans {config_path}")
            return False

        # Écrire le contenu mis à jour
        new_content = '\n'.join(new_lines)
        success = self._write_file_content(config_path, new_content, backup=backup)

        # Vider le cache pour ce fichier
        if success:
            self.clear_cache(str(config_path))

        return success

    def create_public_namespace(self, unite: str, location: Optional[str] = None, config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Crée un namespace public pour une unité spécifique.

        Args:
            unite: Nom de l'unité (ex: "FINANCE")
            location: Chemin de stockage (par défaut: "/partage/Mail_archive/{unite}")
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la création réussit, False sinon
        """
        if location is None:
            location = f"/partage/Mail_archive/{unite}"

        namespace_name = f"PUBLIC_{unite}"
        namespace_config = {
            "inbox": "no",
            "type": "public",
            "separator": "/",
            "prefix": f"Archives_{unite}/",
            "location": f"maildir:{location}",
            "subscriptions": "no",
            "list": "yes"
        }

        return self.add_namespace(namespace_name, namespace_config, config_path, backup=backup)

    def create_namespace_from_template(self, template_name: str, new_name: str,
                                       replacements: Dict[str, str], config_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Crée un nouveau namespace basé sur un template existant.

        Args:
            template_name: Nom du namespace template (avec ou sans le préfixe "namespace ")
            new_name: Nom du nouveau namespace (sans le préfixe "namespace ")
            replacements: Dictionnaire {pattern: replacement} pour les substitutions
            config_path: Chemin du fichier de configuration ou None pour utiliser le fichier mail par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la création réussit, False sinon
        """
        if config_path is None:
            config = self.read_config('mail')
            config_type = 'mail'
        else:
            config = self.read_config(config_path)
            config_type = config_path

        if config is None:
            self.log_error(f"Impossible de lire la configuration pour créer le namespace {new_name}")
            return False

        # Ajuster le nom du template si nécessaire
        if not template_name.startswith("namespace "):
            template_key = f"namespace {template_name}"
        else:
            template_key = template_name

        # Vérifier si le template existe
        if template_key not in config:
            self.log_error(f"Le namespace template '{template_name}' n'existe pas")
            return False

        # Cloner la configuration du template
        template_config = config[template_key]
        new_config = dict(template_config)

        # Appliquer les remplacements
        import json
        config_str = json.dumps(new_config)
        for pattern, replacement in replacements.items():
            config_str = config_str.replace(pattern, replacement)
        new_config = json.loads(config_str)

        # Ajouter le nouveau namespace
        return self.add_namespace(new_name, new_config, config_type, backup=backup)

    # Méthodes pour la gestion des ACL

    def read_acl_file(self, acl_path: Optional[str] = None) -> List[Tuple[str, str, str, str]]:
        """
        Lit un fichier d'ACL Dovecot et retourne les règles sous forme de liste.
        Le format attendu est: mailbox identifier=user rights [#comment]

        Args:
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut

        Returns:
            List[Tuple[str, str, str, str]]: Liste de (mailbox, identifier, rights, comment)
        """
        if acl_path is None:
            acl_path = self.get_config_path('acl')
        else:
            acl_path = Path(acl_path)

        self.log_debug(f"Lecture du fichier ACL: {acl_path}")

        # Lire le contenu du fichier
        success_read, content, stderr_read = self.run(['cat', str(acl_path)],
                                                    check=False, needs_sudo=True,
                                                    no_output=True, error_as_warning=True)
        if not success_read:
            self.log_error(f"Impossible de lire le fichier ACL {acl_path}. Stderr: {stderr_read}")
            return []

        acl_entries = []

        for line in content.splitlines():
            line = line.strip()

            # Ignorer les lignes vides et les commentaires complets
            if not line or line.startswith('#'):
                continue

            # Extraire le commentaire éventuel
            comment = ""
            if '#' in line:
                line_parts = line.split('#', 1)
                line = line_parts[0].strip()
                comment = line_parts[1].strip()

            # Extraire les parties de la règle
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                self.log_warning(f"Format ACL invalide, ignoré: {line}")
                continue

            mailbox = parts[0]
            identifier = parts[1]
            rights = parts[2]

            acl_entries.append((mailbox, identifier, rights, comment))

        return acl_entries

    def write_acl_file(self, acl_entries: List[Tuple[str, str, str, str]], acl_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Écrit les règles ACL dans un fichier.

        Args:
            acl_entries: Liste de (mailbox, identifier, rights, comment)
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'écriture réussit, False sinon
        """
        if acl_path is None:
            acl_path = self.get_config_path('acl')
        else:
            acl_path = Path(acl_path)

        self.log_debug(f"Écriture du fichier ACL: {acl_path}")

        # Formater le contenu
        lines = []
        for entry in acl_entries:
            mailbox, identifier, rights, comment = entry
            line = f"{mailbox} {identifier} {rights}"
            if comment:
                line += f" #{comment}"
            lines.append(line)

        content = '\n'.join(lines) + '\n'

        # Écrire le fichier
        return self._write_file_content(acl_path, content, backup=backup)

    def get_acl_entries(self, mailbox: Optional[str] = None, acl_path: Optional[str] = None) -> List[Tuple[str, str, str, str]]:
        """
        Récupère les entrées ACL, éventuellement filtrées par boîte aux lettres.

        Args:
            mailbox: Nom de la boîte aux lettres pour filtrer ou None pour toutes
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut

        Returns:
            List[Tuple[str, str, str, str]]: Liste de (mailbox, identifier, rights, comment)
        """
        acl_entries = self.read_acl_file(acl_path)

        if mailbox is None:
            return acl_entries

        # Filtrer par boîte aux lettres
        return [entry for entry in acl_entries if entry[0] == mailbox]

    def add_acl_entry(self, mailbox: str, identifier: str, rights: str, comment: str = "",
                      acl_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Ajoute une entrée ACL.

        Args:
            mailbox: Nom de la boîte aux lettres (ex: "Archives_FINANCE")
            identifier: Identifiant (ex: "group=finance")
            rights: Droits d'accès (ex: "lrwts")
            comment: Commentaire optionnel
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'ajout réussit, False sinon
        """
        acl_entries = self.read_acl_file(acl_path)

        # Vérifier si l'entrée existe déjà
        for i, entry in enumerate(acl_entries):
            if entry[0] == mailbox and entry[1] == identifier:
                self.log_warning(f"L'entrée ACL pour {mailbox} {identifier} existe déjà, mise à jour")
                acl_entries[i] = (mailbox, identifier, rights, comment)
                return self.write_acl_file(acl_entries, acl_path, backup)

        # Ajouter la nouvelle entrée
        acl_entries.append((mailbox, identifier, rights, comment))
        return self.write_acl_file(acl_entries, acl_path, backup)

    def update_acl_entry(self, mailbox: str, identifier: str, rights: str, comment: Optional[str] = None,
                         acl_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Met à jour une entrée ACL existante.

        Args:
            mailbox: Nom de la boîte aux lettres (ex: "Archives_FINANCE")
            identifier: Identifiant (ex: "group=finance")
            rights: Nouveaux droits d'accès
            comment: Nouveau commentaire ou None pour conserver l'existant
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la mise à jour réussit, False sinon
        """
        acl_entries = self.read_acl_file(acl_path)

        # Rechercher l'entrée à mettre à jour
        entry_found = False
        for i, entry in enumerate(acl_entries):
            if entry[0] == mailbox and entry[1] == identifier:
                # Conserver le commentaire existant si aucun nouveau n'est spécifié
                current_comment = entry[3] if comment is None else comment
                acl_entries[i] = (mailbox, identifier, rights, current_comment)
                entry_found = True
                break

        if not entry_found:
            self.log_warning(f"L'entrée ACL pour {mailbox} {identifier} n'existe pas")
            return False

        return self.write_acl_file(acl_entries, acl_path, backup)

    def delete_acl_entry(self, mailbox: str, identifier: str, acl_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Supprime une entrée ACL.

        Args:
            mailbox: Nom de la boîte aux lettres
            identifier: Identifiant
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la suppression réussit, False sinon
        """
        acl_entries = self.read_acl_file(acl_path)

        # Filtrer l'entrée à supprimer
        new_entries = [entry for entry in acl_entries if not (entry[0] == mailbox and entry[1] == identifier)]

        if len(new_entries) == len(acl_entries):
            self.log_warning(f"L'entrée ACL pour {mailbox} {identifier} n'existe pas")
            return False

        return self.write_acl_file(new_entries, acl_path, backup)

    def delete_all_mailbox_acls(self, mailbox: str, acl_path: Optional[str] = None, backup: bool = True) -> bool:
        """
        Supprime toutes les entrées ACL pour une boîte aux lettres spécifique.

        Args:
            mailbox: Nom de la boîte aux lettres
            acl_path: Chemin du fichier ACL ou None pour utiliser l'emplacement par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la suppression réussit, False sinon
        """
        acl_entries = self.read_acl_file(acl_path)

        # Filtrer les entrées pour la boîte aux lettres
        new_entries = [entry for entry in acl_entries if entry[0] != mailbox]

        if len(new_entries) == len(acl_entries):
            self.log_warning(f"Aucune entrée ACL trouvée pour la boîte aux lettres {mailbox}")
            return False

        return self.write_acl_file(new_entries, acl_path, backup)

    def enable_acl_plugin(self, backup: bool = True) -> bool:
        """
        Active le plugin ACL.

        Args:
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si l'activation réussit, False sinon
        """
        return self.add_mail_plugin('acl', backup=backup)

    def configure_acl_settings(self, acl_dir: Optional[str] = None, backup: bool = True) -> bool:
        """
        Configure les paramètres du plugin ACL.

        Args:
            acl_dir: Répertoire pour les fichiers ACL ou None pour utiliser le répertoire par défaut
            backup: Si True, crée une sauvegarde du fichier original

        Returns:
            bool: True si la configuration réussit, False sinon
        """
        # Activer le plugin
        success = self.enable_acl_plugin(backup)
        if not success:
            return False

        # Définir le répertoire ACL
        if acl_dir:
            return self.set_plugin_setting('acl', 'acl_dir', acl_dir, backup)

        return True