"""
Gestionnaire central des configurations pour les plugins et les paramètres globaux.
"""

from ruamel.yaml import YAML
import os
from pathlib import Path
import json
import shutil
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Set, Tuple, Union, Callable
import traceback
import threading
import copy

from ..utils.logging import get_logger

logger = get_logger('config_manager')

class ConfigManager:
    """
    Gestionnaire centralisé pour les configurations de plugins et globales.
    
    Cette classe est responsable de:
    - Charger les configurations YAML
    - Fournir un accès unifié aux configurations
    - Valider les configurations selon des schémas
    - Gérer les sauvegardes et restauration des configurations
    - Surveiller les modifications de fichiers
    """

    def __init__(self, enable_backups: bool = True):
        """
        Initialise le gestionnaire de configurations.
        
        Args:
            enable_backups: Si True, active les sauvegardes automatiques
        """
        # Configurations chargées
        self.global_configs = {}  # {config_id: {config_data}}
        self.plugin_configs = {}  # {plugin_id: {config_data}}
        
        # Options de configuration
        self.enable_backups = enable_backups
        self.backup_count = 5
        self.auto_reload = False
        
        # Gestionnaire YAML avec préservation du formatage
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        
        # Cache pour éviter de recharger les fichiers
        self.config_cache = {}  # {chemin: (timestamp, config_data)}
        
        # Verrou pour les opérations thread-safe
        self._lock = threading.RLock()
        
        # Callbacks pour les notifications de changement
        self.change_callbacks = []
        
        logger.debug("ConfigManager initialisé")

    def register_change_callback(self, callback: Callable[[str, bool], None]) -> None:
        """
        Enregistre un callback à appeler quand une configuration change.
        
        Args:
            callback: Fonction appelée avec (config_id, is_global) comme arguments
        """
        with self._lock:
            if callback not in self.change_callbacks:
                self.change_callbacks.append(callback)
                logger.debug(f"Callback enregistré: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}")

    def unregister_change_callback(self, callback: Callable[[str, bool], None]) -> None:
        """
        Supprime un callback précédemment enregistré.
        
        Args:
            callback: Le callback à supprimer
        """
        with self._lock:
            if callback in self.change_callbacks:
                self.change_callbacks.remove(callback)
                logger.debug(f"Callback supprimé: {callback.__name__ if hasattr(callback, '__name__') else str(callback)}")

    def _notify_change(self, config_id: str, is_global: bool) -> None:
        """
        Notifie les callbacks enregistrés d'un changement de configuration.
        
        Args:
            config_id: Identifiant de la configuration modifiée
            is_global: Si True, c'est une configuration globale
        """
        with self._lock:
            callbacks = list(self.change_callbacks)
            
        for callback in callbacks:
            try:
                callback(config_id, is_global)
            except Exception as e:
                logger.error(f"Erreur dans le callback {callback.__name__ if hasattr(callback, '__name__') else str(callback)}: {e}")
                logger.error(traceback.format_exc())

    def load_global_config(self, config_id: str, config_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge une configuration globale depuis un fichier YAML.
        
        Args:
            config_id: Identifiant unique de la configuration
            config_path: Chemin vers le fichier de configuration
            
        Returns:
            Optional[Dict[str, Any]]: Configuration chargée ou None en cas d'erreur
        """
        return self._load_config(config_id, config_path, is_global=True)

    def load_plugin_config(self, plugin_id: str, settings_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge la configuration d'un plugin depuis un fichier settings.yml.
        
        Args:
            plugin_id: Identifiant du plugin
            settings_path: Chemin vers le fichier settings.yml
            
        Returns:
            Optional[Dict[str, Any]]: Configuration du plugin ou None en cas d'erreur
        """
        return self._load_config(plugin_id, settings_path, is_global=False)

    def _load_config(self, config_id: str, config_path: str, is_global: bool = False) -> Optional[Dict[str, Any]]:
        """
        Méthode générique pour charger une configuration.
        
        Args:
            config_id: Identifiant de la configuration
            config_path: Chemin du fichier de configuration
            is_global: Si True, charge une configuration globale
            
        Returns:
            Optional[Dict[str, Any]]: Configuration chargée ou None en cas d'erreur
        """
        with self._lock:
            # Vérifier si la configuration est déjà en cache
            cache_key = f"{'global' if is_global else 'plugin'}:{config_path}"
            
            # Vérifier si le fichier a été modifié depuis le dernier chargement
            try:
                path = Path(config_path)
                if not path.exists():
                    logger.error(f"Fichier de configuration inexistant: {config_path}")
                    return None
                    
                # Obtenir la date de dernière modification
                mod_time = path.stat().st_mtime
                
                # Si le fichier est dans le cache et n'a pas été modifié
                if cache_key in self.config_cache:
                    cache_time, config = self.config_cache[cache_key]
                    if cache_time >= mod_time:
                        # Stocker dans le dictionnaire approprié
                        if is_global:
                            self.global_configs[config_id] = config
                        else:
                            self.plugin_configs[config_id] = config
                        logger.debug(f"Configuration {'globale' if is_global else 'plugin'} '{config_id}' récupérée du cache")
                        return config
                
                # Charger le fichier YAML
                with open(path, 'r', encoding='utf-8') as f:
                    config = self.yaml.load(f)
                    
                # Valider la configuration
                validator = self._validate_global_config if is_global else self._validate_plugin_config
                is_valid, errors = validator(config)
                if not is_valid:
                    logger.error(f"Configuration {'globale' if is_global else 'plugin'} '{config_id}' invalide: {errors}")
                    return None
                    
                # Normaliser les champs de configuration si nécessaire
                if not is_global:
                    config = self._normalize_config_fields(config)
                    
                # Faire une copie profonde pour éviter les modifications accidentelles
                config_copy = copy.deepcopy(config)
                
                # Stocker dans le cache et le dictionnaire approprié
                self.config_cache[cache_key] = (mod_time, config_copy)
                if is_global:
                    self.global_configs[config_id] = config_copy
                else:
                    self.plugin_configs[config_id] = config_copy
                    
                logger.debug(f"Configuration {'globale' if is_global else 'plugin'} '{config_id}' chargée: {len(config)} clés")
                return config_copy
                
            except Exception as e:
                logger.error(f"Erreur lors du chargement de {'la configuration' if is_global else 'du plugin'} '{config_id}': {e}")
                logger.error(traceback.format_exc())
                return None

    def _create_backup(self, config_path: str) -> bool:
        """
        Crée une sauvegarde du fichier de configuration.
        
        Args:
            config_path: Chemin du fichier à sauvegarder
            
        Returns:
            bool: True si la sauvegarde a réussi
        """
        if not self.enable_backups:
            return True
            
        try:
            path = Path(config_path)
            if not path.exists():
                logger.debug(f"Pas de backup créé, le fichier n'existe pas: {config_path}")
                return False
                
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_file = backup_dir / f"{path.stem}_{timestamp}{path.suffix}"
            shutil.copy2(path, backup_file)
            
            logger.debug(f"Backup créé: {backup_file}")
            
            # Nettoyer les anciennes sauvegardes
            self._cleanup_backups(backup_dir, path.stem, self.backup_count)
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la création du backup pour {config_path}: {e}")
            logger.error(traceback.format_exc())
            return False
            
    def _cleanup_backups(self, backup_dir: Path, file_prefix: str, max_count: int) -> None:
        """
        Supprime les sauvegardes les plus anciennes.
        
        Args:
            backup_dir: Répertoire des sauvegardes
            file_prefix: Préfixe du fichier
            max_count: Nombre maximum de sauvegardes à conserver
        """
        try:
            if not backup_dir.exists():
                return
                
            # Lister tous les fichiers de sauvegarde pour ce préfixe
            backups = sorted([
                f for f in backup_dir.iterdir()
                if f.is_file() and f.name.startswith(file_prefix + "_")
            ], key=lambda f: f.stat().st_mtime)
            
            # Supprimer les plus anciens si nécessaire
            if len(backups) > max_count:
                for old_backup in backups[:-max_count]:
                    old_backup.unlink()
                    logger.debug(f"Ancienne sauvegarde supprimée: {old_backup}")
                    
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage des sauvegardes: {e}")
            logger.error(traceback.format_exc())

    def _normalize_config_fields(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise les champs de configuration d'un plugin.
        
        Args:
            config: Configuration brute du plugin
            
        Returns:
            Dict[str, Any]: Configuration normalisée
        """
        # Si config_fields est une liste, la convertir en dictionnaire
        if 'config_fields' in config and isinstance(config['config_fields'], list):
            fields_dict = {}
            for field in config['config_fields']:
                if isinstance(field, dict) and 'id' in field:
                    fields_dict[field['id']] = field
            config['config_fields'] = fields_dict
            logger.debug(f"Liste config_fields normalisée en dictionnaire: {len(fields_dict)} champs")
            
        # Normaliser les options spéciales
        if 'remote_execution' in config and not isinstance(config['remote_execution'], bool):
            config['remote_execution'] = str(config['remote_execution']).lower() in ('true', 'yes', '1', 'on')
            
        # Normaliser les dépendances
        if 'depends_on' in config and isinstance(config['depends_on'], list):
            dependencies = {}
            for dep in config['depends_on']:
                if isinstance(dep, str):
                    dependencies[dep] = True
                elif isinstance(dep, dict) and 'plugin' in dep:
                    dependencies[dep['plugin']] = dep.get('required', True)
            config['depends_on'] = dependencies
            
        return config

    def _validate_global_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valide une configuration globale.
        
        Args:
            config: Configuration à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        return self._validate_config(config, is_global=True)

    def _validate_plugin_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valide la configuration d'un plugin.
        
        Args:
            config: Configuration à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        return self._validate_config(config, is_global=False)

    def _validate_config(self, config: Dict[str, Any], is_global: bool = False) -> Tuple[bool, str]:
        """
        Valide une configuration selon son type.
        
        Args:
            config: Configuration à valider
            is_global: Si True, valide une configuration globale
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        if not isinstance(config, dict):
            return False, "La configuration doit être un dictionnaire"
        
        # Champs requis selon le type de configuration
        required_fields = ['config_fields'] if is_global else ['name']
        
        # Vérifier les champs requis
        for field in required_fields:
            if field not in config:
                return False, f"Champ requis manquant: {field}"
        
        # Vérifier le format de config_fields s'il existe
        if 'config_fields' in config and not isinstance(config['config_fields'], (dict, list)):
            return False, "Le champ 'config_fields' doit être un dictionnaire ou une liste"
        
        # Validation spécifique aux plugins
        if not is_global:
            # Vérifier la version minimale requise si spécifiée
            if 'min_version' in config and not isinstance(config['min_version'], (str, int, float)):
                return False, "Le champ 'min_version' doit être une chaîne, un entier ou un flottant"
                
            # Vérifier les dépendances
            if 'depends_on' in config:
                if not isinstance(config['depends_on'], (list, dict)):
                    return False, "Le champ 'depends_on' doit être une liste ou un dictionnaire"
        
        return True, ""

    def get_fields(self, config_id: str, is_global: bool = False) -> Dict[str, Any]:
        """
        Récupère les champs de configuration.
        
        Args:
            config_id: Identifiant de la configuration
            is_global: Si True, cherche dans les configurations globales
            
        Returns:
            Dict[str, Any]: Champs de configuration
        """
        with self._lock:
            source = self.global_configs if is_global else self.plugin_configs
            config = source.get(config_id, {})
    
            # Les configs globales utilisent 'fields', les plugins utilisent 'config_fields'
            field_key = 'fields' if is_global else 'config_fields'
            fields = config.get(field_key, {})
            
            # Assurer que le résultat est un dictionnaire
            if isinstance(fields, list):
                fields_dict = {}
                for field in fields:
                    if isinstance(field, dict) and 'id' in field:
                        fields_dict[field['id']] = field
                return fields_dict
                
            return copy.deepcopy(fields)  # Copie profonde pour éviter les modifications accidentelles

    def supports_remote_execution(self, plugin_id: str) -> bool:
        """
        Vérifie si un plugin supporte l'exécution à distance.
        
        Args:
            plugin_id: Identifiant du plugin
            
        Returns:
            bool: True si le plugin supporte l'exécution à distance
        """
        with self._lock:
            config = self.plugin_configs.get(plugin_id, {})
            return config.get('remote_execution', False)
        
    def get_config_value(self, config_id: str, key: str, default: Any = None, is_global: bool = False) -> Any:
        """
        Récupère une valeur de configuration.
        
        Args:
            config_id: Identifiant de la configuration
            key: Clé de la valeur à récupérer
            default: Valeur par défaut si la clé n'existe pas
            is_global: Si True, cherche dans les configurations globales
            
        Returns:
            Any: Valeur de configuration
        """
        with self._lock:
            source = self.global_configs if is_global else self.plugin_configs
            config = source.get(config_id, {})
            value = config.get(key, default)
            
            # Retourner une copie pour éviter la modification accidentelle des objets
            if isinstance(value, (dict, list)):
                return copy.deepcopy(value)
            return value
        
    def save_config(self, config_id: str, config_data: Dict[str, Any], config_path: str, is_global: bool = False) -> bool:
        """
        Sauvegarde une configuration dans un fichier YAML.
        
        Args:
            config_id: Identifiant de la configuration
            config_data: Données de configuration à sauvegarder
            config_path: Chemin où sauvegarder la configuration
            is_global: Si True, c'est une configuration globale
            
        Returns:
            bool: True si la sauvegarde a réussi
        """
        with self._lock:
            try:
                # Valider la configuration avant sauvegarde
                validator = self._validate_global_config if is_global else self._validate_plugin_config
                valid, error = validator(config_data)
                
                if not valid:
                    logger.error(f"Impossible de sauvegarder une configuration invalide: {error}")
                    return False
                    
                # Créer une sauvegarde avant modification
                self._create_backup(config_path)
                
                # Créer le dossier parent si nécessaire
                path = Path(config_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                
                # Normaliser les champs pour le plugin si nécessaire
                if not is_global:
                    config_data = self._normalize_config_fields(config_data)
                
                # Sauvegarder la configuration
                with open(path, 'w', encoding='utf-8') as f:
                    self.yaml.dump(config_data, f)
                    
                # Mettre à jour le cache et le dictionnaire
                cache_key = f"{'global' if is_global else 'plugin'}:{config_path}"
                self.config_cache[cache_key] = (time.time(), copy.deepcopy(config_data))
                
                if is_global:
                    self.global_configs[config_id] = copy.deepcopy(config_data)
                else:
                    self.plugin_configs[config_id] = copy.deepcopy(config_data)
                    
                logger.debug(f"Configuration {'globale' if is_global else 'plugin'} '{config_id}' sauvegardée: {config_path}")
                
                # Notifier les callbacks du changement
                self._notify_change(config_id, is_global)
                
                return True
                
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde de la configuration '{config_id}': {e}")
                logger.error(traceback.format_exc())
                return False
            
    def get_default_values(self, plugin_id: str) -> Dict[str, Any]:
        """
        Récupère les valeurs par défaut des champs d'un plugin.
        
        Args:
            plugin_id: Identifiant du plugin
            
        Returns:
            Dict[str, Any]: Valeurs par défaut {nom_variable: valeur}
        """
        with self._lock:
            default_values = {}
            
            # Parcourir tous les champs
            for field_id, field_config in self.get_fields(plugin_id).items():
                if 'default' in field_config:
                    # Utiliser le nom de variable s'il est défini, sinon l'ID du champ
                    variable_name = field_config.get('variable', field_id)
                    default_values[variable_name] = field_config['default']
                    
            return default_values
        
    def merge_configs(self, base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fusionne deux configurations avec priorité à override_config.
        
        Args:
            base_config: Configuration de base
            override_config: Configuration prioritaire
            
        Returns:
            Dict[str, Any]: Configuration fusionnée
        """
        # Copie profonde des configurations
        result = copy.deepcopy(base_config)
        override = copy.deepcopy(override_config)
        
        def _recursive_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
            """Fonction interne pour la fusion récursive des dictionnaires"""
            for key, value in override.items():
                # Fusion récursive pour les dictionnaires
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    base[key] = _recursive_merge(base[key], value)
                # Pour les listes, on peut choisir différentes stratégies
                elif key in base and isinstance(base[key], list) and isinstance(value, list):
                    # Stratégie : remplacer la liste entière
                    base[key] = value
                else:
                    # Sinon, remplacer/ajouter la valeur
                    base[key] = value
            return base
            
        # Appliquer la fusion récursive
        return _recursive_merge(result, override)
        
    def clear_cache(self, config_id: Optional[str] = None, is_global: bool = False) -> None:
        """
        Vide le cache des configurations.
        
        Args:
            config_id: Identifiant spécifique à vider ou None pour tout vider
            is_global: Si True, vide le cache des configurations globales
        """
        with self._lock:
            if config_id:
                # Vider le cache pour une configuration spécifique
                source = self.global_configs if is_global else self.plugin_configs
                if config_id in source:
                    # Trouver la clé de cache correspondante
                    prefix = 'global:' if is_global else 'plugin:'
                    to_remove = []
                    for key, (timestamp, data) in self.config_cache.items():
                        if key.startswith(prefix) and data is source[config_id]:
                            to_remove.append(key)
                    
                    # Supprimer les entrées du cache
                    for key in to_remove:
                        del self.config_cache[key]
                        
                    logger.debug(f"Cache vidé pour la configuration {'globale' if is_global else 'plugin'} '{config_id}'")
            else:
                # Vider tout le cache
                self.config_cache.clear()
                logger.debug("Cache de configurations entièrement vidé")
    
    def export_config(self, config_id: str, export_path: str, is_global: bool = False, format: str = 'yaml') -> bool:
        """
        Exporte une configuration dans un format spécifique.
        
        Args:
            config_id: Identifiant de la configuration
            export_path: Chemin où exporter la configuration
            is_global: Si True, exporte une configuration globale
            format: Format d'export ('yaml' ou 'json')
            
        Returns:
            bool: True si l'export a réussi
        """
        with self._lock:
            try:
                # Récupérer la configuration
                source = self.global_configs if is_global else self.plugin_configs
                if config_id not in source:
                    logger.error(f"Configuration '{config_id}' non trouvée pour export")
                    return False
                
                config_data = copy.deepcopy(source[config_id])
                
                # Créer le dossier parent si nécessaire
                path = Path(export_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                
                # Exporter selon le format
                if format.lower() == 'json':
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)
                else:  # yaml par défaut
                    with open(path, 'w', encoding='utf-8') as f:
                        self.yaml.dump(config_data, f)
                
                logger.debug(f"Configuration '{config_id}' exportée au format {format}: {export_path}")
                return True
                
            except Exception as e:
                logger.error(f"Erreur lors de l'export de la configuration '{config_id}': {e}")
                logger.error(traceback.format_exc())
                return False
    
    def import_config(self, config_id: str, import_path: str, is_global: bool = False, format: str = None) -> bool:
        """
        Importe une configuration depuis un fichier.
        
        Args:
            config_id: Identifiant de la configuration
            import_path: Chemin du fichier à importer
            is_global: Si True, importe une configuration globale
            format: Format du fichier ('yaml', 'json' ou None pour auto-détection)
            
        Returns:
            bool: True si l'import a réussi
        """
        with self._lock:
            try:
                path = Path(import_path)
                if not path.exists():
                    logger.error(f"Fichier d'import inexistant: {import_path}")
                    return False
                
                # Déterminer le format si non spécifié
                if format is None:
                    suffix = path.suffix.lower()
                    if suffix in ('.yaml', '.yml'):
                        format = 'yaml'
                    elif suffix == '.json':
                        format = 'json'
                    else:
                        logger.error(f"Impossible de déterminer le format: {suffix}")
                        return False
                
                # Importer selon le format
                if format.lower() == 'json':
                    with open(path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                else:  # yaml par défaut
                    with open(path, 'r', encoding='utf-8') as f:
                        config_data = self.yaml.load(f)
                
                # Valider la configuration
                validator = self._validate_global_config if is_global else self._validate_plugin_config
                valid, error = validator(config_data)
                if not valid:
                    logger.error(f"Configuration invalide dans {import_path}: {error}")
                    return False
                
                # Stocker la configuration
                if is_global:
                    self.global_configs[config_id] = config_data
                else:
                    self.plugin_configs[config_id] = config_data
                
                logger.debug(f"Configuration '{config_id}' importée depuis {import_path}")
                
                # Notifier les callbacks du changement
                self._notify_change(config_id, is_global)
                
                return True
                
            except Exception as e:
                logger.error(f"Erreur lors de l'import de la configuration '{config_id}': {e}")
                logger.error(traceback.format_exc())
                return False
    
    def get_dependencies(self, plugin_id: str) -> Dict[str, bool]:
        """
        Récupère les dépendances d'un plugin.
        
        Args:
            plugin_id: Identifiant du plugin
            
        Returns:
            Dict[str, bool]: Dépendances {plugin_id: required}
        """
        with self._lock:
            config = self.plugin_configs.get(plugin_id, {})
            dependencies = config.get('depends_on', {})
            
            # Normaliser les dépendances en dictionnaire
            if isinstance(dependencies, list):
                deps_dict = {}
                for dep in dependencies:
                    if isinstance(dep, str):
                        deps_dict[dep] = True  # Par défaut, la dépendance est requise
                    elif isinstance(dep, dict) and 'plugin' in dep:
                        deps_dict[dep['plugin']] = dep.get('required', True)
                return deps_dict
            
            return copy.deepcopy(dependencies) if isinstance(dependencies, dict) else {}