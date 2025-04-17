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
from plugins_utils import users_groups
from plugins_utils import interactive_commands
from plugins_utils import security

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
            usersCmd=  users_groups.UserGroupCommands(log, target_ip)
            interactiveCmd = interactive_commands.InteractiveCommands(log, target_ip)
            securityCmd = security.SecurityCommands(log, target_ip)
            content = config['config']
            user = content.get('user')
            password = content.get('password')
            create_scan_dir = content.get('create_scan_dir')
            scan_directory = content.get('scan_directory')
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                total_steps=3
                if create_scan_dir:
                    total_steps+=4
                    if not os.path.isdir(scan_directory):
                        total_steps+=1
                log.info("Ajout de l'utilisateur scan")
                log.set_total_steps(total_steps)

                error = usersCmd.add_user(user, password,home_dir=None,create_home=False)
                log.next_step()
                if not error:
                    scenario = [
                        ("New SMB password:", password, None),
                        ("Retype new SMB password:", password, None)
                    ]
                    success, reponse = interactiveCmd.run_scenario("/usr/bin/smbpasswd -a {user}".format(user=user),scenario)
                    log.next_step()
                    if success:
                        log.info("Ajout de l'utilisateur {user} pour samba effectué avec succès".format(user=user))
                        success, stdout, stderr = interactiveCmd.run(["/usr/bin/smbpasswd","-e",user])
                        log.next_step()
                        if success:
                            log.info("Activation samba de l'utilisateur {user} effectuée avec succès".format(user=user))
                            log.next_step()
                            if not os.path.isdir(scan_directory):
                                try:
                                    os.makedirs(scan_directory,mode=0o777)
                                    success=True
                                except Exception as e:
                                    success=False
                                log.next_step()
                            if not success:
                                output_msg="Erreur lors de la creation du dossier {scan_directory}".format(scan_directory=scan_directory)
                            else:
                                log.info(f"Creation du dossier {scan_directory} effectuée avec succès")
                                success=securityCmd.set_permissions(scan_directory,mode="u+t",recursive=True)
                                if not success:
                                    output_msg="Erreur lors de la mise en place des droits sur {scan_directory}".format(scan_directory=scan_directory)
                                else:
                                    log.next_step()
                                    log.info(f"Mise en place des droits sur {scan_directory} effectuée avec succès")
                                    success=securityCmd.set_ownership(scan_directory,"nobody","nogroup",recursive=True)
                                    if not success:
                                        output_msg="Erreur lors de l'affectation de nobody:nogroup sur {scan_directory}".format(scan_directory=scan_directory)
                                    else:
                                        log.next_step()
                                        log.info(f"Affectation de  nobody:nogroup sur {scan_directory} effectuée avec succès")
                                        success=securityCmd.set_acl(scan_directory,"u::rwx",recursive=True,modify=True)
                                        if not success:
                                            output_msg="Erreur lors de la mise en place des ACLs sur {scan_directory}".format(scan_directory=scan_directory)
                                        else:
                                            log.next_step()
                                            success= securityCmd.set_acl(scan_directory,"u::rx",recursive=False,modify=True)
                                            if not success:
                                                output_msg="Erreur lors de la mise en place des ACLs sur {scan_directory}".format(scan_directory=scan_directory)
                                            else:
                                                log.next_step()
                                                log.info(f"Mise en place des ACLs sur {scan_directory} effectuée avec succès")
                        else:
                            output_msg="Erreur lors de l'activation samba de l'utilisateur {user}".format(user=user)
                    else:
                        output_msg="Erreur lors de l'ajout de l'utilisateur {user} pour samba".format(user=user)
                else:
                    output_msg = "Erreur lors de l'ajout de l'utilisateur {user}".format(user=user)
                if success==True and error==False:
                    output_msg = "Configuration effectuée avec succès"
                    returnValue=True
                else:
                    output_msg = "Erreur lors de la configuration pour le scan"
                    returnValue=False
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