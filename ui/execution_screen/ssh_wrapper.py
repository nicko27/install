#!/usr/bin/env python3
"""
Script wrapper pour l'exécution SSH des plugins.
Ce script est exécuté sur la machine distante et gère l'exécution du plugin avec sudo si nécessaire.
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

# Créer un répertoire de logs temporaire avec les bonnes permissions
def ensure_log_dir():
    # Utiliser un répertoire temporaire accessible en écriture
    log_dir = os.path.join(tempfile.gettempdir(), 'pcUtils_logs')
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            print(f"Répertoire de logs créé: {log_dir}")
        except Exception as e:
            print(f"Erreur lors de la création du répertoire de logs: {e}")
            # Utiliser /tmp comme fallback
            log_dir = tempfile.gettempdir()
    
    # Définir la variable d'environnement pour que les plugins puissent trouver le répertoire de logs
    os.environ['PCUTILS_LOG_DIR'] = log_dir
    return log_dir

# Configurer le répertoire de logs
log_dir = ensure_log_dir()
log_file = os.path.join(log_dir, 'ssh_wrapper.log')

# Définir la variable d'environnement pour que les plugins puissent l'utiliser
os.environ['PCUTILS_LOG_DIR'] = log_dir
print(f"Variable d'environnement PCUTILS_LOG_DIR définie à: {log_dir}", flush=True)

# Configuration du logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def execute_command(cmd: str, sudo: bool = False, password: Optional[str] = None) -> Tuple[bool, str, str]:
    """Exécute une commande avec ou sans sudo"""
    try:
        # Vérifier si la commande contient des variables d'environnement
        env_vars = {}
        cmd_parts = cmd.split()
        cmd_to_execute = []
        
        # Extraire les variables d'environnement (format VAR=VALUE)
        for part in cmd_parts:
            if '=' in part and not part.startswith('-'):
                var_name, var_value = part.split('=', 1)
                env_vars[var_name] = var_value
            else:
                cmd_to_execute.append(part)
        
        # Obtenir l'environnement actuel et le mettre à jour avec nos variables
        env = os.environ.copy()
        env.update(env_vars)
        
        logger.debug(f"Exécution de la commande: {' '.join(cmd_to_execute)}")
        logger.debug(f"Variables d'environnement: {env_vars}")
        
        if sudo and password:
            # Utiliser sudo avec le mot de passe fourni
            process = subprocess.Popen(
                ['sudo', '-S'] + cmd_to_execute,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            stdout, stderr = process.communicate(input=f"{password}\n")
        else:
            # Exécuter la commande normalement
            process = subprocess.Popen(
                cmd_to_execute,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            stdout, stderr = process.communicate()
        
        success = process.returncode == 0
        return success, stdout, stderr
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de la commande: {e}")
        return False, "", str(e)

def main():
    """Fonction principale"""
    try:
        # Vérifier les arguments
        if len(sys.argv) != 2:
            logger.error("Usage: python3 ssh_wrapper.py <config_file>")
            sys.exit(1)
        
        config_file = sys.argv[1]
        
        # Vérifier que le fichier de configuration existe
        if not os.path.exists(config_file):
            logger.error(f"Le fichier de configuration n'existe pas: {config_file}")
            sys.exit(1)
        
        # S'assurer que le répertoire de logs existe et est accessible
        logger.debug(f"Répertoire de logs utilisé: {log_dir}")
            
        # Ajouter le répertoire parent au chemin Python pour trouver loading_utils
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)  # Remonter au répertoire parent
        if parent_dir not in sys.path:
            logger.debug(f"Ajout du répertoire parent au chemin Python: {parent_dir}")
            sys.path.append(parent_dir)
        else:
            logger.debug(f"Le répertoire parent est déjà dans le chemin Python: {parent_dir}")
        
        # Lire la configuration
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Erreur lors de la lecture du fichier de configuration: {e}")
            sys.exit(1)
        
        if not config:
            logger.error("Le fichier de configuration est vide")
            sys.exit(1)
        
        # Récupérer les paramètres de configuration
        plugin_path = config.get('plugin_path')
        plugin_config = config.get('plugin_config', {})
        needs_sudo = config.get('needs_sudo', False)
        root_password = config.get('root_password')
        
        if not plugin_path:
            logger.error("Chemin du plugin non spécifié dans la configuration")
            sys.exit(1)
        
        if not os.path.exists(plugin_path):
            logger.error(f"Le script du plugin n'existe pas: {plugin_path}")
            sys.exit(1)
        
        # Préparer la commande avec le chemin Python correct pour trouver loading_utils
        plugin_dir = os.path.dirname(plugin_path)
        parent_dir = os.path.dirname(plugin_dir)  # Remonter au répertoire parent où se trouve loading_utils
        
        # Construire la commande avec PYTHONPATH pour s'assurer que loading_utils est trouvé
        # La variable PCUTILS_LOG_DIR est déjà définie dans l'environnement
        pythonpath = f"PYTHONPATH={parent_dir}"
        cmd = f"{pythonpath} python3 {plugin_path} -c {config_file}"
        
        # Exécuter la commande
        success, stdout, stderr = execute_command(cmd, needs_sudo, root_password)
        
        if not success:
            logger.error(f"Erreur lors de l'exécution de la commande: {stderr}")
            sys.exit(1)
        
        # Afficher la sortie
        if stdout:
            print(stdout)
        if stderr:
            logger.warning(f"STDERR: {stderr}")
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 