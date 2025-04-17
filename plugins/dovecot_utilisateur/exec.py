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
import shutil
from datetime import datetime, timedelta
# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date

# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import main
from plugins_utils import metier
from plugins_utils import utils_cmd
from plugins_utils import dpkg
from plugins_utils import apt
from plugins_utils import services
from plugins_utils import files
from plugins_utils import config_files
from plugins_utils import dovecot
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)
DOVECOT_ACL="/etc/dovecot/dovecot-acl"
DOVECOT_MAIL="/etc/dovecot/conf.d/10-mail.conf"


class Plugin:
    def run(self,config,log,target_ip):
        try:
            returnValue=True
            metierCmd = metier.MetierCommands(log,target_ip,config)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            dpkgCmd = dpkg.DpkgCommands(log,target_ip)
            aptCmd = apt.AptCommands(log,target_ip)
            servicesCmd = services.ServiceCommands(log,target_ip)
            filesCmd = files.FilesCommands(log,target_ip)
            cfCmd = config_files.ConfigFileCommands(log,target_ip)
            dovecotCmd = dovecot.DovecotCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                sms=config['config'].get("sms")
                dovecot_autoadd=os.getcwd()+"/"+dovecot-autoadd.sh
                dest_dovecot_autoadd="/etc/profile.d/dovecot_autoadd/dovecot-autadd.sh"
                log.info("Copie du fichier dovecot-autoadd.sh vers /etc/profile.d")
                returnValue=filesCmd.copy_file(dovecot_autoadd,dest_dovecot_autoadd)
                if returnValue:
                    log.next_step()
                else:
                    output_msg="Impossible de copier le fichier dovecot-autoadd.sh"
                if returnValue:
                    returnValue=filesCmd.replace_in_file(dest_dovecot_autoadd,"%%DOVECOT_SMS%%",sms)
                    if returnValue:
                        log.next_step()
                    else:
                        output_msg="Erreur dans le remplacement dans le fichier"
                if returnValue:
                    returnValue,stdout,stderr = filesCmd.run(dest_dovecot_autoadd,no_output=False,needs_sudo=True)
                    if returnValue:
                        log.next_step()
                    else:
                        output_msg="Erreur avec la modif automatique des prefs.js"
                # Résultat final
                if returnValue:
                    output_msg = "Dovecot configuré pour les utilisateurs avec succès"
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