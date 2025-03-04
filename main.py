import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger

logger = get_logger('main')
logger.info('Starting application')

# Get the absolute path to the libs folder
# Assuming main.py is at the same level as the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Look for directories containing Python packages
    # Typically where .dist-info or .py files are stored
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Add the parent directory to the search path
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                logger.debug(f"Added {parent_dir} to sys.path")

        # Also add the main package directory to the path
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
            logger.debug(f"Added {pkg_dir} to sys.path")


import argparse
from ruamel.yaml import YAML
from ui.choice import Choice
from ui.executor import ExecutionScreen



def parse_args():
    parser = argparse.ArgumentParser(description='Install')
    parser.add_argument('--plugin', help='Exécuter directement un plugin spécifique')
    parser.add_argument('--config', help='Fichier de configuration pour le plugin')
    parser.add_argument('--params', nargs='*', help='Paramètres supplémentaires au format clé=valeur')
    return parser.parse_args()

def load_config(config_file):
    if not config_file:
        return {}
    yaml=YAML()
    try:
        with open(config_file, 'r') as f:
            return yaml.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return {}

def parse_params(params):
    if not params:
        return {}
    config = {}
    for param in params:
        try:
            key, value = param.split('=')
            config[key.strip()] = value.strip()
        except ValueError:
            print(f"Invalid format for parameter: {param}. Use key=value")
    return config

if __name__ == "__main__":
    args = parse_args()

    if args.plugin:
        # Direct execution of a plugin
        config = {}
        # Load configuration from file if specified
        if args.config:
            config.update(load_config(args.config))
        # Add command line parameters
        if args.params:
            config.update(parse_params(args.params))

        # Create plugin configuration
        plugins_config = {args.plugin: config}

        # Launch execution screen directly
        app = ExecutionScreen(plugins_config)
        app.run()
    else:
        # Normal selection interface
        app = Choice()
        app.run()
