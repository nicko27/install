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

# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import *

# Initialiser le logger du plugin
log = PluginLogger()

# Initialiser les gestionnaires de commandes
printer_manager = PrinterCommands(log)
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
            # Log de débogage pour indiquer le début de l'exécution
            log.set_total_steps(2)

            # Récupérer la configuration
            printer_config = config['config']
            printer_all =printer_config.get('printer_all')
            printer_ip = printer_config.get('printer_ip')

            if printer_all != None and printer_all != False:
                returnValue = printer_manager.remove_all_network_printers()
            else:
                returnValue = printer_manager.remove_printer_by_ip(printer_ip)
            log.next_step()
            # Redémarrer le service CUPS si l'installation a réussi
            if returnValue:
                log.info("Redémarrage du service CUPS")
                try:
                    # Utiliser ServiceCommands pour redémarrer CUPS
                    returnValue = service_manager.restart("cups")

                    if returnValue:
                        log.success("Service CUPS redémarré avec succès")
                    else:
                        log.error(f"Erreur lors du redémarrage du service CUPS")
                        return False, "Erreur lors du redémarrage de CUPS"
                except Exception as e:
                    log.error(f"Erreur lors du redémarrage de CUPS: {e}")
                    return False, f"Erreur lors du redémarrage de CUPS: {e}"
            log.next_step()
            # Résultat final
            if returnValue:
                success_msg = "Suppression(s) effectué(es) avec succès"
                log.success(success_msg)
                return True, success_msg
            else:
                error_msg = "Erreur lors de la suppression"
                log.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            log.error(error_msg)
            log.debug(traceback.format_exc())
            return False, error_msg

if __name__ == "__main__":
    plugin=Plugin()
    main(log,plugin)