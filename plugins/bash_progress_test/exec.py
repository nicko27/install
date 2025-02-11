#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import logging

def execute_plugin(config):
    """
    Point d'entrée pour l'exécution du plugin Bash
    
    Args:
        config (dict): Configuration du plugin
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Récupérer le nom et l'intensité du test
        test_name = config.get('test_name', 'BashTest')
        test_intensity = config.get('test_intensity', 'light')
        
        # Chemin du script bash
        bash_script = os.path.join(os.path.dirname(__file__), 'main.sh')
        
        # Rendre le script exécutable
        subprocess.run(['chmod', '+x', bash_script], check=True)
        
        # Exécuter le script bash
        result = subprocess.run(
            [bash_script, test_name, test_intensity], 
            capture_output=True, 
            text=True
        )
        
        # Vérifier le code de retour
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    
    except Exception as e:
        logging.exception(f"Erreur lors de l'exécution du plugin Bash Progress Test")
        return False, f"Erreur d'exécution : {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: exec.py <config_json>")
        sys.exit(1)
        
    try:
        config = json.loads(sys.argv[1])
        success, message = execute_plugin(config)
        if success:
            print(f"Succès: {message}")
            sys.exit(0)
        else:
            print(f"Erreur: {message}")
            sys.exit(1)
    except json.JSONDecodeError:
        print("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur inattendue: {e}")
        sys.exit(1)
