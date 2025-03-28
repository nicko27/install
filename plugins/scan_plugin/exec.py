#!/usr/bin/env python3
"""
Plugin pour l'ajout d'imprimantes à un système Linux.
Utilise CUPS via lpadmin pour configurer différentes options d'impression.
"""
import json
import time
import traceback
import pexpect
# Configuration du chemin d'import pour trouver les modules communs
import sys
import os
import re

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
commands_manager = Commands(log)

class Plugin:
    def execute_plugin(self,total_config):
        """Point d'entrée pour l'exécution du plugin"""
        try:
            config=total_config.get("config")
            # Récupérer la configuration
            user = config.get('user',"scan")
            password = config.get('password',"scan")
            confirm=config.get('confirm', False)
            scan_directory=config.get("scan_directory","/partage/commun/Numerisation")
            printer_ip = config.get('printer_ip')
            total_steps=3
            if confirm:
                total_steps+=4
                if not os.path.isdir(scan_directory):
                    total_steps+=1
            log.set_total_steps(total_steps)
            log.info("📠 Configuration serveur pour Numerisation")
            log.info("Ajout de l'utilisateur scan")
            success, stdout, stderr=commands_manager.run(["/usr/sbin/useradd",user],error_as_warning=True)
            log.next_step()
            process= pexpect.spawn("/usr/bin/smbpasswd -a {user}".format(user=user))
            process.expect([pexpect.TIMEOUT,"New SMB password:"])
            process.sendline(password)
            process.expect("Retype new SMB password:")
            process.sendline(password)
            returnValue=process.expect([pexpect.EOF,"Added user {user}.".format(user=user)])
            if returnValue==0:
                log.info("Mise à jour du mot de passe")
            else:
                log.error("Mise à jour du mot de passe")
            log.next_step()
            if returnValue==0:
                success, stdout, stderr=commands_manager.run(["/usr/bin/smbpasswd", "-e"],no_output=True)
                if returnValue==0:
                    log.success("Activation du compte")
                else:
                    log.error("Activation du compte")
            log.next_step()

            if returnValue==0:
                if not os.path.isdir(scan_directory):
                    try:
                        os.makedirs(scan_directory,mode=0o777)
                        log.info(f"Creation du dossier {scan_directory}")
                        returnValue=0
                    except Exception as e:
                        log.error(f"Creation du dossier {scan_directory}")
                        returnValue=0
                    log.next_step()

            if returnValue==0:
                returnValue, stdout, stderr=commands_manager.run(["/usr/bin/chown","-Rv","nobody:nogroup",scan_directory],no_output=True,re_error_ignore="maintenue")
            if returnValue>0:
                log.error("Affectation a nobody:nogroup du dossier {scan_directory}".format(scan_directory=scan_directory))
            else:
                log.info("Affectation a nobody:nogroup du dossier {scan_directory}".format(scan_directory=scan_directory))
                log.next_step()
            if returnValue==0:
                returnValue, stdout, stderr=commands_manager.run(["/usr/bin/chmod","u+t","-v",scan_directory],re_error_ignore="a été conservé")
                if returnValue>0:
                    log.error("Interdiction de suppression du dossier {scan_directory}".format(scan_directory=scan_directory))
                else:
                    log.info("Interdiction de suppression du dossier {scan_directory}".format(scan_directory=scan_directory))
                    log.next_step()
                    path=os.path.abspath(f"{scan_directory}")
                    parts= path.strip(os.sep).split(os.sep)
                    current_path = os.sep
                    for index,part in enumerate(parts):
                        current_path=os.path.join(current_path,part)
                        acl_permission = "rwx" if index==len(parts)-1 else "rx"
                        recursivity="-Rm" if index==len(parts)-1 else "-m"
                        if returnValue==0:
                            returnValue, stdout, stderr=commands_manager.run(["/usr/bin/setfacl",recursivity,"u:"+user+":"+acl_permission,current_path],error_as_warning=True,print_command=False,no_output=False)
                            if returnValue==0:
                                log.info("Mise en place des droits sur {current_path}".format(current_path=current_path))
                            else:
                                log.error("Mise en place des droits sur {current_path}".format(current_path=current_path))

            log.next_step()
            if returnValue==0:
                return True,""
            else:
                return False, "Echec dans l'exécution du plugin"

        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            log.exception(error_msg)
            return False, error_msg

if __name__ == "__main__":
    plugin=Plugin()
    main(log,plugin)