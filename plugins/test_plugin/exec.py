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
                dovecot_unite=config['config'].get("unite","BT")
                namespace=f"PUBLIC_{dovecot_unite}"
                archive=f"Archives_{dovecot_unite}"
                dovecot_admin=config['config'].get("admin","unite_solc.bdrij.ggd27")
                dovecot_modif=config['config'].get("modif","")
                dovecot_user=config['config'].get("user","")
                dovecot_sauvegarde=config['config'].get("sauvegarde","")
                steps=3+dovecot_sauvegarde+len(dovecot_admin.split(","))+len(dovecot_modif.split(","))+len(dovecot_user.split(","))
                log.set_total_steps(steps)
                if aptCmd.is_installed("dovecot-gend"):
                    returnValue=True
                    log.info("Paquet dovecot-gend bien installé")
                    log.info("Sauvegarde des fichiers de configuration au cas ou")
                    now=datetime.now()
                    moment= now.strftime("%Y-%m-%d-%H-%M-%S")
                    dossier=f"/root/dovecot/{moment}"
                    try:
                        log.info(f"Création du dossier de sauvegarde: {dossier}")
                        os.makedirs(dossier,exist_ok=True)
                        log.next_step()
                        log.info("Copie de /etc/dovecot")
                        barre="copieDovecot"
                        returnValue=filesCmd.copy_dir("/etc/dovecot",f"{dossier}",barre,task_id=barre)
                        if returnValue:
                            log.next_step()
                            if dovecot_sauvegarde:
                                barre="copieMA"
                                log.info("Copie de /partage/Mail_archive")
                                returnValue=filesCmd.copy_dir("/partage/Mail_archive",f"{dossier}/Mail_archive",task_id=barre)
                                if returnValue:
                                    log.next_step()
                                else:
                                    output_msg="Impossible de sauvegarder mail:archive"
                        else:
                            output_msg="Impossible de copier les anciens fichiers dovecot"

                    except Exception as e:
                        output_msg="Impossible de créer le dossier de sauvegarde"
                        returnValue=True
                else:
                    log.info("Installation de dovecot")
                    returnValue=aptCmd.install("dovecot-gend")
                    if returnValue:
                        log.next_step()
                    else:
                        output_msg="Impossible d'installer dovecot"
                if returnValue:
                    try:
                        for elt in dovecot_admin.split(","):
                            if len(elt)>0:
                                log.info(f"Ajout des droits admin pour le groupe {elt} ")
                                dovecotCmd.add_acl_entry(f"{archive}",f"group={elt}","lrwtipekxas")
                                log.next_step()
                        for elt in dovecot_modif.split(','):
                            if len(elt)>0:
                                log.info(f"Ajout des droits modif pour le groupe {elt} ")
                                dovecotCmd.add_acl_entry(f"{archive}",f"group={elt}","lrwtipekxs")
                                log.next_step()
                        for elt in dovecot_user.split(','):
                            if len(elt)>0:
                                log.info(f"Ajout des droits user pour le groupe {elt} ")
                                dovecotCmd.add_acl_entry(f"{archive}",f"group={elt}","lrst")
                                log.next_step()
                    except Exception as e:
                        returnValue=False
                        output_msg="Erreur avec l'ajout des acls"
                if returnValue:
                    dict_namespace=dovecotCmd.list_namespaces()
                    if namespace not in dict_namespace.keys():
                        namespace_config={
                            "inbox": "no",
                            "type": "public",
                            "separator": "/",
                            "prefix": f"{archive}",
                            "location": f"maildir:/partage/Mail_archive/{dovecot_unite}",
                            "subscriptions":"no",
                            "list":"yes"
                        }
                        dovecotCmd.add_namespace(namespace,namespace_config)


                # Résultat final
                if returnValue:
                    output_msg = "Dovecot installé et configuré avec succès"
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