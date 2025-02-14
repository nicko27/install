#!/usr/bin/env python3
import os
import sys
import json
import time
import random
import logging
from datetime import datetime

# Configuration du logging
LOG_FILE = "/media/nico/Drive/install/logs/python_progress_test.log"

# Créer un formateur personnalisé
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Configurer le logger
logger = logging.getLogger('python_progress_test')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Fonction pour écrire directement sur stdout (pour la progression)
def print_progress(step: int, total: int):
    progress = int((step * 100) / total)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Progression : {progress}% (étape {step}/{total})")

def run_python_test(test_name: str, test_intensity: str) -> bool:
    """
    Exécute le test Python avec progression
    
    Args:
        test_name: Nom du test
        test_intensity: Intensité du test (light, medium, heavy)
    
    Returns:
        bool: True si succès, False si échec
    """
    try:
        # Configuration basée sur l'intensité
        config = {
            'light': {'steps': 5, 'max_delay': 0.5, 'complexity': 1},
            'medium': {'steps': 10, 'max_delay': 1.0, 'complexity': 2},
            'heavy': {'steps': 20, 'max_delay': 2.0, 'complexity': 3}
        }
        
        if test_intensity not in config:
            logging.error(f"Intensité de test invalide : {test_intensity}")
            return False
            
        params = config[test_intensity]
        total_steps = params['steps']
        max_delay = params['max_delay']
        complexity = params['complexity']
        
        logger.info(f"Démarrage du test Python : {test_name}")
        logger.debug(f"Paramètres : steps={total_steps}, max_delay={max_delay}, complexity={complexity}")
        
        # Simulation des étapes avec progression
        for step in range(total_steps):
            # Simulation de travail
            delay = random.uniform(0, max_delay)
            time.sleep(delay)
            
            # Simulation de calculs
            for _ in range(1000 * complexity):
                _ = random.random() ** 2
            
            # Affichage de la progression
            print_progress(step + 1, total_steps)
            
            # Log détaillé
            logger.info(f"Étape {step + 1}/{total_steps} complétée")
            
            # Simulation d'erreur aléatoire (5% de chance)
            if random.random() < 0.05:
                logger.error(f"Erreur simulée à l'étape {step + 1}")
                return False
        
        logger.info(f"Test Python {test_name} terminé avec succès")
        return True
        
    except Exception as e:
        logger.exception(f"Erreur lors de l'exécution du test Python")
        return False

def execute_plugin(config):
    """
    Point d'entrée pour l'exécution du plugin
    
    Args:
        config (dict): Configuration du plugin
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        print(f"[DEBUG] Configuration reçue dans execute_plugin: {config}")
        
        # Récupérer les valeurs de configuration
        test_name = config.get('test_name', 'PythonTest')
        test_intensity = config.get('test_intensity', 'light')
        
        print(f"[DEBUG] Valeurs extraites: test_name={test_name}, test_intensity={test_intensity}")
        
        # Exécuter le test
        success = run_python_test(test_name, test_intensity)
        
        if success:
            return True, "Test Python terminé avec succès"
        else:
            return False, "Erreur lors de l'exécution du test Python"
            
    except Exception as e:
        logger.exception("Erreur lors de l'exécution du plugin Python Progress Test")
        return False, f"Erreur d'exécution : {str(e)}"

if __name__ == "__main__":
    # Lire la configuration depuis les arguments
    if len(sys.argv) != 2:
        print("[ERROR] Usage: python exec.py <config_json>")
        sys.exit(1)
        
    try:
        # Charger la configuration
        print(f"[DEBUG] Arguments reçus: {sys.argv}")
        config_json = sys.argv[1]
        print(f"[DEBUG] Configuration JSON reçue: {config_json}")
        
        config = json.loads(config_json)
        print(f"[DEBUG] Configuration chargée: {config}")
        
        # Exécuter le plugin
        success, message = execute_plugin(config)
        print(f"[DEBUG] Résultat: {success}, {message}")
        
        # Sortir avec le code approprié
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        sys.exit(1)
        
    try:
        # Charger la configuration depuis l'argument JSON
        config = json.loads(sys.argv[1])
        
        # Exécuter le plugin
        success, message = execute_plugin(config)
        
        # Sortir avec le code approprié
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Erreur : {str(e)}", file=sys.stderr)
        sys.exit(1)
