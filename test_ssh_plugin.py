#!/usr/bin/env python3
"""
Script de test pour exécuter le plugin add_printer via SSH
et vérifier les chemins de logs utilisés.
"""

import os
import sys
import tempfile
import logging
import json
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

def main():
    """Fonction principale de test"""
    try:
        # Créer un répertoire temporaire pour les logs
        temp_dir = tempfile.mkdtemp(prefix="pcUtils_test_")
        log_dir = os.path.join(temp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        logger.info(f"Répertoire temporaire créé: {temp_dir}")
        logger.info(f"Répertoire de logs: {log_dir}")
        
        # Définir la variable d'environnement pour les logs
        os.environ["PCUTILS_LOG_DIR"] = log_dir
        logger.info(f"Variable d'environnement PCUTILS_LOG_DIR définie à: {log_dir}")
        
        # Chemin vers le plugin add_printer
        plugin_dir = os.path.abspath("plugins/add_printer")
        plugin_path = os.path.join(plugin_dir, "exec.py")
        
        # Créer une configuration de test
        config = {
            "plugin_name": "add_printer",
            "instance_id": 1,
            "ssh_mode": True,
            "printer_name": "TestPrinter",
            "printer_model": "KM301i",
            "printer_ip": "192.168.1.100",
            "printer_location": "Test Location"
        }
        
        # Écrire la configuration dans un fichier temporaire
        config_file = os.path.join(temp_dir, "test_config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Configuration écrite dans: {config_file}")
        
        # Exécuter le plugin avec la configuration
        cmd = f"PYTHONPATH={os.path.dirname(plugin_dir)} PCUTILS_LOG_DIR={log_dir} python3 {plugin_path} -c {config_file}"
        logger.info(f"Exécution de la commande: {cmd}")
        
        # Exécuter la commande
        exit_code = os.system(cmd)
        
        logger.info(f"Code de sortie: {exit_code}")
        
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
        
    except Exception as e:
        logger.error(f"Erreur lors du test: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
