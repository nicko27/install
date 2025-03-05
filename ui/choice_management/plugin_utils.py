import os
from ruamel.yaml import YAML
from ..logging import get_logger

logger = get_logger('plugin_utils')

# Création d'une instance YAML unique
yaml = YAML()

def get_plugin_folder_name(plugin_name: str) -> str:
    """Retourne le nom du dossier d'un plugin à partir de son nom"""
    logger.debug(f"Getting folder name for plugin: {plugin_name}")

    # S'assurer que plugin_name a au moins deux parties séparées par des underscores
    parts = plugin_name.split('_')
    if len(parts) < 2:
        logger.warning(f"  Plugin name {plugin_name} doesn't have expected format (name_type_id)")
        return plugin_name

    # Extraire le nom de base du plugin (sans l'ID d'instance)
    base_name = parts[0] + '_' + parts[1]
    test_type = base_name + '_test'

    # Vérifier si la version test existe
    test_path = os.path.join('plugins', test_type)
    exists_test = os.path.exists(test_path)
    logger.debug(f"  Test path: {test_path} (exists: {exists_test})")

    # Vérifier si la version base existe
    base_path = os.path.join('plugins', base_name)
    exists_base = os.path.exists(base_path)
    logger.debug(f"  Base path: {base_path} (exists: {exists_base})")

    if exists_test:
        logger.debug(f"  Returning test folder name: {test_type}")
        return test_type

    # Sinon retourner le nom de base
    logger.debug(f"  Returning base folder name: {base_name}")
    return base_name

def load_plugin_info(plugin_name: str, default_info=None) -> dict:
    """Charge les informations d'un plugin depuis son fichier settings.yml"""
    logger.debug(f"Loading plugin info for: {plugin_name}")

    if default_info is None:
        default_info = {"name": plugin_name, "description": "No description available", "icon": "📦"}

    folder_name = get_plugin_folder_name(plugin_name)
    settings_path = os.path.join('plugins', folder_name, 'settings.yml')

    logger.debug(f"  Folder name: {folder_name}")
    logger.debug(f"  Settings path: {settings_path} (exists: {os.path.exists(settings_path)})")

    try:
        with open(settings_path, 'r') as f:
            settings = yaml.load(f)
            logger.debug(f"  Successfully loaded settings for {plugin_name}")
            return settings
    except Exception as e:
        logger.error(f"Error loading plugin {plugin_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return default_info