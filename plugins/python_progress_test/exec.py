#!/usr/bin/env python3
import os
import sys
import logging
import importlib.util

# Importer dynamiquement le module main.py
spec = importlib.util.spec_from_file_location("main", os.path.join(os.path.dirname(__file__), "main.py"))
main_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_module)

def execute_plugin(config, progress_callback=None, status_callback=None):
    """
    Point d'entrée pour l'exécution du plugin
    
    Args:
        config (dict): Configuration du plugin
        progress_callback (callable): Fonction pour rapporter la progression (0-100)
        status_callback (callable): Fonction pour rapporter l'état du plugin
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Configurer les callbacks dans le module main
        main_module.set_callbacks(progress_callback, status_callback)
        
        # Utiliser la fonction execute_plugin du module main
        return main_module.execute_plugin(config)
    
    except Exception as e:
        logging.exception(f"Erreur lors de l'exécution du plugin Python Progress Test")
        if status_callback:
            status_callback("error", f"Erreur d'exécution : {str(e)}")
        return False, f"Erreur d'exécution : {str(e)}"

if __name__ == "__main__":
    # Pour les tests en ligne de commande
    import json
    
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
