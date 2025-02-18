#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import logging
import threading
from datetime import datetime

# Configuration du logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BASE_DIR, "logs", "mysql_install.log")
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('mysql_install')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def print_progress(step: int, total: int):
    """Affiche la progression"""
    progress = int((step * 100) / total)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Progression : {progress}% (étape {step}/{total})")
    sys.stdout.flush()  # Forcer l'envoi immédiat des données

def run_command(cmd, input_data=None):
    """Exécute une commande en utilisant Popen"""
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_data else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(input=input_data)
    return process.returncode == 0, stdout, stderr

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:

        # Récupérer la configuration
        mysql_root_password = config.get('mysql_root_password')
        remove_test_db = config.get('remove_test_db', True)
        allow_remote_root = config.get('allow_remote_root', False)
        validate_password = config.get('validate_password', True)
        
        total_steps = 4
        current_step = 0
        
        # Étape 1: Installation de MySQL
        current_step += 1
        print_progress(current_step, total_steps)
        logger.info("Installation de MySQL")
        
        # Préparer les réponses pour debconf-set-selections
        debconf_settings = [
            'mysql-server mysql-server/root_password password ' + mysql_root_password,
            'mysql-server mysql-server/root_password_again password ' + mysql_root_password
        ]
        
        # Configurer les réponses automatiques
        for setting in debconf_settings:
            success, stdout, stderr = run_command(['debconf-set-selections'], setting)
            if not success:
                logger.error(f"Erreur lors de la configuration des réponses: {stderr}")
                return False, "Erreur lors de la configuration des réponses automatiques"
            logger.info("Configuration des réponses automatiques réussie")
        
        # Installer MySQL
        success, stdout, stderr = run_command(['apt-get', 'update'])
        if not success:
            logger.error(f"Erreur lors de la mise à jour: {stderr}")
            return False, "Erreur lors de la mise à jour des paquets"
            
        env = os.environ.copy()
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        success, stdout, stderr = run_command(['apt-get', 'install', '-y', 'mysql-server'])
        if not success:
            logger.error(f"Erreur lors de l'installation: {stderr}")
            return False, "Erreur lors de l'installation de MySQL"
        logger.info("Installation des paquets réussie")
        
        # Étape 2: Configuration de base
        current_step += 1
        print_progress(current_step, total_steps)
        logger.info("Configuration de base")
        
        # Préparer le script de configuration MySQL
        mysql_secure = f"""
        ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{mysql_root_password}';
        DELETE FROM mysql.user WHERE User='';
        """
        
        if remove_test_db:
            mysql_secure += """
            DROP DATABASE IF EXISTS test;
            DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';
            """
            
        if allow_remote_root:
            mysql_secure += f"""
            CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '{mysql_root_password}';
            GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
            """
            
        # Étape 3: Application de la configuration
        current_step += 1
        print_progress(current_step, total_steps)
        logger.info("Application de la configuration")
        
        # Exécuter les commandes MySQL
        mysql_cmd = ['mysql', '-u', 'root', f'--password={mysql_root_password}']
        success, stdout, stderr = run_command(mysql_cmd, mysql_secure)
        if not success:
            logger.error(f"Erreur lors de la configuration MySQL: {stderr}")
            return False, "Erreur lors de la configuration de MySQL"
        logger.info("Configuration de MySQL réussie")
        
        # Étape 4: Redémarrage du service
        current_step += 1
        print_progress(current_step, total_steps)
        logger.info("Redémarrage du service")
        
        success, stdout, stderr = run_command(['systemctl', 'restart', 'mysql'])
        if not success:
            logger.error(f"Erreur lors du redémarrage du service: {stderr}")
            return False, "Erreur lors du redémarrage de MySQL"
        logger.info("Redémarrage du service réussi")
        
        return True, "Installation et configuration de MySQL terminées avec succès"
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Erreur lors de l'exécution de la commande: {e}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        logger.exception(error_msg)
        return False, error_msg

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
