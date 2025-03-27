#!/usr/bin/env python3
"""
Module d'aide à la configuration des plugins pcUtils.
Ce module permet de configurer les plugins à partir des arguments JSON.
"""

import json
import sys
import os

# Importer directement la classe PluginLogger depuis le module pluginlogger
from .pluginlogger import PluginLogger

def setup_plugin_from_args():
    """
    Configure un plugin en utilisant les arguments de ligne de commande.
    Retourne un tuple (config, logger)
    """
    # Vérifier si nous avons des arguments
    if len(sys.argv) < 2:
        print("Erreur: Aucune configuration fournie")
        sys.exit(1)
        
    # Récupérer l'argument JSON (le premier argument après le nom du script)
    json_config = sys.argv[1]
    
    # Charger la configuration
    try:
        config = json.loads(json_config)
    except json.JSONDecodeError as e:
        print(f"Erreur: Configuration JSON invalide: {str(e)}")
        sys.exit(1)
    
    # Initialiser le logger
    logger = PluginLogger(
        plugin_name=config.get("plugin_name"),
        instance_id=config.get("instance_id"),
        ssh_mode=config.get("ssh_mode", False)
    )
    
    # Définir le mode notextual si spécifié
    if "notextual" in config and config["notextual"]:
        logger.notextual = True
        logger.debug("Mode notextual activé via exec_utils")
    
    return config, logger

def load_json_file(file_path):
    """
    Charge un fichier JSON et retourne son contenu.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        print(f"Erreur: Fichier JSON invalide: {str(e)}")
        return None
    except Exception as e:
        print(f"Erreur lors du chargement du fichier JSON: {str(e)}")
        return None 