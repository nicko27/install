import argparse
import yaml
import os
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
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
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