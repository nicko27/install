"""
Gestionnaire de configuration des séquences.
Gère le chargement et l'application des configurations de séquence aux plugins.
"""

from pathlib import Path
from ruamel.yaml import YAML
from typing import Dict, List, Optional, Any, Tuple
from ..utils.logging import get_logger

logger = get_logger('sequence_config_manager')
yaml = YAML()
yaml.preserve_quotes = True

class SequenceConfigManager:
    """Gestionnaire de configuration des séquences"""
    
    def __init__(self):
        self.sequence_data = None
        self.sequence_configs = {}  # Configurations indexées par nom de plugin
        self.current_config = {}    # Configurations finales par instance_id
    
    def load_sequence(self, sequence_file: str) -> None:
        """Charge une séquence depuis un fichier"""
        try:
            logger.debug(f"=== Chargement de la séquence: {sequence_file} ===")
            with open(sequence_file, 'r', encoding='utf-8') as f:
                self.sequence_data = yaml.load(f)
            logger.debug(f"Données de séquence chargées: {self.sequence_data}")
            
            # Initialiser le mapping des configurations par plugin
            self._init_sequence_configs()
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence: {e}")
            raise
    
    def _init_sequence_configs(self) -> None:
        """Initialise le mapping des configurations par plugin"""
        if not self.sequence_data or 'plugins' not in self.sequence_data:
            return
            
        for i, plugin in enumerate(self.sequence_data['plugins']):
            if not isinstance(plugin, dict) or 'name' not in plugin:
                continue
                
            plugin_name = plugin['name']
            if plugin_name not in self.sequence_configs:
                self.sequence_configs[plugin_name] = []
            
            # Créer la structure de configuration
            config_data = {
                'plugin_name': plugin_name,
                'config': {},
                'position': i  # Garder la position pour l'ordre
            }
            
            # Vérifier d'abord 'config' puis 'variables' pour la rétrocompatibilité
            if 'config' in plugin:
                config_data['config'] = plugin['config'].copy()
            elif 'variables' in plugin:
                config_data['config'] = plugin['variables'].copy()
            
            # Copier les clés spéciales au niveau principal
            special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
            for key in special_keys:
                if key in plugin:
                    config_data[key] = plugin[key]
            
            self.sequence_configs[plugin_name].append(config_data)
            logger.debug(f"Configuration ajoutée pour {plugin_name} position {i}: {config_data}")
    
    def add_plugin_config(self, plugin_name: str, instance_id: str, config: Dict) -> None:
        """
        Ajoute une configuration de plugin existante.
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID unique de l'instance
            config: Configuration existante du plugin
        """
        # Créer la structure de configuration
        config_data = {
            'plugin_name': plugin_name,
            'config': {}
        }
        
        # Si on a déjà une structure avec 'config'
        if 'config' in config:
            config_data['config'] = config['config'].copy()
        else:
            # Sinon, copier toutes les clés sauf celles spéciales dans 'config'
            special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
            config_data['config'] = {k: v for k, v in config.items() if k not in special_keys}
            
            # Copier les clés spéciales au niveau principal
            for key in special_keys:
                if key in config:
                    config_data[key] = config[key]
        
        # Stocker dans current_config
        self.current_config[instance_id] = config_data
        logger.debug(f"Configuration ajoutée pour {plugin_name} (ID: {instance_id}): {config_data}")
        
        # Ajouter également à sequence_configs pour la fusion ultérieure
        if plugin_name not in self.sequence_configs:
            self.sequence_configs[plugin_name] = []
        self.sequence_configs[plugin_name].append(config_data)
    
    def apply_configs_to_plugins(self, plugin_instances: List[Tuple[str, str, Optional[Dict]]]) -> Dict[str, Dict]:
        """
        Applique les configurations de la séquence aux plugins sélectionnés.
        
        Args:
            plugin_instances: Liste de tuples (plugin_name, instance_id, config?)
            
        Returns:
            Dict des configurations finales indexées par instance_id
        """
        instance_counts = {}  # Compteur d'instances par plugin
        id=0
        self.current_config={}
        
        for plugin_data in plugin_instances:
            id+=1
            # Extraire les données du plugin
            if len(plugin_data) >= 3:
                plugin_name, instance_id, existing_config = plugin_data
            else:
                plugin_name, instance_id = plugin_data[:2]
                existing_config = None
                
            # Ignorer les plugins spéciaux comme __sequence__
            if plugin_name.startswith('__'):
                continue
            
            # Initialiser ou incrémenter le compteur d'instances
            if plugin_name not in instance_counts:
                instance_counts[plugin_name] = 0
            current_count = instance_counts[plugin_name]
            instance_counts[plugin_name] += 1
            
            # Créer la configuration de base
            config_data = {
                'plugin_name': plugin_name,
                'config': {}
            }
            
            # 1. Si une config existe déjà, l'utiliser comme base
            if existing_config:
                if 'config' in existing_config:
                    config_data['config'] = existing_config['config'].copy()
                else:
                    # Copier les valeurs non spéciales dans config
                    special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
                    config_data['config'] = {k: v for k, v in existing_config.items() if k not in special_keys}
                    # Copier les clés spéciales au niveau principal
                    for key in special_keys:
                        if key in existing_config:
                            config_data[key] = existing_config[key]
            
            # 2. Si une config de séquence existe pour ce plugin, la fusionner
            if plugin_name in self.sequence_configs:
                configs = self.sequence_configs[plugin_name]
                if current_count < len(configs):
                    sequence_config = configs[current_count]
                    # Fusionner les configs
                    config_data['config'].update(sequence_config['config'])
                    # Copier les métadonnées si non définies
                    for key in ['show_name', 'icon', 'remote_execution']:
                        if key in sequence_config and key not in config_data:
                            config_data[key] = sequence_config[key]
            
            self.current_config[id] = config_data
            logger.debug(f"Configuration finale pour {plugin_name} (ID: {instance_id}): {config_data}")
        
        return self.current_config
