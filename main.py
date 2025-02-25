import sys
import os
import glob
# Obtenir le chemin absolu du dossier libs
# Si main.py est au même niveau que le dossier libs
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Ajouter tous les sous-dossiers de libs au chemin de recherche
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Chercher les dossiers qui contiennent des packages Python
    # Typiquement, c'est là où les fichiers .dist-info ou .py sont stockés
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or 
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Ajouter le dossier parent au chemin de recherche
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
        
        # Aussi ajouter le dossier principal du package au chemin
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)


import argparse
from ruamel.yaml import YAML
from ui.choice import Choice
from ui.execution import ExecutionScreen



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
        print(f"Erreur lors du chargement de la configuration: {e}")
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
            print(f"Format invalide pour le paramètre: {param}. Utiliser clé=valeur")
    return config

if __name__ == "__main__":
    args = parse_args()
    
    if args.plugin:
        # Exécution directe d'un plugin
        config = {}
        # Charger la configuration depuis le fichier si spécifié
        if args.config:
            config.update(load_config(args.config))
        # Ajouter les paramètres de la ligne de commande
        if args.params:
            config.update(parse_params(args.params))
            
        # Créer la configuration du plugin
        plugins_config = {args.plugin: config}
        
        # Lancer directement l'écran d'exécution
        app = ExecutionScreen(plugins_config)
        app.run()
    else:
        # Interface normale de sélection
        app = Choice()
        app.run()
