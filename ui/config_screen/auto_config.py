"""
Module pour le traitement automatique d'une configuration de séquence sans interface graphique.
Ce module permet de préparer les configurations des plugins pour l'exécution.
"""

import os
import traceback
import re
from ruamel.yaml import YAML
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set, Union

from ..utils.logging import get_logger
from ..choice_screen.plugin_utils import get_plugin_folder_name, get_plugin_settings_path
from .config_manager import ConfigManager

logger = get_logger('auto_config')
yaml = YAML()
yaml.preserve_quotes = True

# Compilation de l'expression régulière une seule fois pour une meilleure performance
VAR_PATTERN = re.compile(r'\{([^}]+)\}')

class AutoConfig:
    """
    Gestion automatique de la configuration des plugins sans interface graphique.
    
    Cette classe permet de traiter une séquence et de générer une configuration
    compatible avec ExecutionScreen sans passer par l'interface de configuration.
    """
    
    def __init__(self):
        """Initialisation du gestionnaire de configuration automatique."""
        logger.debug("Initialisation d'AutoConfig")
        self.config_manager = ConfigManager()
        self.settings_cache = {}  # Cache pour les fichiers settings.yml
        
    def process_sequence(self, sequence_path: Union[str, Path], 
                         plugin_instances: List[Tuple[str, int, Optional[Dict[str, Any]]]]) -> Dict[str, Any]:
        """
        Traite une séquence et génère une configuration pour tous les plugins.
        
        Args:
            sequence_path: Chemin vers le fichier de séquence YAML
            plugin_instances: Liste de tuples (plugin_name, instance_id, [config])
            
        Returns:
            dict: Configuration des plugins au format attendu par ExecutionScreen
        """
        try:
            sequence_path = Path(sequence_path) if isinstance(sequence_path, str) else sequence_path
            logger.debug(f"Traitement de la séquence {sequence_path} avec {len(plugin_instances)} plugins")
            
            # Charger la séquence
            sequence_data = self._load_sequence(sequence_path)
            if not sequence_data:
                logger.error(f"Impossible de charger la séquence: {sequence_path}")
                return {}
            
            # Configuration finale à retourner
            config = {}
            
            # Indexer les plugins par type pour faciliter le traitement
            sequence_plugins_by_type = self._index_sequence_plugins(sequence_data.get('plugins', []))
            plugin_type_instances = self._count_plugin_type_instances(plugin_instances)
            
            # Traiter chaque plugin avec sa configuration
            for i, plugin_data in enumerate(plugin_instances):
                # Extraire les informations du plugin
                if len(plugin_data) >= 3:
                    plugin_name, instance_id, initial_config = plugin_data
                else:
                    plugin_name, instance_id = plugin_data[:2]
                    initial_config = None
                
                # Ignorer les séquences
                if plugin_name.startswith('__sequence__'):
                    continue
                
                # Générer l'ID unique du plugin
                plugin_id = f"{plugin_name}_{instance_id}"
                logger.debug(f"Traitement du plugin {plugin_id} (instance {plugin_type_instances[plugin_name].index(instance_id) + 1} de {len(plugin_type_instances[plugin_name])})")
                
                # Construire la configuration complète du plugin
                plugin_config = self._build_plugin_config(
                    plugin_name, 
                    instance_id, 
                    sequence_plugins_by_type.get(plugin_name, []),
                    plugin_type_instances[plugin_name].index(instance_id),
                    initial_config
                )
                
                # Ajouter au résultat
                config[plugin_id] = plugin_config
                logger.debug(f"Configuration générée pour {plugin_id}")
            
            logger.debug(f"Configuration complète générée avec {len(config)} plugins")
            return config
            
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la séquence: {e}")
            logger.error(traceback.format_exc())
            return {}

    def _load_sequence(self, sequence_path: Path) -> Optional[Dict[str, Any]]:
        """
        Charge une séquence depuis un fichier YAML.
        
        Args:
            sequence_path: Chemin du fichier de séquence
            
        Returns:
            Optional[Dict[str, Any]]: Données de la séquence ou None en cas d'erreur
        """
        try:
            if not sequence_path.exists():
                logger.error(f"Fichier de séquence inexistant: {sequence_path}")
                return None
                
            with open(sequence_path, 'r', encoding='utf-8') as f:
                sequence_data = yaml.load(f)
                logger.debug(f"Séquence chargée: {sequence_path}")
                return sequence_data
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_path}: {e}")
            return None

    def _index_sequence_plugins(self, plugins: List[Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Indexe les plugins d'une séquence par leur type.
        
        Args:
            plugins: Liste des plugins de la séquence
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: Plugins indexés par type
        """
        indexed = {}
        
        for plugin in plugins:
            # Traiter les deux formats possibles (dict ou str)
            if isinstance(plugin, dict) and 'name' in plugin:
                plugin_name = plugin['name']
                if plugin_name not in indexed:
                    indexed[plugin_name] = []
                indexed[plugin_name].append(plugin)
            elif isinstance(plugin, str):
                if plugin not in indexed:
                    indexed[plugin] = []
                indexed[plugin].append({'name': plugin})
        
        return indexed
        
    def _count_plugin_type_instances(self, plugin_instances: List[Tuple[str, int, Optional[Dict[str, Any]]]]) -> Dict[str, List[int]]:
        """
        Compte les instances de chaque type de plugin.
        
        Args:
            plugin_instances: Liste des instances de plugins
            
        Returns:
            Dict[str, List[int]]: Pour chaque type de plugin, liste des IDs d'instance
        """
        type_instances = {}
        
        for plugin_data in plugin_instances:
            plugin_name = plugin_data[0]
            instance_id = plugin_data[1]
            
            # Ignorer les séquences
            if plugin_name.startswith('__sequence__'):
                continue
                
            if plugin_name not in type_instances:
                type_instances[plugin_name] = []
                
            type_instances[plugin_name].append(instance_id)
            
        return type_instances

    def _load_plugin_settings(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Charge les paramètres d'un plugin avec mise en cache.
        
        Args:
            plugin_name: Nom du plugin
            
        Returns:
            Optional[Dict[str, Any]]: Paramètres du plugin ou None en cas d'erreur
        """
        # Vérifier d'abord le cache
        if plugin_name in self.settings_cache:
            return self.settings_cache[plugin_name]
        
        try:
            # Determiner le chemin du fichier settings.yml
            settings_path = get_plugin_settings_path(plugin_name)
            
            # Charger les paramètres
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = yaml.load(f)
                
            # Mettre en cache
            self.settings_cache[plugin_name] = settings
            logger.debug(f"Paramètres chargés pour {plugin_name}")
            return settings
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement des paramètres de {plugin_name}: {e}")
            return None

    def _build_plugin_config(self, plugin_name: str, instance_id: int, 
                           sequence_configs: List[Dict[str, Any]], 
                           sequence_position: int,
                           initial_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Construit la configuration complète d'un plugin.
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID d'instance
            sequence_configs: Liste des configurations dans la séquence pour ce plugin
            sequence_position: Position du plugin dans sa séquence
            initial_config: Configuration initiale du plugin
            
        Returns:
            Dict[str, Any]: Configuration complète du plugin
        """
        try:
            # Charger les paramètres du plugin
            plugin_settings = self._load_plugin_settings(plugin_name)
            if not plugin_settings:
                logger.warning(f"Paramètres non trouvés pour {plugin_name}")
                plugin_settings = {'name': plugin_name, 'icon': '📦'}
            
            # Structure de base de la configuration
            config = {
                'plugin_name': plugin_name,
                'instance_id': instance_id,
                'name': plugin_settings.get('name', plugin_name),
                'show_name': plugin_settings.get('plugin_name', plugin_name),
                'icon': plugin_settings.get('icon', '📦'),
                'config': {},
                'remote_execution': False
            }
            
            # 1. Ajouter les valeurs par défaut depuis les paramètres
            self._add_default_values(config, plugin_settings)
            
            # 2. Ajouter la configuration de la séquence si disponible
            if sequence_configs and sequence_position < len(sequence_configs):
                seq_config = sequence_configs[sequence_position]
                self._add_sequence_config(config, seq_config)
            
            # 3. Ajouter la configuration initiale (priorité maximale)
            if initial_config:
                self._add_initial_config(config, initial_config)
            
            # 4. Charger les contenus dynamiques si nécessaire
            config = self._load_dynamic_file_contents(plugin_name, config)
            
            # 5. Configuration SSH si le plugin est en mode distant
            if config.get('remote_execution', False):
                config = self._process_ssh_config(config)
            
            # 6. Finaliser la configuration
            self._finalize_config(config, plugin_settings)
            
            return config
        except Exception as e:
            logger.error(f"Erreur lors de la construction de la configuration pour {plugin_name}: {e}")
            logger.error(traceback.format_exc())
            # Retourner une configuration minimale en cas d'erreur
            return {
                'plugin_name': plugin_name,
                'instance_id': instance_id,
                'name': plugin_name,
                'icon': '📦',
                'config': {},
                'remote_execution': False
            }

    def _add_default_values(self, config: Dict[str, Any], plugin_settings: Dict[str, Any]) -> None:
        """
        Ajoute les valeurs par défaut des champs à la configuration.
        
        Args:
            config: Configuration à enrichir
            plugin_settings: Paramètres du plugin
        """
        try:
            # Vérifier que les champs de configuration existent
            if 'config_fields' not in plugin_settings:
                logger.warning(f"Pas de config_fields dans les paramètres de {config['plugin_name']}")
                return
            
            # Parcourir tous les champs
            for field_id, field_config in plugin_settings['config_fields'].items():
                if not isinstance(field_config, dict):
                    continue
                
                # Récupérer le nom de variable (export)
                variable_name = field_config.get('variable', field_id)
                
                # Vérifier si une valeur par défaut est spécifiée
                if 'default' in field_config:
                    # Ne pas écraser une valeur déjà définie
                    if variable_name not in config['config']:
                        # Copier la valeur par défaut
                        import copy
                        default_value = copy.deepcopy(field_config['default'])
                        config['config'][variable_name] = default_value
                        logger.debug(f"Valeur par défaut pour {config['plugin_name']}.{variable_name}: {default_value}")
                    
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout des valeurs par défaut: {e}")
            logger.error(traceback.format_exc())

    def _add_sequence_config(self, config: Dict[str, Any], sequence_config: Dict[str, Any]) -> None:
        """
        Ajoute les paramètres de la séquence à la configuration.
        
        Args:
            config: Configuration à enrichir
            sequence_config: Configuration de la séquence
        """
        try:
            # Vérifier que le dictionnaire de config existe
            if 'config' not in config:
                config['config'] = {}
            
            # Gérer le cas des différents formats de configuration
            if 'config' in sequence_config and isinstance(sequence_config['config'], dict):
                # Format moderne avec 'config'
                import copy
                sequence_values = copy.deepcopy(sequence_config['config'])
                config['config'].update(sequence_values)
                logger.debug(f"Configuration de séquence ajoutée pour {config['plugin_name']}: {len(sequence_values)} paramètres")
            elif 'variables' in sequence_config and isinstance(sequence_config['variables'], dict):
                # Format ancien avec 'variables'
                import copy
                sequence_values = copy.deepcopy(sequence_config['variables'])
                config['config'].update(sequence_values)
                logger.debug(f"Variables de séquence (ancien format) ajoutées pour {config['plugin_name']}: {len(sequence_values)} paramètres")
            
            # Copier les attributs spéciaux
            special_keys = {
                'show_name', 'icon', 'remote_execution', 
                'template', 'ignore_errors', 'timeout'
            }
            
            for key in special_keys:
                if key in sequence_config:
                    config[key] = sequence_config[key]
                
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de la configuration de séquence: {e}")
            logger.error(traceback.format_exc())

    def _add_initial_config(self, config: Dict[str, Any], initial_config: Dict[str, Any]) -> None:
        """
        Ajoute la configuration initiale à la configuration.
        La configuration initiale a la priorité la plus élevée.
        
        Args:
            config: Configuration à enrichir
            initial_config: Configuration initiale
        """
        try:
            # Vérifier que le dictionnaire de config existe
            if 'config' not in config:
                config['config'] = {}
            
            # Gérer le cas des différents formats de configuration
            if 'config' in initial_config and isinstance(initial_config['config'], dict):
                # Format moderne avec 'config'
                import copy
                initial_values = copy.deepcopy(initial_config['config'])
                config['config'].update(initial_values)
                logger.debug(f"Configuration initiale ajoutée pour {config['plugin_name']}: {len(initial_values)} paramètres")
            else:
                # Format ancien (structure plate)
                # Identifier les clés spéciales vs. les clés de configuration
                special_keys = {
                    'plugin_name', 'instance_id', 'name', 'show_name', 
                    'icon', 'remote_execution', 'template'
                }
                
                # Copier les valeurs non spéciales dans config
                config_values = {}
                for k, v in initial_config.items():
                    if k not in special_keys:
                        config_values[k] = v
                    
                if config_values:
                    config['config'].update(config_values)
                    logger.debug(f"Configuration initiale (format plat) ajoutée pour {config['plugin_name']}: {len(config_values)} paramètres")
            
            # Copier les attributs spéciaux
            special_keys = {
                'show_name', 'icon', 'remote_execution', 
                'template', 'ignore_errors', 'timeout'
            }
            
            for key in special_keys:
                if key in initial_config:
                    config[key] = initial_config[key]
                
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de la configuration initiale: {e}")
            logger.error(traceback.format_exc())

    def _load_dynamic_file_contents(self, plugin_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Charge le contenu des fichiers dynamiques référencés dans la configuration.
        
        Args:
            plugin_name: Nom du plugin
            config: Configuration du plugin
            
        Returns:
            Dict[str, Any]: Configuration mise à jour
        """
        try:
            # Récupérer les paramètres du plugin
            plugin_settings = self._load_plugin_settings(plugin_name)
            if not plugin_settings:
                return config
                
            # Vérifier si le plugin utilise files_content
            files_content = plugin_settings.get('files_content', {})
            if not files_content:
                return config
                
            logger.debug(f"Le plugin {plugin_name} utilise files_content: {files_content}")
            
            # Traiter chaque fichier référencé
            folder_name = get_plugin_folder_name(plugin_name)
            plugin_dir = Path('plugins') / folder_name
            
            for content_key, path_template in files_content.items():
                try:
                    # Remplacer les variables dans le chemin
                    file_path = self._resolve_template_path(path_template, config['config'])
                    
                    # Si toutes les variables sont remplacées, charger le fichier
                    if '{' not in file_path:
                        # Construire le chemin complet
                        full_path = plugin_dir / file_path
                        
                        if full_path.exists():
                            # Charger le contenu du fichier
                            with open(full_path, 'r', encoding='utf-8') as f:
                                file_content = yaml.load(f)
                            
                            # Ajouter le contenu
                            config['config'][content_key] = file_content
                            logger.debug(f"Contenu de {full_path} chargé pour {content_key}")
                        else:
                            logger.warning(f"Fichier {full_path} introuvable")
                except Exception as e:
                    logger.error(f"Erreur lors du chargement de {content_key}: {e}")
                    logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Erreur lors du chargement des fichiers dynamiques: {e}")
            
        return config

    def _resolve_template_path(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Résout un chemin de template en remplaçant les variables.
        
        Args:
            template: Chemin de template avec variables {var}
            variables: Dictionnaire des variables à remplacer
            
        Returns:
            str: Chemin résolu
        """
        path = template
        
        # Trouver toutes les variables dans le template
        var_matches = VAR_PATTERN.findall(template)
        
        for var in var_matches:
            if var in variables:
                value = str(variables[var])
                
                # Éviter les doubles extensions
                if '.yml' in template and value.endswith('.yml'):
                    value = value[:-4]  # Retirer .yml
                    logger.debug(f"Extension .yml retirée de {value+'.yml'} pour éviter la double extension")
                
                # Remplacer la variable
                path = path.replace(f"{{{var}}}", value)
        
        return path

    def _process_ssh_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite les configurations SSH spécifiques.
        
        Args:
            config: Configuration du plugin
            
        Returns:
            Dict[str, Any]: Configuration mise à jour
        """
        try:
            # Vérifier si c'est un plugin SSH
            if 'ssh_ips' in config['config']:
                # Gérer les IPs multiples ou wildcards
                from ..ssh_manager.ip_utils import get_target_ips
                target_ips = get_target_ips(
                    config['config'].get('ssh_ips', ''), 
                    config['config'].get('ssh_exception_ips', [])
                )
                if target_ips:
                    config['config']['ssh_ips'] = ','.join(target_ips)
                    logger.debug(f"IPs SSH traitées: {config['config']['ssh_ips']}")
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la configuration SSH: {e}")
            
        return config

    def _finalize_config(self, config: Dict[str, Any], plugin_settings: Dict[str, Any]) -> None:
        """
        Finalise la configuration pour l'exécution.
        
        Args:
            config: Configuration à finaliser
            plugin_settings: Paramètres du plugin
        """
        # Vérifier si le plugin supporte l'exécution distante
        supports_remote = plugin_settings.get('remote_execution', False)
        remote_enabled = config.get('remote_execution', False)
        
        # Appliquer l'état d'exécution distante final
        config['remote_execution'] = supports_remote and remote_enabled
        
        # Si l'exécution distante est activée, traiter la configuration SSH
        if config['remote_execution']:
            config = self._process_ssh_config(config)
            logger.debug(f"Configuration SSH traitée pour exécution distante")

# Fonction utilitaire pour être appelée directement depuis main.py
def process_sequence_file(sequence_path: Union[str, Path], 
                        plugin_instances: List[Tuple[str, int, Optional[Dict[str, Any]]]]) -> Dict[str, Any]:
    """
    Traite un fichier de séquence et retourne la configuration des plugins.
    
    Args:
        sequence_path: Chemin vers le fichier de séquence
        plugin_instances: Liste des instances de plugins
        
    Returns:
        Dict[str, Any]: Configuration des plugins au format ExecutionScreen
    """
    auto_config = AutoConfig()
    return auto_config.process_sequence(sequence_path, plugin_instances)