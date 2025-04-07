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
            Dict des configurations finales indexées par plugin_name_instance_id
        """
        result_config = {}   # Configurations finales à retourner
        
        # Créer un mapping des instances de séquence par plugin
        sequence_plugin_instances = {}
        if self.sequence_data and 'plugins' in self.sequence_data:
            for i, plugin_config in enumerate(self.sequence_data['plugins']):
                if isinstance(plugin_config, dict) and 'name' in plugin_config:
                    plugin_name = plugin_config['name']
                    if plugin_name not in sequence_plugin_instances:
                        sequence_plugin_instances[plugin_name] = []
                    sequence_plugin_instances[plugin_name].append(i)
        
        logger.debug("=== DÉBUT FUSION DES CONFIGURATIONS ===")
        logger.debug(f"Plugins à configurer: {plugin_instances}")
        logger.debug(f"Instances de séquence: {sequence_plugin_instances}")
        
        # Compteurs pour suivre les instances de chaque plugin
        plugin_counters = {}
        
        for plugin_data in plugin_instances:
            # Extraire les données du plugin
            if len(plugin_data) >= 3:
                plugin_name, instance_id, existing_config = plugin_data
            else:
                plugin_name, instance_id = plugin_data[:2]
                existing_config = None
                
            # Ignorer les plugins spéciaux comme __sequence__
            if plugin_name.startswith('__'):
                continue
            
            # Incrémenter le compteur pour ce plugin
            if plugin_name not in plugin_counters:
                plugin_counters[plugin_name] = 0
            current_count = plugin_counters[plugin_name]
            plugin_counters[plugin_name] += 1
            
            # IMPORTANT: Utiliser un ID standardisé partout
            plugin_instance_id = f"{plugin_name}_{instance_id}"
            logger.debug(f"Traitement du plugin {plugin_instance_id} (compteur: {current_count})")
            
            # Créer la configuration de base
            config_data = {
                'plugin_name': plugin_name,
                'instance_id': instance_id,
                'config': {}
            }
            
            # ÉTAPE 1: Appliquer la configuration par défaut
            # Si déjà une config par défaut dans current_config, la récupérer
            if plugin_instance_id in self.current_config:
                default_config = self.current_config[plugin_instance_id]
                if 'config' in default_config:
                    config_data['config'] = default_config['config'].copy()
                    logger.debug(f"Config par défaut trouvée pour {plugin_instance_id}: {config_data['config']}")
            
            # ÉTAPE 2: Appliquer la configuration de séquence si elle existe
            # Vérifier si ce plugin a des instances dans la séquence
            if plugin_name in sequence_plugin_instances and current_count < len(sequence_plugin_instances[plugin_name]):
                # Récupérer l'index de l'instance dans la séquence
                seq_index = sequence_plugin_instances[plugin_name][current_count]
                seq_plugin = self.sequence_data['plugins'][seq_index]
                
                # Extraire la configuration
                seq_config = {}
                if 'config' in seq_plugin:
                    seq_config = seq_plugin['config']
                elif 'variables' in seq_plugin:  # Rétrocompatibilité
                    seq_config = seq_plugin['variables']
                
                logger.debug(f"Config de séquence trouvée pour {plugin_instance_id} (index {seq_index}): {seq_config}")
                
                # Fusionner la configuration de séquence
                config_data['config'].update(seq_config)
                
                # Copier les métadonnées si présentes
                for key in ['show_name', 'icon', 'remote_execution']:
                    if key in seq_plugin:
                        config_data[key] = seq_plugin[key]
            
            # ÉTAPE 3: Si une config existante (plugin indépendant), elle a la priorité maximale
            if existing_config:
                logger.debug(f"Config existante (prioritaire) trouvée pour {plugin_instance_id}: {existing_config}")
                
                # Appliquer la configuration existante (priorité maximale)
                if 'config' in existing_config:
                    config_data['config'].update(existing_config['config'])
                else:
                    # Copier les valeurs non spéciales dans config
                    special_keys = {'plugin_name', 'instance_id', 'show_name', 'icon', 'remote_execution'}
                    existing_values = {k: v for k, v in existing_config.items() if k not in special_keys}
                    config_data['config'].update(existing_values)
                    
                # Copier les clés spéciales au niveau principal
                for key in ['show_name', 'icon', 'remote_execution']:
                    if key in existing_config:
                        config_data[key] = existing_config[key]
            
            # Stocker la configuration finale avec l'ID standardisé
            result_config[plugin_instance_id] = config_data
            logger.debug(f"Configuration finale pour {plugin_instance_id}: {config_data}")
        
        logger.debug(f"=== CONFIGURATIONS FINALES: {len(result_config)} plugins configurés ===")
        return result_config
