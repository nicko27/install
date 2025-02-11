#!/usr/bin/env python3
import os
import sys
import logging
import time
import random
import json

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/media/nico/Drive/install/logs/python_progress_test.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PythonProgressTest:
    def __init__(self, config):
        """
        Initialise le gestionnaire de test de progression Python
        Args:
            config (dict): Configuration du test
        """
        logger.debug(f"Initialisation du test avec config : {config}")
        self.config = config
        self.test_name = config.get('test_name', 'PythonTest')
        self.test_complexity = config.get('test_complexity', 'simple')
        logger.info(f"Test configuré : nom={self.test_name}, complexité={self.test_complexity}")

    def run_test(self):
        """
        Exécute un test de progression avec différents niveaux de complexité
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Vérifier les champs requis
            if not self.test_name or not self.test_complexity:
                logger.error("Nom ou complexité de test manquant")
                return False, "Nom ou complexité de test manquant"

            logger.info(f" Démarrage du test Python : {self.test_name}")
            
            # Paramètres de test basés sur la complexité
            if self.test_complexity == 'simple':
                total_steps = 5
                max_delay = 0.5
                complexity_factor = 1
            elif self.test_complexity == 'moderate':
                total_steps = 10
                max_delay = 1.0
                complexity_factor = 2
            else:  # complex
                total_steps = 20
                max_delay = 2.0
                complexity_factor = 3

            logger.debug(f"Configuration du test : étapes={total_steps}, délai max={max_delay}, facteur={complexity_factor}")

            # Simulation de progression avec complexité
            for step in range(1, total_steps + 1):
                percentage = int(step * 100 / total_steps)
                logger.info(f"Progression : {percentage}% (étape {step}/{total_steps})")
                
                # Simulation de travail
                time.sleep(max_delay)
                
                # Simulation de calculs complexes
                for _ in range(1000 * complexity_factor):
                    random.random()

            logger.info(" Test Python terminé avec succès")
            return True, f"Test {self.test_name} terminé avec succès"
        
        except Exception as e:
            logger.exception("Erreur lors de l'exécution du test")
            return False, f"Erreur inattendue : {str(e)}"

def execute_plugin(config):
    """
    Point d'entrée du plugin de test de progression Python
    Args:
        config (dict): Configuration du plugin
    Returns:
        tuple: (success: bool, message: str)
    """
    logger.debug(f"Début de l'exécution du plugin avec config : {config}")
    try:
        # Créer une instance de PythonProgressTest
        test = PythonProgressTest(config)
        
        # Exécuter le test
        success, message = test.run_test()
        
        logger.info(f"Résultat du test : success={success}, message={message}")
        return success, message
    
    except Exception as e:
        logger.exception("Erreur lors de l'exécution du test Python")
        return False, f"Erreur inattendue : {str(e)}"

if __name__ == "__main__":
    # Pour les tests en ligne de commande
    logger.debug("Exécution en mode ligne de commande")
    
    # Logs détaillés sur les arguments
    logger.debug(f"sys.argv complet: {sys.argv}")
    logger.debug(f"Nombre d'arguments: {len(sys.argv)}")
    for i, arg in enumerate(sys.argv):
        logger.debug(f"Argument {i}: '{arg}'")
    
    # Récupérer le nom du script de manière robuste
    script_name = os.path.basename(sys.argv[0])
    logger.debug(f"Nom du script: {script_name}")
    logger.debug(f"Chemin complet du script: {sys.argv[0]}")
    
    # Informations supplémentaires de débogage
    logger.debug(f"Répertoire de travail courant: {os.getcwd()}")
    logger.debug(f"Chemin du script: {os.path.abspath(sys.argv[0])}")
    
    # Accepter un argument JSON ou des arguments séparés
    if len(sys.argv) == 2:
        try:
            # Essayer de charger comme JSON
            config = json.loads(sys.argv[1])
            logger.debug(f"Configuration chargée depuis JSON : {config}")
        except json.JSONDecodeError:
            # Si ce n'est pas un JSON valide, créer un dictionnaire avec les arguments
            config = {
                "test_name": sys.argv[1],
                "test_complexity": "simple"  # Valeur par défaut
            }
            logger.debug(f"Configuration créée à partir des arguments : {config}")
    elif len(sys.argv) == 3:
        # Deux arguments : nom du test et complexité
        config = {
            "test_name": sys.argv[1],
            "test_complexity": sys.argv[2]
        }
        logger.debug(f"Configuration créée à partir de deux arguments : {config}")
    else:
        logger.error(f"Arguments invalides. Usage: {script_name} <test_name> [test_complexity]")
        print(f"Usage: {script_name} <test_name> [test_complexity]")
        sys.exit(1)
    
    try:
        success, message = execute_plugin(config)
        if success:
            logger.info(f"Succès: {message}")
            print(f"Succès: {message}")
            sys.exit(0)
        else:
            logger.error(f"Erreur: {message}")
            print(f"Erreur: {message}")
            sys.exit(1)
    except Exception as e:
        logger.exception("Erreur inattendue")
        print(f"Erreur inattendue: {e}")
        sys.exit(1)
