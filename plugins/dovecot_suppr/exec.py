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
import glob
import shutil
from pathlib import Path
from datetime import datetime, timedelta
# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date

# Maintenant on peut importer tous les éléments du module utils
from plugins_utils import main
from plugins_utils import metier
from plugins_utils import utils_cmd
from plugins_utils import services
from plugins_utils import mozilla_prefs
from plugins_utils import security
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)
DOVECOT_AUTOADD="/etc/profile.d/dovecot-autoadd.sh"
HOME_DIR='/home'


class Plugin:
    def run(self,config,log,target_ip):
        try:
            returnValue=True
            metierCmd = metier.MetierCommands(log,target_ip,config)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            servicesCmd = services.ServiceCommands(log,target_ip)
            mozillaCmd = mozilla_prefs.MozillaPrefsCommands(log,target_ip)
            securityCmd = security.SecurityCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            log.set_total_steps(3)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                try:
                    log.info("Suppression du fichier d'ajout automatique")
                    if os.path.isfile(DOVECOT_AUTOADD):
                        os.remove(DOVECOT_AUTOADD)
                except Exception as e:
                    output_msg="Impossible de supprimer le fichier d'ajout automatique"
                log.next_step()
                log.info("Arrêt automatique de thunderbird")
                returnValue,_=utilsCmd.kill_process_by_name("thunderbird")
                if not returnValue:
                    output_msg="Impossible d'arrêter thunderbird"
                if returnValue:
                    log.next_step()
                    log.info("Lecture des fichiers prefs.js")
                    try:
                        prefs_files=[]
                        user_dirs = [d for d in glob.glob(os.path.join(HOME_DIR, '*')) if os.path.isdir(d)]

                        for user_dir in user_dirs:
                            thunderbird_config_path = os.path.join(user_dir, '.thunderbird')
                            if os.path.exists(thunderbird_config_path):
                                prefs_path = glob.glob(os.path.join(thunderbird_config_path, '*.default*', 'prefs.js'))
                                for prefs in prefs_path:
                                    log.info(f"Lecture de {prefs}")
                                    returnValuePrefs=mozillaCmd.read_prefs_file(prefs)
                                    if returnValuePrefs == None:
                                        log.warning(f"Impossible de lire le fichier {prefs}")
                                    else:
                                        for compteur in range(0,10):
                                            cle=f"mail.identity.id{compteur}.organization"
                                            if cle in returnValuePrefs.keys():
                                                value=returnValuePrefs[cle]
                                                if value=="Dossiers_Locaux_Unites_via_Dovecot (ne pas effacer ou modifier cette ligne)":
                                                    break
                                        log.info(f"Réécriture de {prefs}")
                                        recherche=[]
                                        recherche.append(f"mail.identity.id{compteur}")
                                        recherche.append(f"mail.account.account{compteur}.identities")
                                        recherche.append(f"mail.account.account{compteur}.server")
                                        newPrefs={}
                                        for cle in returnValuePrefs.keys():
                                            nok=0
                                            for search in recherche:
                                                if cle.startswith(search):
                                                    nok=1
                                            if nok==0:
                                                newPrefs[cle]=returnValuePrefs[cle]
                                        returnValueTmp=mozillaCmd.write_prefs_file(prefs,newPrefs,backup=True)
                                        if not returnValueTmp:
                                            log.warning(f"Impossible de modifier {prefs}")
                                            returnValueTmp=securityCmd.set_ownership(prefs,user,user)
                                        if not returnValueTmp:
                                            log.warning(f"Impossible de changer les droits sur {prefs}")
                                        if returnValueTmp:
                                            imap_dir_list=glob.glob(os.path.join(thunderbird_config_path, '*.default*', 'ImapMail'))
                                            for imap_dir in imap_dir_list:
                                                for imap_path in os.listdir(imap_dir):
                                                    if imap_path.startswith("ggd"):
                                                        root=os.path.join(imap_dir,imap_path)
                                                        shutil.rmtree(root,ignore_errors=True)
                    except Exception as e:
                        output_msg="Impossible de trouver les prefs.js"
                        returnValue=False
                    log.next_step()
                # Résultat final
                if returnValue:
                    output_msg = "Dossiers Locaux dovecot supprimé avec succès pour tous les utilisateurs"
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