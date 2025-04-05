"""
Gestionnaire central des configurations pour les plugins et les paramètres globaux.
"""

from ruamel.yaml import YAML
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple
from ..utils.logging import get_logger

logger = get_logger('config_manager')

class ConfigManager:
    """
    Gestionnaire centralisé pour les configurations de plugins et globales.
    
    Cette classe est responsable de:
    - Charger les configurations YAML
    - Fournir un accès unifié aux configurations
    - Valider les configurations selon des schémas
    """

    def __init__(self):
        """Initialise le gestionnaire de configurations."""
        self.global_configs = {}  # {config_id: {config_data}}
        self.plugin_configs = {}  # {plugin_id: {config_data}}
        self.yaml = YAML()
        self.yaml.preserve_quotes = True  # Préserver les guillemets pour la sauvegarde
        self.config_cache = {}  # Cache pour les fichiers déjà chargés
        logger.debug("ConfigManager initialisé")

    def load_global_config(self, config_id: str, config_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge une configuration globale depuis un fichier YAML.
        
        Args:
            config_id: Identifiant unique de la configuration
            config_path: Chemin vers le fichier de configuration
            
        Returns:
            Optional[Dict[str, Any]]: Configuration chargée ou None en cas d'erreur
        """
        # Vérifier si la configuration est déjà en cache
        cache_key = f"global:{config_path}"
        if cache_key in self.config_cache:
            self.global_configs[config_id] = self.config_cache[cache_key]
            logger.debug(f"Configuration globale '{config_id}' récupérée du cache")
            return self.config_cache[cache_key]
        
        try:
            path = Path(config_path)
            if not path.exists():
                logger.error(f"Fichier de configuration inexistant: {config_path}")
                return None
                
            with open(path, 'r', encoding='utf-8') as f:
                config = self.yaml.load(f)
                
            # Valider la configuration
            is_valid, errors = self._validate_global_config(config)
            if not is_valid:
                logger.error(f"Configuration globale '{config_id}' invalide: {errors}")
                return None
                
            # Stocker dans le cache et le dictionnaire des configurations
            self.config_cache[cache_key] = config
            self.global_configs[config_id] = config
            logger.debug(f"Configuration globale '{config_id}' chargée: {len(config)} clés")
            return config
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la configuration '{config_id}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def load_plugin_config(self, plugin_id: str, settings_path: str) -> Optional[Dict[str, Any]]:
        """
        Charge la configuration d'un plugin depuis un fichier settings.yml.
        
        Args:
            plugin_id: Identifiant du plugin
            settings_path: Chemin vers le fichier settings.yml
            
        Returns:
            Optional[Dict[str, Any]]: Configuration du plugin ou None en cas d'erreur
        """
        # Vérifier si la configuration est déjà en cache
        cache_key = f"plugin:{settings_path}"
        if cache_key in self.config_cache:
            self.plugin_configs[plugin_id] = self.config_cache[cache_key]
            logger.debug(f"Configuration du plugin '{plugin_id}' récupérée du cache")
            return self.config_cache[cache_key]
            
        try:
            path = Path(settings_path)
            if not path.exists():
                logger.error(f"Fichier settings.yml inexistant: {settings_path}")
                return None
                
            with open(path, 'r', encoding='utf-8') as f:
                config = self.yaml.load(f)
                
            # Valider la configuration
            is_valid, errors = self._validate_plugin_config(config)
            if not is_valid:
                logger.error(f"Configuration du plugin '{plugin_id}' invalide: {errors}")
                return None
                
            # Normaliser les champs de configuration
            config = self._normalize_config_fields(config)
                
            # Stocker dans le cache et le dictionnaire des configurations
            self.config_cache[cache_key] = config
            self.plugin_configs[plugin_id] = config
            logger.debug(f"Configuration du plugin '{plugin_id}' chargée: {len(config)} clés")
            return config
        except Exception as e:
            logger.error(f"Erreur lors du chargement du plugin '{plugin_id}': {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

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
            
        return config

    def _validate_global_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valide une configuration globale.
        
        Args:
            config: Configuration à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        if not isinstance(config, dict):
            return False, "La configuration doit être un dictionnaire"
            
        # Vérifier les champs requis
        required_fields = ['config_fields']
        for field in required_fields:
            if field not in config:
                return False, f"Champ requis manquant: {field}"
                
        # Vérifier le format de config_fields
        if not isinstance(config['config_fields'], (dict, list)):
            return False, "Le champ 'config_fields' doit être un dictionnaire ou une liste"
            
        return True, ""

    def _validate_plugin_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valide la configuration d'un plugin.
        
        Args:
            config: Configuration à valider
            
        Returns:
            Tuple[bool, str]: (est_valide, message_erreur)
        """
        if not isinstance(config, dict):
            return False, "La configuration doit être un dictionnaire"
            
        # Vérifier les champs requis
        required_fields = ['name']
        for field in required_fields:
            if field not in config:
                return False, f"Champ requis manquant: {field}"
        
        # Vérifier le format de config_fields s'il existe
        if 'config_fields' in config and not isinstance(config['config_fields'], (dict, list)):
            return False, "Le champ 'config_fields' doit être un dictionnaire ou une liste"
            
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
            
        return fields

    def supports_remote_execution(self, plugin_id: str) -> bool:
        """
        Vérifie si un plugin supporte l'exécution à distance.
        
        Args:
            plugin_id: Identifiant du plugin
            
        Returns:
            bool: True si le plugin supporte l'exécution à distance
        """
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
        source = self.global_configs if is_global else self.plugin_configs
        config = source.get(config_id, {})
        return config.get(key, default)
        
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
        try:
            # Valider la configuration avant sauvegarde
            validator = self._validate_global_config if is_global else self._validate_plugin_config
            valid, error = validator(config_data)
            
            if not valid:
                logger.error(f"Impossible de sauvegarder une configuration invalide: {error}")
                return False
                
            # Créer le dossier parent si nécessaire
            path = Path(config_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarder la configuration
            with open(path, 'w', encoding='utf-8') as f:
                self.yaml.dump(config_data, f)
                
            # Mettre à jour le cache et le dictionnaire
            cache_key = f"{'global' if is_global else 'plugin'}:{config_path}"
            self.config_cache[cache_key] = config_data
            
            if is_global:
                self.global_configs[config_id] = config_data
            else:
                self.plugin_configs[config_id] = config_data
                
            logger.debug(f"Configuration {'globale' if is_global else 'plugin'} '{config_id}' sauvegardée: {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la configuration '{config_id}': {e}")
            import traceback
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
        plugin_config = self.plugin_configs.get(plugin_id, {})
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
        # Copie profonde de la configuration de base
        result = {**base_config}
        
        # Appliquer les valeurs de la configuration prioritaire
        for key, value in override_config.items():
            # Fusion récursive pour les dictionnaires
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result
        
    def clear_cache(self, config_id: Optional[str] = None, is_global: bool = False) -> None:
        """
        Vide le cache des configurations.
        
        Args:
            config_id: Identifiant spécifique à vider ou None pour tout vider
            is_global: Si True, vide le cache des configurations globales
        """
        if config_id:
            # Vider le cache pour une configuration spécifique
            source = self.global_configs if is_global else self.plugin_configs
            if config_id in source:
                # Trouver la clé de cache correspondante
                prefix = 'global:' if is_global else 'plugin:'
                to_remove = []
                
                for cache_key in self.config_cache:
                    if cache_key.startswith(prefix) and self.config_cache[cache_key] is source[config_id]:
                        to_remove.append(cache_key)
                
                # Supprimer les entrées du cache
                for key in to_remove:
                    del self.config_cache[key]
                    
                logger.debug(f"Cache vidé pour la configuration {'globale' if is_global else 'plugin'} '{config_id}'")
        else:
            # Vider tout le cache
            self.config_cache.clear()
            logger.debug("Cache de configurations entièrement vidé")