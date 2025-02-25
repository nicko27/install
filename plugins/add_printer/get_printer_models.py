#!/usr/bin/env python3
import os
import json
from ruamel.yaml import YAML


def parse_model_file(file_path):
    """Parse un fichier de configuration d'imprimante au format YAML"""
    yaml = YAML()
    with open(file_path, 'r') as f:
        try:
            return yaml.load(f)
        except yaml.YAMLError as e:
            print(f"Erreur lors de la lecture du fichier YAML {file_path}: {e}")
            return {}


def get_printer_models():
    """Récupère la liste des modèles d'imprimantes depuis le répertoire des modèles"""
    # Utiliser le répertoire modeles relatif au script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, "models")
    options = []
    
    if not os.path.exists(models_dir):
        return []
        
    for model_file in os.listdir(models_dir):
        if not model_file.endswith('.yml'):
            continue
            
        model_path = os.path.join(models_dir, model_file)
        if os.path.isfile(model_path):
            config = parse_model_file(model_path)
            if 'title' in config:
                # Enlever l'extension .yml du nom du fichier pour la valeur
                model_name = model_file
                options.append((config['title'], model_name))
    
    # Trier par label (premier élément du tuple)
    options.sort(key=lambda x: x[0])
    return options

if __name__ == "__main__":
    options = get_printer_models()
    print(json.dumps(options))
