#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import logging
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

def print_progress(step: int, total: int, message: str = ""):
    """Affiche la progression"""
    progress = int((step * 100) / total)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] "
          f"Progression : {progress}% (étape {step}/{total}) {message}")
    sys.stdout.flush()

def check_sudo():
    """Vérifie si le script a les privilèges sudo"""
    try:
        subprocess.run(['sudo', '-n', 'true'], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:
        # Vérifier les privilèges sudo
        if not check_sudo():
            return False, "Ce plugin nécessite des privilèges sudo. Veuillez relancer avec sudo."

        # Récupérer la configuration
        mysql_root_password = config.get('mysql_root_password')
        remove_test_db = config.get('remove_test_db', True)
        allow_remote_root = config.get('allow_remote_root', False)
        validate_password = config.get('validate_password', True)
        
        total_steps = 4
        current_step = 0
        
        # Étape 1: Installation de MySQL
        current_step += 1
        print_progress(current_step, total_steps, "Installation de MySQL")
        
        # Préparer les réponses pour debconf-set-selections
        debconf_settings = [
            'mysql-server mysql-server/root_password password ' + mysql_root_password,
            'mysql-server mysql-server/root_password_again password ' + mysql_root_password
        ]
        
        # Configurer les réponses automatiques
        for setting in debconf_settings:
            subprocess.run(['sudo', 'debconf-set-selections'], input=setting.encode(), check=True)
            
        # Installer MySQL
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'DEBIAN_FRONTEND=noninteractive', 'apt-get', 'install', '-y', 'mysql-server'], check=True)
        
        # Étape 2: Configuration de base
        current_step += 1
        print_progress(current_step, total_steps, "Configuration de base")
        
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
        print_progress(current_step, total_steps, "Application de la configuration")
        
        # Exécuter les commandes MySQL
        mysql_cmd = ['sudo', 'mysql', '-u', 'root', f'--password={mysql_root_password}']
        subprocess.run(mysql_cmd, input=mysql_secure.encode(), check=True)
        
        # Étape 4: Redémarrage du service
        current_step += 1
        print_progress(current_step, total_steps, "Redémarrage du service")
        subprocess.run(['sudo', 'systemctl', 'restart', 'mysql'], check=True)
        
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
