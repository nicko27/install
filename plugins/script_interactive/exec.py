#!/usr/bin/env python3
import os
import sys
import json
import time
import pexpect
import logging
from datetime import datetime

# Configuration du logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BASE_DIR, "logs", "script_interactive.log")
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('script_interactive')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def print_progress(step: int, total: int, message: str = None):
    """Affiche la progression"""
    progress = int((step * 100) / total)
    msg = f"Progression : {progress}% (étape {step}/{total})"
    if message:
        msg += f" - {message}"
    logger.info(msg)
    sys.stdout.flush()

def config_to_responses(config):
    """Convertit la configuration en liste de réponses."""
    responses = []
    
    # Réponse pour le serveur web
    install_web = config.get('install_web_server', True)
    responses.append('o' if install_web else 'n')
    
    if install_web:
        # Port du serveur web
        port = str(config.get('web_server_port', 80))
        responses.append(port)
        
        # Support PHP
        enable_php = config.get('enable_php', True)
        responses.append('o' if enable_php else 'n')
        
        if enable_php:
            # Version PHP
            php_version = config.get('php_version', '8.1')
            responses.append(php_version)
    else:
        # Type de base de données
        db_type = config.get('db_type', 'mysql')
        responses.append(db_type)
        
        # Port de la base de données
        db_port = str(config.get('db_port', 3306 if db_type == 'mysql' else 5432))
        responses.append(db_port)
        
        # Mot de passe root
        db_password = config.get('db_root_password', '')
        responses.append(db_password)
    
    # Confirmation finale
    confirm = config.get('confirm_config', True)
    responses.append('o' if confirm else 'n')
    
    return responses

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin."""
    try:
        logger.info("Démarrage de l'exécution du script interactif")
        
        # Chemin du script dans le dossier du plugin
        script_path = os.path.join(os.path.dirname(__file__), 'test_script.sh')
        if not os.path.exists(script_path):
            raise ValueError(f"Script introuvable: {script_path}")
        
        # Convertir la configuration en réponses
        responses = config_to_responses(config)
        total_steps = len(responses) * 2  # Questions + Réponses
        current_step = 0
        
        # Utiliser pexpect avec un buffer plus grand
        child = pexpect.spawn(f'bash {script_path}', encoding='utf-8')
        
        # Pour chaque réponse attendue
        for i, response in enumerate(responses, 1):
            # Attendre une sortie
            current_step += 1
            print_progress(current_step, total_steps, "Attente de la question...")
            
            index = child.expect(['.*\n', pexpect.EOF, pexpect.TIMEOUT])
            if index != 0:
                raise RuntimeError("Le script s'est terminé ou ne répond pas")
            
            # Récupérer la sortie
            output = child.before + child.after
            logger.info(f"Question : {output.strip()}")
            
            # Envoyer la réponse
            current_step += 1
            # Masquer le mot de passe dans les logs
            displayed_response = '****' if 'mot de passe' in output.lower() else response
            print_progress(current_step, total_steps, f"Réponse : {displayed_response}")
            
            child.sendline(response)
            time.sleep(0.5)  # Petite pause pour la lisibilité
        
        # Attendre la fin du script
        child.expect(pexpect.EOF)
        
        # Vérifier le code de retour
        child.close()
        if child.exitstatus == 0:
            logger.info("Exécution terminée avec succès")
            return True
        else:
            raise RuntimeError(f"Le script a retourné le code {child.exitstatus}")
            
    except Exception as e:
        error_msg = f"Erreur lors de l'exécution : {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: exec.py <config_json>")
        sys.exit(1)
        
    try:
        config = json.loads(sys.argv[1])
        execute_plugin(config)
    except Exception as e:
        logger.error(f"Erreur : {str(e)}")
        sys.exit(1)
