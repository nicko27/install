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
import re
from datetime import datetime, timedelta
# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import main
from plugins_utils import metier
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            metierCmd = metier.MetierCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                log.set_total_steps(1)
                log.info("Envoi d'un inventaire, opération longue")
                returnValue,stdout,stderr=metierCmd.run("ocsinventory-agent --force --debug",no_output=True,error_as_warning=True)
                if "Cannot establish communication" in stderr:
                    output_msg="Erreur 500 avec le serveur OCS"
                else:
                    if "NO_ACCOUNT_UPDATE" in stderr:
                        status_send=False
                    else:
                        status_send=True
                # Résultat final
                if returnValue:
                    if status_send:
                        output_msg = "Envoi OCS effectué avec succès avec mise à jour"
                    else:
                        output_msg = "Envoi OCS effectué avec succès sans mise à jour"
                else:
                    output_msg = "Erreur lors des opérations pour OCS"
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
    resultat=m.start()
    returnValue=1-resultat
    sys.exit(returnValue)