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

# Initialiser le logger du plugin
#log = PluginUtilsBase("add_printer")

# Initialiser les gestionnaires de commandes
#printer_manager = PrinterCommands(log)
#service_manager = ServiceCommands(log)

class Plugin:
    def run(self,config,log):
        try:
            log.debug(f"Début de l'exécution du plugin add_printer")

            # Vérifier si nous sommes en mode SSH depuis la configuration
            is_ssh = config.get('ssh_mode', False)
            if is_ssh:
                
            # Récupérer la configuration
            printer_conf = config['config']
            printer_name = printer_conf.get('printer_name')
            printer_model = printer_conf.get('printer_model')
            printer_ip = printer_conf.get('printer_ip')
            a3 = printer_conf.get('printer_a3')
            log.info(f"Configuration de l'imprimante: {json.dumps(printer_conf, ensure_ascii=False)}")

            # Récupérer les informations du modèle d'imprimante
            model_content = config.get('printer_model_content')
            # Récupérer les options du modèle
            couleurs = int(model_content.get('couleurs', 0))
            rectoverso = int(model_content.get('rectoverso', 0))
            ppdFile = model_content.get('ppdFile', '')
            agraffes = int(model_content.get('agraffes', 0))
            orecto = model_content.get('orecto', '')
            orectoverso = model_content.get('orectoverso', '')
            onb = model_content.get('onb', '')
            ocouleurs = model_content.get('ocouleurs', '')
            oagraffes = model_content.get('oagraffes', '')
            oa4 = model_content.get('oa4', '')
            oa3 = model_content.get('oa3', '')
            ocommun = model_content.get('ocommun', '')
            mode = model_content.get('mode', '')
            baseName = model_content.get('nom', '')
            socket = model_content.get('socket', '')

            ip = f"{socket}{printer_ip}"

            # Calculer le nombre total d'étapes
            total_steps = 3  # Étapes de base

            # Recto NB always
            total_steps += 1

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
            name = f"{baseName}_{printer_name}_Recto_NB"
            log.info(f"Installation de {name}")

            # Utiliser PrinterCommands pour ajouter l'imprimante
            options = f"{ocommun} {orecto} {oa4} {onb}"
            driver_param = ppdFile
            is_ppd= (mode=="ppd") or (mode =="-P")

            returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

            if couleurs == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_Recto_Couleurs"
                log.info(f"Installation de {name}")
                options = f"{ocommun} {orecto} {oa4} {ocouleurs}"

                if rectoverso == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                    log.info(f"Installation de {name}")

                    options = f"{ocommun} {orectoverso} {oa4} {ocouleurs}"
                    if mode == "ppd" or mode == "-P":
                        returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

            if rectoverso == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_RectoVerso_NB"
                log.info(f"Installation de {name}")

                options = f"{ocommun} {orectoverso} {oa4} {onb}"
                returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

            if agraffes == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_Recto_NB_Agraffes"
                log.info(f"Installation de {name}")
                options = f"{ocommun} {orecto} {oagraffes} {oa4} {onb}"
                returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

                if rectoverso == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_RectoVerso_NB_Agraffes"
                    log.info(f"Installation de {name}")
                    options = f"{ocommun} {orectoverso} {oagraffes} {oa4} {onb}"
                    if couleurs == 1 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                        log.info(f"Installation de {name}")
                        options = f"{ocommun} {orectoverso} {oagraffes} {oa4} {ocouleurs}"
                        returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

                if couleurs == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_Recto_Couleurs_Agraffes"
                    log.info(f"Installation de {name}")

                    options = f"{ocommun} {orecto} {oagraffes} {oa4} {ocouleurs}"
                    returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

            if a3 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_Recto_NB_A3"
                log.info(f"Installation de {name}")

                options = f"{ocommun} {orecto} {oa3} {onb}"
                returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)
                if rectoverso == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_RectoVerso_NB_A3"
                    log.info(f"Installation de {name}")

                    options = f"{ocommun} {orectoverso} {oa3} {onb}"
                    returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

                    if couleurs == 1 and returnValue:
                        log.next_step()
                        name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_A3"
                        log.info(f"Installation de {name}")

                        options = f"{ocommun} {orectoverso} {oa3} {ocouleurs}"
                        returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)
                if couleurs == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_Recto_Couleurs_A3"
                    log.info(f"Installation de {name}")

                    options = f"{ocommun} {orecto} {oa3} {ocouleurs}"
                    returnValue = printer_manager.add_printer(name, ip, driver_param, options,is_ppd)

            # Redémarrer le service CUPS si l'installation a réussi
            if returnValue:
                log.info("Redémarrage du service CUPS")
                try:
                    # Redémarrer CUPS directement car nous sommes déjà en sudo
                    log.info("Redémarrage du service cups")
                    cups_restart_success = service_manager.restart("cups")

                    if cups_restart_success:
                        log.success("Service CUPS redémarré avec succès")
                    else:
                        log.error(f"Erreur lors du redémarrage du service CUPS")
                        return False, "Erreur lors du redémarrage de CUPS"
                except Exception as e:
                    log.error(f"Erreur lors du redémarrage de CUPS: {e}")
                    return False, f"Erreur lors du redémarrage de CUPS: {e}"

            # Résultat final
            if returnValue:
                success_msg = "Ajout de l'imprimante effectué avec succès"
                log.success(success_msg)
                return True, success_msg
            else:
                error_msg = "Erreur lors de l'ajout de l'imprimante"
                log.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Erreur inattendue: {str(e)}"
            log.error(error_msg)
            log.debug(traceback.format_exc())
            return False, error_msg

if __name__ == "__main__":
    plugin=Plugin()
    m=main.Main(plugin)
    m.start()