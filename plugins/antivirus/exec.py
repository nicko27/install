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
from plugins_utils import printers
from plugins_utils import utils_cmd
from plugins_utils import dpkg
from plugins_utils import apt
from plugins_utils import services
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            metierCmd = metier.MetierCommands(log,target_ip,config)
            printerCmd = printers.PrinterCommands(log,target_ip)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            dpkgCmd = dpkg.DpkgCommands(log,target_ip)
            aptCmd = apt.AptCommands(log,target_ip)
            servicesCmd = services.ServiceCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                log.set_total_steps(4)
                if aptCmd.is_installed("eset-agent"):
                    returnValue=True
                    log.info("Paquet eset-agent bien installé")
                    log.next_step()
                else:
                    returnValue=False
                    output_msg="Paquet eset-agent absent"
                if returnValue == True and aptCmd.is_installed("eset-endpoint-antivirus"):
                    log.info("Paquet eset-endpoint-antivirus bien installé")
                    log.next_step()
                else:
                    returnValue=False
                    output_msg="Paquet eset-endpoint-antivirus absent"
                if returnValue == True and servicesCmd.is_active("eea"):
                    log.info("Service EEA bien démarré")
                    log.next_step()
                else:
                    output_msg="Service EEA n'est pas démarré"
                if returnValue == True:
                    returnValue,stdout,sterr=utilsCmd.run("/opt/eset/eea/bin/upd -l")
                    moteur=""
                    if returnValue == True:
                        for line in stdout.split('\n'):
                            if "moteur" in line.lower():
                                moteur=line
                        if len(moteur)>0:
                            match = re.search(r"\b(\d{8})\b", moteur)
                            if match:
                                date_str = match.group(1)
                                date_extraite = datetime.strptime(date_str, "%Y%m%d").date()
                                log.next_step()
                                aujourd_hui = datetime.today().date()
                                hier = aujourd_hui - timedelta(days=1)
                                if date_extraite != aujourd_hui and date_extraite != hier:
                                    log.info("Mise à jour en cours d'exécution")
                                    returnValue,stdout,sterr=utilsCmd.run("/opt/eset/eea/bin/upd -u")
                                    returnValue=1-returnValue
                                    if returnValue:
                                        output_msg="Problème avec UPD logiciel qui fait les maj"
                                else:
                                    log.info("Antivirus à jour")
                            else:
                                log.info("Mise à jour en cours d'exécution")
                                returnValue,stdout,sterr=utilsCmd.run("/opt/eset/eea/bin/upd -u")
                                if returnValue:
                                    output_msg="Problème avec UPD logiciel qui fait les maj"
                        else:
                            returnValue = False
                            output_msg="Problème avec UPD logiciel qui fait les maj"
                    else:
                        output_msg="Problème avec UPD logiciel qui fait les maj"

                # Résultat final
                if returnValue:
                    output_msg = "Antivirus vérifié avec succès"
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