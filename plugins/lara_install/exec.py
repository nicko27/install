#!/usr/bin/env python3
"""
Plugin pour l'ajout d'imprimantes à un système Linux.
Utilise CUPS via lpadmin pour configurer différentes options d'impression.
"""
import json
import time
import traceback
# Configuration du chemin d'import pour trouver les modules communs
import sys
import os

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import du module d'aide à l'import
from loading_utils.import_helper import setup_import_paths

# Configurer les chemins d'import
setup_import_paths()

# Maintenant on peut importer tous les éléments du module loading_utils
from loading_utils import *

# Initialiser le logger du plugin
log = PluginLogger()

# Initialiser les gestionnaires de commandes
apt_manager = AptCommands(log)
service_manager = ServiceCommands(log)

def execute_plugin(config):
    """
    Point d'entrée principal pour l'exécution du plugin.

    Args:
        config: Configuration du plugin (dictionnaire)

    Returns:
        Tuple (success, message)
    """
    try:
        repository="deb http://gendbuntu.gendarmerie.fr/jammy/gendarmerie-dev/lara-waiting jammy main"
        lara_list="lara.list"
        if apt_manager.is_installed("lara-program", min_version="22.04.3.0"):
            success_msg = "Lara est déja installé"
            log.success(success_msg)
            return True, success_msg
        else:
            returnValue=True
            if apt_manager.is_installed("lara-program"):
                log.info("Ancien LARA installé, désinstallation....")
                returnValue=apt_manager.uninstall("lara-*",purge=True)
            if returnValue:
                apt_manager.remove_repository(repository,lara_list, True)
                returnValue=apt_manager.add_repository(repository,custom_filename=lara_list)
                if returnValue:
                    returnValue=apt_manager.update()
                    if returnValue:
                        returnValue=apt_manager.install("lara-program")
                        if returnValue:
                            msg="Installation de LARA effectuée avec succès"
                        else:
                            msg="Echec dans l'installation de LARA"
                    else:
                        msg="Impossible de mettre à jour les paquets"
                else:
                    msg="Impossible de mettre à jour le dépot"
            else:
                msg="Erreur lors de la suppression de Lara"

            if returnValue:
                log.success(msg)
                return returnValue, msg
            else:
                log.error(msg)
                return False, msg




    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        log.error(error_msg)
        log.debug(traceback.format_exc())
        return False, error_msg

if __name__ == "__main__":
    try:
        # Charger la configuration
        config = json.loads(sys.argv[1])
        log.set_instance_id(config.get("instance_id",0))
        log.set_plugin_name(config.get("plugin_name","test"))
        log.init_logs()

        # Exécuter le plugin
        success, message = execute_plugin(config)

        # Attendre un court instant pour s'assurer que tous les logs sont traités
        time.sleep(0.2)

        # Afficher le résultat final
        if success:
            log.success(f"Succès: {message}")
            sys.exit(0)
        else:
            log.error(f"Échec: {message}")
            sys.exit(1)

    except json.JSONDecodeError as je:
        log.error("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        log.error(f"Erreur inattendue: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)