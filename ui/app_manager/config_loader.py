"""
Module de chargement des configurations.
"""

from ruamel.yaml import YAML
from ..utils.logging import get_logger

logger = get_logger('config_loader')
yaml = YAML()

class ConfigLoader:
    """Chargement des configurations"""
    
    @staticmethod
    def load_config(config_file):
        """Charge un fichier de configuration YAML"""
        if not config_file:
            return {}
            
        try:
            with open(config_file, 'r') as f:
                return yaml.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la configuration: {e}")
            return {}
            
    @staticmethod
    def parse_params(params):
        """Parse les paramètres de ligne de commande"""
        if not params:
            return {}
            
        config = {}
        for param in params:
            try:
                key, value = param.split('=')
                config[key.strip()] = value.strip()
            except ValueError:
                logger.error(f"Format invalide pour le paramètre: {param}. Utilisez key=value")
                
        return config
