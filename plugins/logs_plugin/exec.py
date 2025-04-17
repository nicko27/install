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
import shutil
# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import main
from plugins_utils import metier
from plugins_utils import logs
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            metierCmd = metier.MetierCommands(log,target_ip,config)
            logsCmd = logs.LogCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                returnValue=True
                log.set_total_steps(5)
                log.info('Suppression des fichiers de logs de plus de 100Mo')
                logsCmd.purge_large_logs(directories=["/var/log"],patterns=["*.log","*.journal"],size_threshold_mb=100,dry_run=True)
                log.next_step()
                log.info("Désactivation de Apparmor pour sssd")
                returnValue,stdout,stderr=logsCmd.run("ln -sf /etc/apparmor.d/usr.sbin.sssd /etc/apparmor.d/disable/",print_command=True,needs_sudo=True)
                if returnValue:
                    returnValue,stdout,stderr=logsCmd.run("apparmor_parser -R /etc/apparmor.d/usr.sbin.sssd",print_command=True, needs_sudo=True,error_as_warning=True)
                    if not returnValue:
                        if re.compile("Profil inexistant").search(stderr):
                            log.warning("L'opération semble déja avoir été effectuée précédemment")
                            returnValue=True
                        else:
                            output_msg="Erreur avec apparmor_parser"
                else:
                    output_msg="Impossible de créer le lien pour apparmor"
                # Résultat final
                if returnValue:
                    output_msg = "Nettoyage des logs effectués avec succès"
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