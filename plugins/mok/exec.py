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
                returnValue,stdout,stderr=metierCmd.run("/bin/bash /usr/local/sbin/create-mok-gend", needs_sudo=True)
                returnValue=False
                create_mok=False
                for line in stdout.split('\n'):
                    if "Il est maintenant nécessaire de redémarrer afin de finir l'importation de la clé MOK." in line.strip():
                        returnValue=True
                        create_mok=True
                    elif "MOK-JAMMY déjà enrôlée et bi-clé correspondante dans /var/lib/shim-signed/mok." in line.strip():
                        returnValue=True
                # Résultat final
                if returnValue:
                    if create_mok==True:
                        output_msg = "MOK créé avec succès, ne pas oublier de redémarrer pour finir la configuration"
                    else:
                        output_msg = "MOK déja présent, inutile de redémarrer"
                else:
                    output_msg =  "Problème avec la mise à jour MOK"
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