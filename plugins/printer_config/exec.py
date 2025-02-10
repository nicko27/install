#!/usr/bin/env python3
import os
import sys
import logging
from printer_actions import PrinterManager

logger = logging.getLogger(__name__)

def execute_plugin(config):
    """
    Point d'entrée du plugin d'ajout d'imprimante
    Args:
        config (dict): Configuration du plugin avec les champs:
            - printer_name: Nom de l'imprimante (sans espaces)
            - printer_model: Modèle d'imprimante
            - printer_ip: Adresse IP de l'imprimante
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Vérifier que tous les champs requis sont présents
        required_fields = ['printer_name', 'printer_model', 'printer_ip']
        for field in required_fields:
            if not config.get(field):
                return False, f"Le champ {field} est requis"

        # Vérifier que le nom ne contient pas d'espaces
        if ' ' in config['printer_name']:
            return False, "Le nom de l'imprimante ne doit pas contenir d'espaces"

        # Exécuter l'ajout de l'imprimante
        manager = PrinterManager(config)
        success, message = manager.add_local_printer()

        if success:
            logger.info(f"Imprimante {config['printer_name']} ajoutée avec succès")
        else:
            logger.error(f"Erreur lors de l'ajout de l'imprimante: {message}")

        return success, message

    except Exception as e:
        logger.exception("Erreur inattendue lors de l'ajout de l'imprimante")
        return False, f"Erreur: {str(e)}"

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
