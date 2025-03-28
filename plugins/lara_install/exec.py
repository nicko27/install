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
from plugins_utils.import_helper import setup_import_paths

# Configurer les chemins d'import
setup_import_paths()

# Maintenant on peut importer tous les éléments du module plugins_utils
from plugins_utils import *

# Initialiser le logger du plugin
log = PluginLogger()

# Initialiser les gestionnaires de commandes
apt_manager = AptCommands(log)
service_manager = ServiceCommands(log)

class Plugin:
    def execute_plugin(self,config):
        """
        Point d'entrée principal pour l'exécution du plugin.

        Args:
            config: Configuration du plugin (dictionnaire)

        Returns:
            Tuple (success, message)
        """
        try:
            total_steps=1
            log.set_total_steps(total_steps)
            repository="deb http://gendbuntu.gendarmerie.fr/jammy/gendarmerie-dev/lara-waiting jammy main"
            lara_list="lara.list"
            if apt_manager.is_installed("lara-program", min_version="22.04.3.0"):
                success_msg = "Lara est déja installé"
                log.success(success_msg)
                log.next_step()
                return True, success_msg
            else:
                returnValue=True
                total_steps+=4
                log.set_total_steps(total_steps)
                log.next_step()
                if apt_manager.is_installed("lara-program"):
                    log.info("Ancien LARA installé, désinstallation....")
                    returnValue=apt_manager.uninstall("lara-*",purge=True)
                    total_steps+=1
                    log.set_total_steps(total_steps)
                    log.next_step()
                if returnValue:
                    apt_manager.remove_repository(repository,lara_list, True)
                    returnValue=apt_manager.add_repository(repository,custom_filename=lara_list)
                    log.next_step()
                    if returnValue:
                        returnValue=apt_manager.update()
                        log.next_step()
                        if returnValue:
                            returnValue=apt_manager.install("lara-program")
                            log.next_step()
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
    plugin=Plugin()
    main(log,plugin)