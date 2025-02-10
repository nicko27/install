#!/usr/bin/env python3
import os
import json

def parse_model_file(file_path):
    """Parse un fichier de configuration d'imprimante au format shell"""
    config = {}
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    key, value = line.split('=', 1)
                    # Enlever les guillemets si présents
                    config[key] = value.strip('"')
                except ValueError:
                    continue
    return config

def get_printer_models():
    """Récupère la liste des modèles d'imprimantes depuis le répertoire des modèles"""
    # Utiliser le répertoire modeles de l'ancien script
    models_dir = "/media/nico/Drive/install.sh.extract/imprimantes/modeles"
    options = []
    
    if not os.path.exists(models_dir):
        return []
        
    for model_file in os.listdir(models_dir):
        model_path = os.path.join(models_dir, model_file)
        if os.path.isfile(model_path):
            config = parse_model_file(model_path)
            if 'title' in config:
                options.append({
                    "value": model_file,  # Utiliser le nom du fichier comme identifiant
                    "label": config['title']
                })
    
    # Trier par label
    options.sort(key=lambda x: x['label'])
    return options

if __name__ == "__main__":
    options = get_printer_models()
    print(json.dumps(options))
