import os
from ruamel.yaml import YAML
from ..logging import get_logger

logger = get_logger('plugin_utils')

# Création d'une instance YAML unique
yaml = YAML()

def get_plugin_folder_name(plugin_name: str) -> str:
    """Retourne le nom du dossier d'un plugin à partir de son nom.

    Args:
        plugin_name: Le nom du plugin (peut inclure l'ID d'instance)

    Returns:
        str: Le nom du dossier du plugin
    """
    # Extraire le nom de base du plugin (sans l'ID d'instance)
    base_name = plugin_name.split('_')[0] + '_' + plugin_name.split('_')[1]
    test_type = base_name + '_test'

    # Vérifier si la version test existe
    test_path = os.path.join('plugins', test_type)
    if os.path.exists(test_path):
        return test_type

    # Sinon retourner le nom de base
    return base_name

def load_plugin_info(plugin_name: str, default_info=None) -> dict:
    """Charge les informations d'un plugin depuis son fichier settings.yml

    Args:
        plugin_name: Le nom du plugin
        default_info: Informations par défaut en cas d'erreur

    Returns:
        dict: Les informations du plugin
    """
    if default_info is None:
        default_info = {"name": plugin_name, "description": "No description available", "icon": "📦"}

    folder_name = get_plugin_folder_name(plugin_name)
    settings_path = os.path.join('plugins', folder_name, 'settings.yml')

    try:
        with open(settings_path, 'r') as f:
            return yaml.load(f)
    except Exception as e:
        logger.error(f"Error loading plugin {plugin_name}: {e}")
        return default_info