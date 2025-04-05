"""
Module pour la configuration automatique des plugins.

Ce module permet de charger et de traiter automatiquement
les configurations des plugins à partir de fichiers de séquence.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Union
from ruamel.yaml import YAML
from ..utils.logging import get_logger

logger = get_logger('auto_config')

# Tenter d'importer PluginInstance depuis choice_screen
# Si l'import échoue, créer une classe PluginInstance compatible
from ..choice_screen.choice_screen import PluginInstance


class AutoConfig:
    """
    Gestionnaire de configuration automatique pour les plugins.
    
    Cette classe est responsable de:
    - Charger les configurations depuis des séquences sauvegardées
    - Appliquer des configurations par défaut
    - Combiner plusieurs sources de configuration
    """
    
    def __init__(self):
        """Initialise le gestionnaire de configuration automatique."""
        self.yaml = YAML()
        self.config_dir = Path('configs')
        self.auto_config_cache = {}  # Cache pour les configurations
        
        # Créer le dossier de configuration s'il n'existe pas
        if not self.config_dir.exists():
            try:
                self.config_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Dossier de configuration créé: {self.config_dir}")
            except Exception as e:
                logger.error(f"Impossible de créer le dossier de configuration: {e}")
                
        logger.debug("Initialisation du gestionnaire de configuration automatique")
        
    def process_sequence(self, sequence_file: Union[str, Path], plugins: List) -> Dict[str, Dict[str, Any]]:
        """
        Traite une séquence et génère la configuration pour chaque plugin.
        
        Args:
            sequence_file: Chemin vers le fichier de séquence
            plugins: Liste des plugins (tuples ou PluginInstance)
            
        Returns:
            Dict[str, Dict[str, Any]]: Configuration pour chaque plugin, indexée par clé unique
        """
        # Convertir en Path si nécessaire
        if isinstance(sequence_file, str):
            sequence_file = Path(sequence_file)
            
        logger.debug(f"Traitement de la séquence: {sequence_file}")
        
        # Initialiser la configuration
        config = {}
        
        # Charger la séquence
        sequence = self._load_sequence(sequence_file)
        if not sequence:
            logger.error(f"Impossible de charger la séquence: {sequence_file}")
            return config
            
        # Charger les configurations spécifiques pour cette séquence
        sequence_config = self._load_sequence_config(sequence_file)
        
        # Récupérer les plugins de la séquence
        sequence_plugins = sequence.get('plugins', [])
        
        # Traiter chaque plugin
        for plugin_data in plugins:
            # Déterminer le nom et l'ID du plugin selon le type
            if isinstance(plugin_data, tuple):
                plugin_name = plugin_data[0]
                instance_id = plugin_data[1]
            else:  # Si c'est un PluginInstance
                plugin_name = plugin_data.name
                instance_id = plugin_data.instance_id
                
            # Ignorer les séquences
            if plugin_name.startswith('__sequence__'):
                continue
                
            # Créer la clé unique pour ce plugin
            plugin_key = f"{plugin_name}_{instance_id}"
            
            # Initialiser la configuration pour ce plugin
            plugin_config = {}
            
            # Chercher ce plugin dans la séquence
            for i, seq_plugin in enumerate(sequence_plugins):
                # Extraire le nom du plugin selon le format
                if isinstance(seq_plugin, dict) and 'name' in seq_plugin:
                    seq_plugin_name = seq_plugin['name']
                    seq_plugin_config = seq_plugin.get('config', {})
                elif isinstance(seq_plugin, str):
                    seq_plugin_name = seq_plugin
                    seq_plugin_config = {}
                else:
                    logger.warning(f"Format de plugin non reconnu dans la séquence, index {i}")
                    continue
                    
                # Si le plugin correspond, appliquer la configuration de la séquence
                if seq_plugin_name == plugin_name:
                    logger.debug(f"Configuration trouvée dans la séquence pour {plugin_name}")
                    plugin_config.update(seq_plugin_config)
                    break
                    
            # Appliquer la configuration spécifique si disponible
            if plugin_name in sequence_config:
                logger.debug(f"Configuration spécifique trouvée pour {plugin_name}")
                plugin_config.update(sequence_config[plugin_name])
                
            # Stocker la configuration
            config[plugin_key] = plugin_config
            
        return config
        
    def _load_sequence(self, sequence_file: Path) -> Optional[Dict[str, Any]]:
        """
        Charge une séquence depuis un fichier YAML.
        
        Args:
            sequence_file: Chemin vers le fichier de séquence
            
        Returns:
            Optional[Dict[str, Any]]: Données de la séquence ou None si erreur
        """
        try:
            if not sequence_file.exists():
                logger.error(f"Fichier de séquence non trouvé: {sequence_file}")
                return None
                
            # Vérifier si la séquence est déjà en cache
            cache_key = str(sequence_file)
            if cache_key in self.auto_config_cache:
                logger.debug(f"Séquence trouvée dans le cache: {sequence_file}")
                return self.auto_config_cache[cache_key]
                
            # Charger la séquence
            with open(sequence_file, 'r', encoding='utf-8') as f:
                sequence = self.yaml.load(f)
                
            # Vérifier que la séquence est valide
            if not isinstance(sequence, dict) or 'plugins' not in sequence:
                logger.error(f"Format de séquence invalide dans {sequence_file}")
                return None
                
            # Mettre en cache
            self.auto_config_cache[cache_key] = sequence
            
            return sequence
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_file}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def _load_sequence_config(self, sequence_file: Path) -> Dict[str, Dict[str, Any]]:
        """
        Charge la configuration spécifique pour une séquence.
        
        Args:
            sequence_file: Chemin vers le fichier de séquence
            
        Returns:
            Dict[str, Dict[str, Any]]: Configuration par plugin
        """
        config = {}
        
        # Déterminer le nom de base de la séquence
        sequence_name = sequence_file.stem
        
        # Chercher un fichier de configuration
        config_file = self.config_dir / f"{sequence_name}.yml"
        
        # Si le fichier existe, le charger
        if config_file.exists():
            try:
                logger.debug(f"Chargement de la configuration spécifique: {config_file}")
                with open(config_file, 'r', encoding='utf-8') as f:
                    specific_config = self.yaml.load(f)
                    
                # Vérifier que la configuration est valide
                if isinstance(specific_config, dict):
                    config = specific_config
                else:
                    logger.warning(f"Format de configuration invalide dans {config_file}")
            except Exception as e:
                logger.error(f"Erreur lors du chargement de la configuration {config_file}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
        return config
        
    def save_sequence_config(self, sequence_file: Union[str, Path], config: Dict[str, Dict[str, Any]]) -> bool:
        """
        Sauvegarde la configuration pour une séquence.
        
        Args:
            sequence_file: Chemin vers le fichier de séquence
            config: Configuration par plugin
            
        Returns:
            bool: True si la sauvegarde a réussi
        """
        # Convertir en Path si nécessaire
        if isinstance(sequence_file, str):
            sequence_file = Path(sequence_file)
            
        # Déterminer le nom de base de la séquence
        sequence_name = sequence_file.stem
        
        # Déterminer le chemin du fichier de configuration
        config_file = self.config_dir / f"{sequence_name}.yml"
        
        try:
            # Créer le dossier parent si nécessaire
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Restructurer la configuration pour l'adapter au format de fichier
            # On veut stocker par nom de plugin au lieu de plugin_key
            plugin_configs = {}
            
            for plugin_key, plugin_config in config.items():
                # Extraire le nom du plugin à partir de la clé
                plugin_name = plugin_key.rsplit('_', 1)[0]
                
                # Stocker la configuration
                plugin_configs[plugin_name] = plugin_config
                
            # Sauvegarder la configuration
            with open(config_file, 'w', encoding='utf-8') as f:
                self.yaml.dump(plugin_configs, f)
                
            logger.info(f"Configuration sauvegardée: {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de la configuration {config_file}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    def get_plugin_config(self, plugin_name: str, instance_id: int = 0) -> Dict[str, Any]:
        """
        Récupère la configuration pour un plugin spécifique.
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID de l'instance
            
        Returns:
            Dict[str, Any]: Configuration du plugin
        """
        # Créer une clé unique pour ce plugin
        plugin_key = f"{plugin_name}_{instance_id}"
        
        # Chercher dans les configurations spécifiques
        for cache_key, sequence in self.auto_config_cache.items():
            if isinstance(sequence, dict) and 'plugins' in sequence:
                for seq_plugin in sequence['plugins']:
                    # Extraire le nom du plugin selon le format
                    if isinstance(seq_plugin, dict) and 'name' in seq_plugin:
                        seq_plugin_name = seq_plugin['name']
                        seq_plugin_config = seq_plugin.get('config', {})
                    elif isinstance(seq_plugin, str):
                        seq_plugin_name = seq_plugin
                        seq_plugin_config = {}
                    else:
                        continue
                        
                    # Si le plugin correspond, retourner sa configuration
                    if seq_plugin_name == plugin_name:
                        return seq_plugin_config
                        
        # Si aucune configuration n'a été trouvée, retourner un dictionnaire vide
        return {}
        
    def clear_cache(self) -> None:
        """
        Vide le cache des configurations.
        Utile pour les tests ou après des modifications externes.
        """
        self.auto_config_cache.clear()
        logger.debug("Cache des configurations vidé")