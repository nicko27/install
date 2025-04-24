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
from plugins_utils import printers
from plugins_utils import utils_cmd

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
            printerCmd = printers.PrinterCommands(log,target_ip)
            utilsCmd = utils_cmd.UtilsCommands(log,target_ip)
            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_good_sms=metierCmd.is_good_sms()
            is_good_lrpgn=metierCmd.is_good_lrpgn()
            is_ssh=config.get('ssh_mode', False)
            if is_ssh==False or (is_good_sms and is_good_lrpgn):
                # Récupérer la configuration
                printer_conf = config['config']
                printer_name = printer_conf.get('printer_name')
                printer_ip = printer_conf.get('printer_ip')
                a3 = printer_conf.get('printer_a3')
                all= printer_conf.get('printer_all')
                # Récupérer les informations du modèle d'imprimante
                model_content = printer_conf.get('printer_model_content')
                # Récupérer les options du modèle
                couleurs = int(model_content.get('couleurs', 0))
                rectoverso = int(model_content.get('rectoverso', 0))
                ppdFile = model_content.get('ppdFile', '')
                agraffes = int(model_content.get('agraffes', 0))
                orecto = utilsCmd.get_options_dict(model_content.get('orecto', {}))
                orectoverso = utilsCmd.get_options_dict(model_content.get('orectoverso', {}))
                onb = utilsCmd.get_options_dict(model_content.get('onb', {}))
                ocouleurs = utilsCmd.get_options_dict(model_content.get('ocouleurs', {}))
                oagraffes = utilsCmd.get_options_dict(model_content.get('oagraffes', {}))
                oa4 = utilsCmd.get_options_dict(model_content.get('oa4', {}))
                oa3 = utilsCmd.get_options_dict(model_content.get('oa3', {}))
                ocommun = utilsCmd.get_options_dict(model_content.get('ocommun', {}))
                mode = model_content.get('mode', '')
                baseName = model_content.get('nom', '')
                socket = model_content.get('socket', '')
                uri = f"{socket}{printer_ip}"
                is_ppd = (mode=="ppd") or (mode =="-P")
                if not is_ppd:
                    model=ppdFile
                    ppdFile=None
                else:
                    model=None


                # Calculer le nombre total d'étapes
                total_steps = 4  # Étapes de base
                if not all:
                    # Couleurs configurations
                    if couleurs == 1:
                        total_steps += 1  # Recto Couleurs
                        if rectoverso == 1:
                            total_steps += 1  # RectoVerso Couleurs

                    # RectoVerso configurations
                    if rectoverso == 1:
                        total_steps += 1  # RectoVerso NB

                    # Agraffes configurations
                    if agraffes == 1:
                        total_steps += 1  # Recto NB Agraffes
                        if rectoverso == 1:
                            total_steps += 1  # RectoVerso NB Agraffes
                            if couleurs == 1:
                                total_steps += 1  # RectoVerso Couleurs Agraffes
                        if couleurs == 1:
                            total_steps += 1  # Recto Couleurs Agraffes

                    # A3 configurations
                    if a3 == 1:
                        total_steps += 1  # Recto NB A3
                        if rectoverso == 1:
                            total_steps += 1  # RectoVerso NB A3
                            if couleurs == 1:
                                total_steps += 1  # RectoVerso Couleurs A3
                        if couleurs == 1:
                            total_steps += 1  # Recto Couleurs A3

                # Définir le nombre total d'étapes
                log.set_total_steps(total_steps)

                # Débuter avec la première étape
                log.next_step()
                log.info(f"Installation de l'imprimante {printer_name} avec IP {printer_ip}")

                log.next_step()
                log.info("Suppression de la config evince pour éviter bug avec nouvelle imprimante")
                # Utiliser le module os importé globalement
                import os as os_module  # Réimporter explicitement pour éviter les problèmes de portée
                userList = os_module.listdir("/home")

                for user in userList:
                    evince_path = f"/home/{user}/.evince"
                    if os_module.path.exists(evince_path):
                        try:
                            os_module.rmdir(evince_path)
                            log.info(f"Répertoire {evince_path} supprimé")
                        except Exception as e:
                            log.warning(f"Impossible de supprimer {evince_path}: {e}")

                # Progresser pour chaque configuration d'imprimante
                log.next_step()

                # Utiliser PrinterCommands pour ajouter l'imprimante
                if not all:
                    if not couleurs:
                        name = f"{baseName}_{printer_name}_Recto_NB"
                        log.info(f"Installation de {name}")
                        options=utilsCmd.merge_dictionaries(ocommun,orecto,oa4,onb)
                    else:
                        if agraffes:
                            name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa4,ocouleurs,oagraffes)
                        else:
                            name = f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa4,ocouleurs)  
                    returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)
                
                if all:
                    options=utilsCmd.merge_dictionaries(ocommun,orecto,oa4,onb)
                    returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                    if couleurs == 1 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_Recto_Couleurs"
                        log.info(f"Installation de {name}")
                        options=utilsCmd.merge_dictionaries(ocommun,orecto,oa4,ocouleurs)
                        returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                        if rectoverso == 1 and returnValue:
                            log.next_step()
                            name = f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa4,ocouleurs)
                            returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                    if rectoverso == 1 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_RectoVerso_NB"
                        log.info(f"Installation de {name}")
                        options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa4,onb)
                        returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                    if agraffes == 1 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_Recto_NB_Agraffes"
                        log.info(f"Installation de {name}")
                        options=utilsCmd.merge_dictionaries(ocommun,orecto,oagraffes,onb)
                        returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                        if rectoverso == 1 and returnValue:
                            log.next_step()
                            name = f"{baseName}_{printer_name}_RectoVerso_NB_Agraffes"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oagraffes,oa4,onb)
                            returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                            if couleurs == 1 and returnValue:
                                log.next_step()
                                name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                                log.info(f"Installation de {name}")
                                options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oagraffes,oa4,ocouleurs)
                                returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                        if couleurs == 1 and returnValue:
                            log.next_step()
                            name = f"{baseName}_{printer_name}_Recto_Couleurs_Agraffes"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orecto,oagraffes,oa4,ocouleurs)
                            returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                    if a3 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_Recto_NB_A3"
                        log.info(f"Installation de {name}")

                        options=utilsCmd.merge_dictionaries(ocommun,orecto,oagraffes,oa3,onb)
                        returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)
                        if rectoverso == 1 and returnValue:
                            log.next_step()
                            name = f"{baseName}_{printer_name}_RectoVerso_NB_A3"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa3,onb)
                            returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                            if couleurs == 1 and returnValue:
                                log.next_step()
                                name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_A3"
                                log.info(f"Installation de {name}")
                                options=utilsCmd.merge_dictionaries(ocommun,orectoverso,oa3,ocouleurs)
                                returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                        if couleurs == 1 and returnValue:
                            log.next_step()
                            name = f"{baseName}_{printer_name}_Recto_Couleurs_A3"
                            log.info(f"Installation de {name}")
                            options=utilsCmd.merge_dictionaries(ocommun,orecto,oa3,ocouleurs)
                            returnValue = printerCmd.add_printer(name, uri, ppd_file=ppdFile, model=model, options=options)

                # Résultat final
                if returnValue:
                    output_msg = "Ajout de l'imprimante effectué avec succès"
                else:
                    output_msg = "Erreur lors de l'ajout de l'imprimante"
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