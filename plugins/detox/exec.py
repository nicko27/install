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
from plugins_utils import apt
from pathlib import Path
# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log,target_ip):
        try:
            metierCmd = metier.MetierCommands(log,target_ip)
            aptCmd = apt.AptCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            src_dir = config['config']['src_dir']
            log.set_total_steps(3)
            if Path(src_dir).exists():
                returnValue=True
                log.info(f"Le dossier {src_dir} existe")
                log.next_step()
            else:
                returnValue=False
                output_msg="Le dossier {src_dir} n'existe pas"
            if returnValue:
                log.info("Vérification de la présence de Detox")
                if aptCmd.is_installed("detox"):
                    log.info("Logiciel déja installé")
                    returnValue=True
                    log.next_step()
                else:
                    log.info("Installation de Detox")
                    returnValue=aptCmd.install("detox",no_recommends=True)
            if returnValue:
                log.info("Detox installé avec succès")
                returnValue,stdout,stderr=aptCmd.run(f"detox -r -v {src_dir}", needs_sudo=True)
                log.next_step()
            else:
                output_msg="Erreur dans l'installation de Detox"
            if returnValue:
                output_msg = "Renommage des fichiers exécuté avec succès"
            else:
                output_msg="Erreur dans le renommage des fichiers"

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