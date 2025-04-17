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
from plugins_utils import apt
from plugins_utils import utils_cmd

# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            returnValue=True
            metierCmd = metier.MetierCommands(log,target_ip,config)
            aptCmd = apt.AptCommands(log,target_ip)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                total_steps=1
                log.set_total_steps(total_steps)
                repository="deb http://gendbuntu.gendarmerie.fr/jammy/gendarmerie-dev/lara-waiting jammy main"
                lara_list="lara.list"
                returnValue=True

                if aptCmd.is_installed("lara-program", min_version="22.04.5.0"):
                    output_msg = "Lara est déja installé"
                    log.success(output_msg)
                    log.next_step()
                else:
                    total_steps+=4
                    log.set_total_steps(total_steps)
                    log.next_step()
                    if aptCmd.is_installed("lara-program"):
                        log.info("Ancien LARA installé, désinstallation....")
                        returnValue=aptCmd.uninstall("lara-*",purge=True)
                        total_steps+=1
                        log.set_total_steps(total_steps)
                        log.next_step()
                    if returnValue:
                        aptCmd.remove_repository(repository,lara_list, True)
                        returnValue=aptCmd.add_repository(repository,custom_filename=lara_list)
                        log.next_step()
                        if returnValue:
                            returnValue=aptCmd.update()
                            log.next_step()
                            if returnValue:
                                returnValue=aptCmd.install("lara-program")
                                log.next_step()
                                if returnValue:
                                    output_msg="Installation de LARA effectuée avec succès"
                                else:
                                    output_msg="Echec dans l'installation de LARA"
                            else:
                                output_msg="Impossible de mettre à jour les paquets"
                        else:
                            output_msg="Impossible de mettre à jour le dépot"
                    else:
                        output_msg="Erreur lors de la suppression de Lara"

                # Résultat final
                if returnValue:
                    output_msg = "Mise à jour effectuée avec succès"
                else:
                    output_msg = "Echec lors de la mise à jour des paquets"
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