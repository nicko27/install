#!/usr/bin/env python3
import os
import json
import traceback
from ruamel.yaml import YAML


def parse_model_file(file_path):
    """Parse un fichier de configuration d'imprimante au format YAML
    
    Args:
        file_path (str): Chemin vers le fichier YAML à parser
        
    Returns:
        tuple(bool, dict): Tuple contenant:
            - True et le dictionnaire de configuration en cas de succès
            - False et un message d'erreur en cas d'échec
    """
    yaml = YAML()
    try:
        with open(file_path, 'r') as f:
            config = yaml.load(f)
            return True, config
    except yaml.YAMLError as e:
        error_msg = f"Erreur lors de la lecture du fichier YAML {file_path}: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return False, error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la lecture du fichier {file_path}: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return False, error_msg


def get_printer_models():
    """Récupère la liste des modèles d'imprimantes depuis le répertoire des modèles
    
    Returns:
        tuple(bool, list): Tuple contenant:
            - True et la liste des modèles d'imprimantes en cas de succès
            - False et un message d'erreur en cas d'échec
    """
    try:
        # Utiliser le répertoire modeles relatif au script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(script_dir, "models")
        print(f"Dossier des modèles: {models_dir}")
        options = []
        
        if not os.path.exists(models_dir):
            print("Le dossier des modèles n'existe pas")
            return True, []
            
        for model_file in os.listdir(models_dir):
            if not model_file.endswith('.yml'):
                continue
                
            model_path = os.path.join(models_dir, model_file)
            if os.path.isfile(model_path):
                print(f"Lecture du fichier {model_path}")
                success, config = parse_model_file(model_path)
                if not success:
                    print(f"Erreur lors du parsing de {model_path}: {config}")
                    continue
                    
                print(f"Contenu du fichier {model_path}: {config}")
                if 'title' in config:
                    # Créer un dictionnaire avec les clés attendues
                    model_name = model_file
                    options.append({
                        'description': config['title'],
                        'value': model_name
                    })
                    print(f"Ajout du modèle {model_name} avec titre {config['title']}")
        
        # Trier par description
        options.sort(key=lambda x: x['description'])
        print(f"Liste finale des options: {options}")
        return True, options
        
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des modèles d'imprimantes: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return False, error_msg
