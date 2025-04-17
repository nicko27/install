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


# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import main
from plugins_utils import metier
from plugins_utils import printers
from plugins_utils import utils_cmd

# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            log.debug(f"Début de l'exécution du plugin add_printer")
            metierCmd = metier.MetierCommands(log,target_ip,config)
            printerCmd = printers.PrinterCommands(log,target_ip)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            printer_config = config['config']
            printer_all =printer_config.get('printer_all')
            printer_ip = printer_config.get('printer_ip')
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            log.set_total_steps(1)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                if printer_all != None and printer_all != False:
                    returnValue = printerCmd.remove_all_network_printers()
                else:
                    returnValue = printerCmd.remove_printer_by_ip(printer_ip)
                log.next_step()

                # Résultat final
                if returnValue:
                    output_msg = "Suppression(s) effectué(es) avec succès"
                else:
                    output_msg = "Erreur lors de la suppression"
            else:
                output_msg = "Ordinateur non concerné"


        except Exception as e:
            output_msg = f"Erreur inattendue: {str(e)}"
            log.debug(traceback.format_exc())
        finally:
            if returnValue:
                log.success(output_msg)
            else:
                log.error(output_msg)
            return returnValue

if __name__ == "__main__":
    plugin=Plugin()
    m=main.Main(plugin)
    m.start()