#!/usr/bin/env python3
"""
Script de test pour vérifier l'exécution du plugin add_printer
en mode local et SSH avec la nouvelle gestion des logs.
"""

import os
import sys
import json
import tempfile
import logging
import subprocess
import time
from pathlib import Path

# Configurer le logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def test_local_execution():
    """Teste l'exécution locale du plugin"""
    logger.info("=== TEST EXÉCUTION LOCALE ===")
    
    try:
        # Créer un répertoire temporaire pour les logs
        temp_dir = tempfile.mkdtemp(prefix="pcUtils_test_local_")
        log_dir = os.path.join(temp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        logger.info(f"Répertoire temporaire créé: {temp_dir}")
        logger.info(f"Répertoire de logs: {log_dir}")
        
        # Définir la variable d'environnement pour les logs
        os.environ["PCUTILS_LOG_DIR"] = log_dir
        
        # Chemin vers le plugin add_printer
        plugin_dir = os.path.abspath("plugins/add_printer")
        plugin_path = os.path.join(plugin_dir, "exec.py")
        
        # Créer une configuration de test pour le mode local
        config = {
            "plugin_name": "add_printer",
            "instance_id": 1,
            "printer_name": "TestPrinter",
            "printer_model": "KM301i",
            "printer_ip": "192.168.1.100",
            "printer_location": "Test Location"
        }
        
        # Convertir la configuration en JSON
        config_json = json.dumps(config)
        
        # Exécuter le plugin avec la configuration en mode local
        cmd = f"PYTHONPATH={os.path.dirname(plugin_dir)} python3 {plugin_path} '{config_json}'"
        logger.info(f"Exécution de la commande: {cmd}")
        
        # Exécuter la commande
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            env=dict(os.environ, PCUTILS_LOG_DIR=log_dir)
        )
        
        stdout, stderr = process.communicate()
        exit_code = process.returncode
        
        logger.info(f"Code de sortie: {exit_code}")
        
        if stdout:
            logger.info(f"STDOUT:\n{stdout.decode()}")
        if stderr:
            logger.error(f"STDERR:\n{stderr.decode()}")
        
        # Vérifier les fichiers de logs créés
        logger.info("Fichiers de logs créés:")
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                log_file_path = os.path.join(root, file)
                logger.info(f"  - {log_file_path} ({os.path.getsize(log_file_path)} octets)")
                
                # Afficher le contenu du fichier de log
                with open(log_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    logger.info(f"Contenu du fichier {log_file_path}:")
                    logger.info(content)
        
        return exit_code == 0
        
    except Exception as e:
        logger.error(f"Erreur lors du test d'exécution locale: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_ssh_execution():
    """Teste l'exécution SSH du plugin (simulation)"""
    logger.info("=== TEST EXÉCUTION SSH (SIMULATION) ===")
    
    try:
        # Créer un répertoire temporaire pour les logs
        temp_dir = tempfile.mkdtemp(prefix="pcUtils_test_ssh_")
        log_dir = os.path.join(temp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        logger.info(f"Répertoire temporaire créé: {temp_dir}")
        logger.info(f"Répertoire de logs: {log_dir}")
        
        # Définir la variable d'environnement pour les logs
        os.environ["PCUTILS_LOG_DIR"] = log_dir
        
        # Chemin vers le plugin add_printer
        plugin_dir = os.path.abspath("plugins/add_printer")
        plugin_path = os.path.join(plugin_dir, "exec.py")
        
        # Vérifier si le répertoire printer_models existe
        printer_models_dir = os.path.join(plugin_dir, "printer_models")
        if not os.path.exists(printer_models_dir):
            os.makedirs(printer_models_dir, exist_ok=True)
            logger.info(f"Création du répertoire des modèles d'imprimantes: {printer_models_dir}")
            
            # Créer un fichier modèle pour le test
            model_file = os.path.join(printer_models_dir, "KM301i.yml")
            with open(model_file, "w", encoding="utf-8") as f:
                f.write("""couleurs: 1
rectoverso: 1
ppdFile: KM301i.ppd
agraffes: 0
orecto: -o sides=one-sided
orectoverso: -o sides=two-sided-long-edge
onb: -o ColorModel=Gray
ocouleurs: -o ColorModel=CMYK
oagraffes: """)            
            logger.info(f"Fichier modèle créé: {model_file}")
        
        # Créer une configuration de test pour le mode SSH
        config = {
            "plugin_name": "add_printer",
            "instance_id": 2,
            "ssh_mode": True,
            "config": {
                "printer_name": "TestPrinterSSH",
                "printer_model": "KM301i",
                "printer_ip": "192.168.1.200",
                "printer_location": "Test Location SSH"
            }
        }
        
        # Vérifier si le module get_printer_models existe
        get_printer_models_path = os.path.join(plugin_dir, "get_printer_models.py")
        if not os.path.exists(get_printer_models_path):
            logger.info(f"Création du module get_printer_models.py")
            with open(get_printer_models_path, "w", encoding="utf-8") as f:
                f.write("""
import os
import yaml

def get_printer_model(model_name, models_dir):
    \"\"\"Récupère les informations d'un modèle d'imprimante.
    
    Args:
        model_name: Nom du modèle d'imprimante
        models_dir: Répertoire contenant les fichiers de modèles
        
    Returns:
        Dictionnaire contenant les informations du modèle, ou None si le modèle n'existe pas
    \"\"\"
    try:
        model_file = os.path.join(models_dir, f"{model_name}.yml")
        if not os.path.exists(model_file):
            return None
            
        with open(model_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors de la récupération du modèle: {e}")
        return None
""")
        
        # Écrire la configuration dans un fichier temporaire
        config_file = os.path.join(temp_dir, "test_config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Configuration écrite dans: {config_file}")
        
        # Exécuter le plugin avec la configuration en mode SSH
        cmd = f"PYTHONPATH={os.path.dirname(plugin_dir)} python3 {plugin_path} -c {config_file}"
        logger.info(f"Exécution de la commande: {cmd}")
        
        # Exécuter la commande
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            env=dict(os.environ, PCUTILS_LOG_DIR=log_dir)
        )
        
        stdout, stderr = process.communicate()
        exit_code = process.returncode
        
        logger.info(f"Code de sortie: {exit_code}")
        
        if stdout:
            logger.info(f"STDOUT:\n{stdout.decode()}")
        if stderr:
            logger.error(f"STDERR:\n{stderr.decode()}")
        
        # Vérifier les fichiers de logs créés
        logger.info("Fichiers de logs créés:")
        for root, dirs, files in os.walk(log_dir):
            for file in files:
                log_file_path = os.path.join(root, file)
                logger.info(f"  - {log_file_path} ({os.path.getsize(log_file_path)} octets)")
                
                # Afficher le contenu du fichier de log
                with open(log_file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    logger.info(f"Contenu du fichier {log_file_path}:")
                    logger.info(content)
        
        return exit_code == 0
        
    except Exception as e:
        logger.error(f"Erreur lors du test d'exécution SSH: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Fonction principale"""
    success_local = test_local_execution()
    time.sleep(1)  # Pause entre les tests
    success_ssh = test_ssh_execution()
    
    logger.info("\n=== RÉSUMÉ DES TESTS ===")
    logger.info(f"Test d'exécution locale: {'SUCCÈS' if success_local else 'ÉCHEC'}")
    logger.info(f"Test d'exécution SSH: {'SUCCÈS' if success_ssh else 'ÉCHEC'}")
    
    return 0 if success_local and success_ssh else 1

if __name__ == "__main__":
    sys.exit(main())
