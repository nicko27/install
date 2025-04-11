"""
Gestionnaire de configuration des séquences.
Gère le chargement, la fusion et l'application des configurations de séquence aux plugins.
"""

from pathlib import Path
from ruamel.yaml import YAML
from typing import Dict, List, Optional, Any, Tuple, Union, Set
import copy
import traceback
from ..utils.logging import get_logger

logger = get_logger('sequence_config_manager')
yaml = YAML()
yaml.preserve_quotes = True

class SequenceConfigManager:
    """
    Gestionnaire de configuration des séquences
    
    Cette classe est responsable de:
    - Charger les configurations depuis les fichiers de séquence
    - Fusionner les configurations de différentes sources
    - Appliquer les configurations aux plugins sélectionnés
    - Gérer la rétrocompatibilité entre les anciens formats (variables) et nouveaux (config)
    """
    
    def __init__(self):
        """Initialise le gestionnaire de configuration."""
        # Données brutes de la séquence chargée
        self.sequence_data = None
        
        # Configurations indexées par nom de plugin -> liste de configurations
        # Chaque configuration est un dictionnaire avec format standardisé
        self.sequence_configs = {}
        
        # Configurations finales indexées par ID d'instance unique (plugin_name_instance_id)
        # Contient les configurations fusionnées prêtes à être utilisées
        self.current_config = {}
        
        # Ensemble des plugins qui ont déjà été associés à une configuration de séquence
        # Utilisé pour éviter d'associer plusieurs fois un plugin à une même configuration
        self._matched_plugins = set()
        
        logger.debug("Gestionnaire de configuration des séquences initialisé")
    
    def load_sequence(self, sequence_file: Union[str, Path]) -> None:
        """
        Charge une séquence depuis un fichier YAML.
        
        Args:
            sequence_file: Chemin vers le fichier de séquence
            
        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            ValueError: Si le format de la séquence est invalide
        """
        try:
            # Convertir en Path si nécessaire
            sequence_path = Path(sequence_file) if isinstance(sequence_file, str) else sequence_file
            logger.debug(f"=== Chargement de la séquence: {sequence_path} ===")
            
            # Vérifier que le fichier existe
            if not sequence_path.exists():
                logger.error(f"Fichier de séquence non trouvé: {sequence_path}")
                raise FileNotFoundError(f"Fichier de séquence non trouvé: {sequence_path}")
            
            # Charger le contenu YAML
            with open(sequence_path, 'r', encoding='utf-8') as f:
                self.sequence_data = yaml.load(f)
            
            # Valider la structure de base
            if not isinstance(self.sequence_data, dict):
                logger.error(f"Format invalide: la séquence n'est pas un dictionnaire")
                raise ValueError("La séquence doit être un dictionnaire")
            
            # Vérifier les champs obligatoires
            required_fields = ['name', 'plugins']
            missing_fields = [field for field in required_fields if field not in self.sequence_data]
            if missing_fields:
                logger.error(f"Champs requis manquants: {', '.join(missing_fields)}")
                raise ValueError(f"Champs requis manquants: {', '.join(missing_fields)}")
            
            # Vérifier que plugins est une liste
            if not isinstance(self.sequence_data['plugins'], list):
                logger.error("Le champ 'plugins' doit être une liste")
                raise ValueError("Le champ 'plugins' doit être une liste")
            
            # Ajouter une description par défaut si absente
            if 'description' not in self.sequence_data:
                self.sequence_data['description'] = f"Séquence {self.sequence_data['name']}"
            
            logger.debug(f"Séquence chargée: {self.sequence_data['name']} " +
                         f"avec {len(self.sequence_data['plugins'])} plugins")
            
            # Initialiser le mapping des configurations par plugin
            self._init_sequence_configs()
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence: {e}")
            logger.error(traceback.format_exc())
            # Réinitialiser en cas d'erreur
            self.sequence_data = None
            self.sequence_configs = {}
            raise
    
    def _init_sequence_configs(self) -> None:
        """
        Initialise le mapping des configurations par plugin.
        Normalise et convertit toutes les configurations au format standardisé.
        """
        try:
            # Réinitialiser le dictionnaire
            self.sequence_configs = {}
            
            # Vérifier que les données de séquence existent
            if not self.sequence_data or 'plugins' not in self.sequence_data:
                logger.warning("Aucune donnée de séquence à initialiser")
                return
            
            # Parcourir tous les plugins de la séquence
            for position, plugin_config in enumerate(self.sequence_data['plugins']):
                # Traiter différents formats possibles
                
                # Format 1: Chaîne simple (juste le nom du plugin)
                if isinstance(plugin_config, str):
                    plugin_name = plugin_config
                    normalized_config = {
                        'plugin_name': plugin_name,
                        'config': {},
                        'position': position
                    }
                    
                # Format 2: Dictionnaire avec configuration
                elif isinstance(plugin_config, dict) and 'name' in plugin_config:
                    plugin_name = plugin_config['name']
                    
                    # Créer une structure de configuration standardisée
                    normalized_config = {
                        'plugin_name': plugin_name,
                        'config': {},
                        'position': position
                    }
                    
                    # Gestion de la configuration avec rétrocompatibilité
                    # Format moderne: utilise 'config'
                    if 'config' in plugin_config:
                        if isinstance(plugin_config['config'], dict):
                            normalized_config['config'] = copy.deepcopy(plugin_config['config'])
                        else:
                            logger.warning(f"Format 'config' invalide pour {plugin_name} " +
                                          f"(position {position}): doit être un dictionnaire")
                    
                    # Format ancien: utilise 'variables'
                    elif 'variables' in plugin_config:
                        if isinstance(plugin_config['variables'], dict):
                            normalized_config['config'] = copy.deepcopy(plugin_config['variables'])
                            logger.debug(f"Conversion du format ancien 'variables' " +
                                        f"vers 'config' pour {plugin_name}")
                        else:
                            logger.warning(f"Format 'variables' invalide pour {plugin_name} " +
                                          f"(position {position}): doit être un dictionnaire")
                    
                    # Copier les attributs spéciaux au niveau principal
                    special_keys = {
                        'show_name', 'icon', 'remote_execution', 
                        'template', 'ignore_errors', 'timeout'
                    }
                    
                    for key in special_keys:
                        if key in plugin_config:
                            normalized_config[key] = plugin_config[key]
                
                # Format invalide
                else:
                    logger.warning(f"Plugin invalide à la position {position}: " +
                                  f"doit être une chaîne ou un dictionnaire avec 'name'")
                    continue
                
                # Ajouter au dictionnaire des configurations
                if plugin_name not in self.sequence_configs:
                    self.sequence_configs[plugin_name] = []
                
                self.sequence_configs[plugin_name].append(normalized_config)
                
                logger.debug(f"Configuration ajoutée pour {plugin_name} (position {position})")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation des configurations: {e}")
            logger.error(traceback.format_exc())
            self.sequence_configs = {}
    
    def add_plugin_config(self, plugin_name: str, instance_id: Union[int, str], 
                         config: Dict[str, Any]) -> None:
        """
        Ajoute manuellement une configuration de plugin existante.
        Utile pour les configurations qui ne viennent pas d'une séquence.
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID unique de l'instance
            config: Configuration existante du plugin
        """
        try:
            # Créer un ID unique standardisé
            plugin_instance_id = f"{plugin_name}_{instance_id}"
            
            # Créer une structure de configuration standardisée
            normalized_config = {
                'plugin_name': plugin_name,
                'instance_id': instance_id,
                'config': {}
            }
            
            # Format 1: La configuration a déjà une structure 'config'
            if isinstance(config, dict):
                if 'config' in config and isinstance(config['config'], dict):
                    normalized_config['config'] = copy.deepcopy(config['config'])
                
                # Format 2: Ancienne structure plate
                else:
                    # Identifier les clés spéciales vs. les clés de configuration
                    special_keys = {
                        'plugin_name', 'instance_id', 'name', 'show_name', 
                        'icon', 'remote_execution', 'template'
                    }
                    
                    # Copier les valeurs non spéciales dans config
                    config_values = {k: v for k, v in config.items() if k not in special_keys}
                    normalized_config['config'] = config_values
                    
                    # Copier les clés spéciales au niveau principal
                    for key in special_keys:
                        if key in config:
                            normalized_config[key] = config[key]
            
                # Stocker dans current_config avec l'ID standardisé
                self.current_config[plugin_instance_id] = normalized_config
                
                # Ajouter également à sequence_configs pour la fusion ultérieure
                if plugin_name not in self.sequence_configs:
                    self.sequence_configs[plugin_name] = []
                
                # Vérifier si une config existe déjà pour cette instance
                for i, existing_config in enumerate(self.sequence_configs[plugin_name]):
                    if 'instance_id' in existing_config and existing_config['instance_id'] == instance_id:
                        # Remplacer la configuration existante
                        self.sequence_configs[plugin_name][i] = normalized_config
                        logger.debug(f"Configuration remplacée pour {plugin_name} (ID: {instance_id})")
                        break
                else:
                    # Ajouter comme nouvelle configuration
                    self.sequence_configs[plugin_name].append(normalized_config)
                
                logger.debug(f"Configuration ajoutée manuellement pour {plugin_name} " +
                            f"(ID: {instance_id}) avec {len(normalized_config['config'])} paramètres")
            else:
                logger.warning(f"Configuration invalide pour {plugin_name} (ID: {instance_id}): doit être un dictionnaire")
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de configuration manuelle: {e}")
            logger.error(traceback.format_exc())
    
    def apply_configs_to_plugins(self, plugin_instances: List[Tuple[str, Union[int, str], Optional[Dict]]]) -> Dict[str, Dict]:
        """
        Applique les configurations aux plugins sélectionnés.
        Fusionne les configurations de différentes sources selon l'ordre de priorité.
        
        Args:
            plugin_instances: Liste de tuples (plugin_name, instance_id, config?)
            
        Returns:
            Dict[str, Dict]: Configurations finales indexées par plugin_instance_id
        """
        try:
            # Réinitialiser les configurations finales et l'ensemble des plugins associés
            result_config = {}
            self._matched_plugins = set()
            
            logger.debug("=== DÉBUT FUSION DES CONFIGURATIONS ===")
            
            # Index des instances de plugins par type pour le mapping avec la séquence
            plugin_counters = {}
            plugin_type_instances = {}
            
            # Créer un mapping des instances pour chaque type de plugin
            for plugin_data in plugin_instances:
                # Extraire les données du plugin
                if len(plugin_data) >= 3:
                    plugin_name, instance_id, _ = plugin_data
                else:
                    plugin_name, instance_id = plugin_data[:2]
                
                # Ignorer les plugins spéciaux
                if isinstance(plugin_name, str) and plugin_name.startswith('__'):
                    continue
                
                # Initialiser les listes si nécessaire
                if plugin_name not in plugin_type_instances:
                    plugin_type_instances[plugin_name] = []
                
                # Ajouter l'ID d'instance à la liste
                plugin_type_instances[plugin_name].append(instance_id)
            
            # Déterminer les instances de plugins de la séquence par type
            sequence_plugin_instances = self._index_sequence_plugins_by_type()
            logger.debug(f"Instances de plugins dans la séquence: {sequence_plugin_instances}")
            
            # Parcourir tous les plugins sélectionnés
            for plugin_data in plugin_instances:
                # Extraire les données du plugin
                if len(plugin_data) >= 3:
                    plugin_name, instance_id, existing_config = plugin_data
                else:
                    plugin_name, instance_id = plugin_data[:2]
                    existing_config = None
                
                # Ignorer les plugins spéciaux comme les séquences
                if isinstance(plugin_name, str) and plugin_name.startswith('__'):
                    logger.debug(f"Plugin spécial ignoré: {plugin_name}")
                    continue
                
                # Incrémenter le compteur pour ce type de plugin
                if plugin_name not in plugin_counters:
                    plugin_counters[plugin_name] = 0
                current_count = plugin_counters[plugin_name]
                plugin_counters[plugin_name] += 1
                
                # Créer un ID unique standardisé
                plugin_instance_id = f"{plugin_name}_{instance_id}"
                
                logger.debug(f"Traitement du plugin {plugin_instance_id} " +
                            f"(instance {current_count + 1} de {plugin_name})")
                
                # 1. CRÉATION DE LA CONFIGURATION DE BASE
                config_data = self._create_base_config(plugin_name, instance_id)
                
                # 2. AJOUT DES CONFIGURATIONS DE SÉQUENCE SI APPLICABLE
                sequence_config = self._get_sequence_config(
                    plugin_name, 
                    current_count,
                    sequence_plugin_instances, 
                    existing_config
                )
                
                if sequence_config:
                    # Fusionner les configurations
                    for key, value in sequence_config.items():
                        if key == 'config' and isinstance(value, dict) and isinstance(config_data.get('config'), dict):
                            # Fusion profonde des dictionnaires de configuration
                            if 'config' not in config_data:
                                config_data['config'] = {}
                            config_data['config'].update(value)
                        else:
                            # Substitution directe pour les autres attributs
                            config_data[key] = value
                    
                    logger.debug(f"Configuration de séquence appliquée à {plugin_instance_id}")
                
                # 3. AJOUT DE LA CONFIGURATION EXISTANTE SI FOURNIE
                if existing_config:
                    config_data = self._merge_existing_config(config_data, existing_config)
                    logger.debug(f"Configuration existante appliquée à {plugin_instance_id}")
                
                # Stocker la configuration finale
                result_config[plugin_instance_id] = config_data
                
                logger.debug(f"Configuration finale pour {plugin_instance_id}: " +
                            f"{len(config_data.get('config', {}))} paramètres")
            
            # Mettre à jour la configuration courante
            self.current_config = result_config
            
            logger.debug("=== FIN FUSION DES CONFIGURATIONS ===")
            return result_config
            
        except Exception as e:
            logger.error(f"Erreur lors de l'application des configurations: {e}")
            logger.error(traceback.format_exc())
            return {}
    
    def _index_sequence_plugins_by_type(self) -> Dict[str, List[int]]:
        """
        Crée un index des instances de plugins dans la séquence par type.
        
        Returns:
            Dict[str, List[int]]: Mapping des noms de plugins vers leurs positions dans la séquence
        """
        result = {}
        
        if not self.sequence_data or 'plugins' not in self.sequence_data:
            return result
        
        for position, plugin_config in enumerate(self.sequence_data['plugins']):
            # Extraire le nom du plugin
            if isinstance(plugin_config, str):
                plugin_name = plugin_config
            elif isinstance(plugin_config, dict) and 'name' in plugin_config:
                plugin_name = plugin_config['name']
            else:
                logger.warning(f"Format de plugin invalide à la position {position}, ignoré")
                continue
            
            # Ajouter à l'index
            if plugin_name not in result:
                result[plugin_name] = []
            
            result[plugin_name].append(position)
        
        return result
    
    def _create_base_config(self, plugin_name: str, instance_id: Union[int, str]) -> Dict[str, Any]:
        """
        Crée une configuration de base pour un plugin.
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID d'instance
            
        Returns:
            Dict[str, Any]: Configuration de base
        """
        # Structure minimale de configuration
        base_config = {
            'plugin_name': plugin_name,
            'instance_id': instance_id,
            'config': {}  # Valeurs par défaut, seront remplacées plus tard
        }
        
        return base_config
    
    def _get_sequence_config(self, plugin_name: str, instance_index: int,
                        sequence_plugin_instances: Dict[str, List[int]],
                        existing_config: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """
        Récupère la configuration de séquence la plus appropriée pour un plugin.
        
        Args:
            plugin_name: Nom du plugin
            instance_index: Index de l'instance dans la liste des plugins sélectionnés
            sequence_plugin_instances: Mapping des noms de plugins vers leurs positions dans la séquence
            existing_config: Configuration existante du plugin (utilisée pour la correspondance)
            
        Returns:
            Optional[Dict[str, Any]]: Configuration de séquence ou None si non trouvée
        """
        try:
            # Cas 1: Le plugin n'est pas dans la séquence
            if plugin_name not in sequence_plugin_instances or not sequence_plugin_instances[plugin_name]:
                logger.debug(f"Aucune configuration de séquence pour {plugin_name}")
                return None
            
            # Cas 2: La configuration est déjà explicitement fournie
            if existing_config and 'from_sequence' in existing_config:
                seq_position = existing_config['from_sequence']
                if isinstance(seq_position, int) and 0 <= seq_position < len(self.sequence_data['plugins']):
                    matched_key = f"{plugin_name}_{seq_position}"
                    if matched_key in self._matched_plugins:
                        logger.warning(f"Configuration de séquence {seq_position} déjà utilisée pour {plugin_name}")
                        return None
                    
                    self._matched_plugins.add(matched_key)
                    logger.debug(f"Utilisation explicite de la configuration de séquence {seq_position} pour {plugin_name}")
                    
                    plugin_config = self.sequence_data['plugins'][seq_position]
                    if isinstance(plugin_config, str):
                        return {'plugin_name': plugin_name, 'config': {}}
                    return plugin_config
                else:
                    logger.warning(f"Position de séquence invalide: {seq_position}")
            
            # Cas 3: Tentative de correspondance automatique basée sur l'instance
            seq_positions = sequence_plugin_instances[plugin_name]
            
            # Si l'index d'instance est dans les limites des positions de séquence
            if instance_index < len(seq_positions):
                seq_position = seq_positions[instance_index]
                matched_key = f"{plugin_name}_{seq_position}"
                
                # Vérifier si cette configuration n'a pas déjà été utilisée
                if matched_key in self._matched_plugins:
                    logger.warning(f"Configuration de séquence {seq_position} déjà utilisée pour {plugin_name}")
                    return None
                
                self._matched_plugins.add(matched_key)
                
                # Récupérer la configuration depuis la séquence
                plugin_config = self.sequence_data['plugins'][seq_position]
                
                # Normaliser la configuration
                if isinstance(plugin_config, str):
                    # Format simple, juste le nom du plugin
                    return {'plugin_name': plugin_name, 'config': {}}
                elif isinstance(plugin_config, dict):
                    # Format dictionnaire, peut contenir une configuration
                    config_data = {'plugin_name': plugin_name}
                    
                    # Ajouter la configuration si présente
                    if 'config' in plugin_config and isinstance(plugin_config['config'], dict):
                        config_data['config'] = copy.deepcopy(plugin_config['config'])
                    elif 'variables' in plugin_config and isinstance(plugin_config['variables'], dict):
                        config_data['config'] = copy.deepcopy(plugin_config['variables'])
                    else:
                        config_data['config'] = {}
                    
                    # Copier les attributs spéciaux
                    self._copy_special_attributes(plugin_config, config_data)
                    
                    # Ajouter la référence à la position dans la séquence
                    config_data['from_sequence'] = seq_position
                    
                    return config_data
                else:
                    logger.warning(f"Format de configuration invalide pour {plugin_name} à la position {seq_position}")
                    return None
            else:
                logger.debug(f"Instance {instance_index} de {plugin_name} hors limites des positions de séquence {seq_positions}")
                return None
        
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de configuration de séquence: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _copy_special_attributes(self, source: Dict[str, Any], target: Dict[str, Any]) -> None:
        """
        Copie les attributs spéciaux d'une configuration source vers une cible.
        
        Args:
            source: Configuration source
            target: Configuration cible
        """
        special_keys = {
            'name', 'show_name', 'icon', 'remote_execution', 
            'template', 'ignore_errors', 'timeout', 'display_order'
        }
        
        for key in special_keys:
            if key in source:
                target[key] = source[key]
    
    def _merge_existing_config(self, base_config: Dict[str, Any], 
                             existing_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fusionne une configuration existante avec la configuration de base.
        La configuration existante a la priorité.
        
        Args:
            base_config: Configuration de base
            existing_config: Configuration existante à fusionner
            
        Returns:
            Dict[str, Any]: Configuration fusionnée
        """
        try:
            # Copie profonde pour éviter les modifications involontaires
            result = copy.deepcopy(base_config)
            
            # Fusionner les valeurs de configuration
            # Format 1: Configuration avec 'config'
            if 'config' in existing_config and isinstance(existing_config['config'], dict):
                if 'config' not in result:
                    result['config'] = {}
                result['config'].update(existing_config['config'])
            
            # Format 2: Configuration plate (ancienne structure)
            else:
                # Identifier les clés spéciales vs. les clés de configuration
                special_keys = {
                    'plugin_name', 'instance_id', 'name', 'show_name', 
                    'icon', 'remote_execution', 'template', 'from_sequence'
                }
                
                # Configuration plate: ajouter les clés non spéciales à 'config'
                if 'config' not in result:
                    result['config'] = {}
                
                for key, value in existing_config.items():
                    if key not in special_keys:
                        result['config'][key] = value
            
            # Copier les attributs spéciaux
            self._copy_special_attributes(existing_config, result)
            
            # Conserver les attributs d'identification
            for key in ['plugin_name', 'instance_id', 'from_sequence']:
                if key in existing_config:
                    result[key] = existing_config[key]
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors de la fusion de configurations: {e}")
            logger.error(traceback.format_exc())
            return base_config
    
    def get_normalized_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Récupère la configuration normalisée actuelle.
        
        Returns:
            Dict[str, Dict[str, Any]]: Configuration normalisée
        """
        return self.current_config
    
    def clear(self) -> None:
        """
        Réinitialise complètement le gestionnaire de configuration.
        """
        self.sequence_data = None
        self.sequence_configs = {}
        self.current_config = {}
        self._matched_plugins = set()
        logger.debug("Gestionnaire de configuration réinitialisé")