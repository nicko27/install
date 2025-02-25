#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import logging
import threading
from datetime import datetime
from ruamel.yaml import YAML

# Configuration du logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_FILE = os.path.join(BASE_DIR, "logs", "mysql_install.log")
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('mysql_install')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def print_progress(step: int, total: int):
    """Affiche la progression"""
    progress = int((step * 100) / total)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Progression : {progress}% (étape {step}/{total})")
    sys.stdout.flush()  # Forcer l'envoi immédiat des données

def run_command(cmd, input_data=None, no_output=False,print_command=False):
    """Exécute une commande en utilisant Popen avec affichage en temps réel"""
    if print_command==True:
    	logger.info(" ".join(cmd))
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_data else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        universal_newlines=True
    )
    
    if input_data:
        process.stdin.write(input_data)
        process.stdin.close()
    
    # Lire stdout et stderr en temps réel
    stdout_lines = []
    stderr_lines = []
    
    while True:
        stdout_line = process.stdout.readline()
        stderr_line = process.stderr.readline()
        
        if stdout_line:
            if no_output==False:
                logger.info(stdout_line.rstrip())
            stdout_lines.append(stdout_line)
        
        if stderr_line:
            if no_output==False:
                logger.error(stderr_line.rstrip())
            stderr_lines.append(stderr_line)
        
        if process.poll() is not None:
            for line in process.stdout:
                if no_output==False:
                    logger.info(line.rstrip())
                stdout_lines.append(line)
            for line in process.stderr:
                if no_output==False:
                    logger.error(line.rstrip())
                stderr_lines.append(line)
            break
    
    stdout = ''.join(stdout_lines)
    stderr = ''.join(stderr_lines)
    return process.returncode == 0, stdout, stderr


def add_printer(printer_name, printer_mode,printer_file, printer_socket, bases_options, specials_options):
    options="-o cupsIPPSuplies=true -o printer-is-shared=false"
    opt=f"{options} {bases_options} {specials_options}"
    if printer_mode=="ppd" or printer_mode=="-P":
        mode=f"-P{printer_file}"
    else:
        mode=f"-m{printer_file}"
    cmd=["lpadmin", "-p", printer_name, mode, "-v", printer_socket, "-u", "allow:all", "-o", opt, '-E']
    logger.info(f"Commande lpadmin: {cmd}")
    returnValue,stdout,stderr = run_command(cmd)
    if returnValue==0:
        cmd=["lpadmin","-d",printer_name]
        logger.info(f"Commande lpadmin: {cmd}")
        returnValue,stdout,stderr = run_command(cmd)    	
        return returnValue
    else:
        return returnValue

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:

        # Récupérer la configuration
        printer_name = config.get('printer_name')
        printer_model = config.get('printer_model')
        printer_ip = config.get('printer_ip')
        
        model_path = os.path.join(os.path.dirname(__file__), "models", printer_model)
        yaml=YAML()
        try:
            with open(model_path, 'r') as f:
                printer_settings = yaml.load(f)
        except Exception as e:
            logger.exception(f"Error loading settings for {printer_model}: {e}")
            return Container()

        couleurs=int(printer_settings.get('couleurs', 0))
        a3=int(printer_settings.get('a3', 0))
        rectoverso=int(printer_settings.get('rectoverso', 0))
        ppdFile=printer_settings.get('ppdFile', '')
        agraffes=int(printer_settings.get('agraffes', 0))
        orecto=printer_settings.get('orecto', '')
        orectoverso=printer_settings.get('orectoverso', '')
        onb=printer_settings.get('onb', '')
        ocouleurs=printer_settings.get('ocouleurs', '')
        oagraffes=printer_settings.get('oagraffes', '')
        oa4=printer_settings.get('oa4', '')
        oa3=printer_settings.get('oa3', '')
        ocommun=printer_settings.get('ocommun', '')
        mode=printer_settings.get('mode', '')
        baseName=printer_settings.get('nom','')
        socket=printer_settings.get('socket', '')

        ip=f"{socket}{printer_ip}"

        total_steps = 3  # Base steps

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

        current_step = 0
        
        current_step += 1
        print_progress(current_step, total_steps)
        logger.info("Installation de l'imprimante {printer_name} avec ip {printer_ip}".format(printer_name=printer_name, printer_ip=printer_ip))
        
        current_step += 1
        logger.info("Suppression de la config evince pour éviter bug avec nouvelle imprimante")
        userList=os.listdir("/home")
        for user in userList:
            if os.path.exists("/home/{user}/.evince".format(user=user)):
                os.rmdir("/home/{user}/.evince".format(user=user))
        print_progress(current_step, total_steps)

        current_step += 1
        name=f"{baseName}_{printer_name}_Recto_NB"
        logger.info(f"Installation de {name}")
        returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oa4} {onb}")
        print_progress(current_step, total_steps)

        if (couleurs==1) and (returnValue==True):
            current_step += 1
            name=f"{baseName}_{printer_name}_Recto_Couleurs"
            logger.info(f"Installation de {name}")
            returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oa4} {ocouleurs}")
            print_progress(current_step, total_steps)

            if (rectoverso==1) and (returnValue==True):
                current_step += 1
                name=f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                logger.info(f"Installation de {name}")
                returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oa4} {ocouleurs}")
                print_progress(current_step, total_steps)

        if (rectoverso==1) and (returnValue==True):
            current_step += 1
            name=f"{baseName}_{printer_name}_RectoVerso_NB"
            logger.info(f"Installation de {name}")
            returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oa4} {onb}")
            print_progress(current_step, total_steps)


        if (agraffes==1) and (returnValue==True):
            current_step += 1
            name=f"{baseName}_{printer_name}_Recto_NB_Agraffes"
            logger.info(f"Installation de {name}")
            returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {onb}")
            print_progress(current_step, total_steps)


            if (rectoverso==1) and (returnValue==True):
                current_step += 1
                name=f"{baseName}_{printer_name}_RectoVerso_NB_Agraffes"
                logger.info(f"Installation de {name}")
                returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {onb}")
                print_progress(current_step, total_steps)


                if (couleurs==1) and (returnValue==True):
                    current_step += 1
                    name=f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                    logger.info(f"Installation de {name}")
                    returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {ocouleurs}")
                    print_progress(current_step, total_steps)


            if (couleurs==1) and (returnValue==True):
                current_step += 1
                name=f"{baseName}_{printer_name}_Recto_Couleurs_Agraffes"
                logger.info(f"Installation de {name}")
                returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {ocouleurs}")
                print_progress(current_step, total_steps)


        if (a3==1) and (returnValue==True):
            current_step += 1
            name=f"{baseName}_{printer_name}_Recto_NB_A3"
            logger.info(f"Installation de {name}")
            returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oa3} {onb}")
            print_progress(current_step, total_steps)


            if (rectoverso==1) and (returnValue==True):
                current_step += 1
                name=f"{baseName}_{printer_name}_RectoVerso_NB_A3"
                logger.info(f"Installation de {name}")
                returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oa3} {onb}")
                print_progress(current_step, total_steps)
                logger.info(f"Installation de {name}")

                if(couleurs==1) and (returnValue==True):
                    current_step += 1
                    name=f"{baseName}_{printer_name}_RectoVerso_Couleurs_A3"
                    logger.info(f"Installation de {name}")
                    returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orectoverso} {oa3} {ocouleurs}")
                    print_progress(current_step, total_steps)
                    logger.info(f"Installation de {name}")

            if (couleurs==1) and (returnValue==True):
                current_step += 1
                name=f"{baseName}_{printer_name}_Recto_Couleurs_A3"
                logger.info(f"Installation de {name}")
                returnValue=add_printer(name, mode,ppdFile, ip, ocommun, f"{orecto} {oa3} {ocouleurs}")
                print_progress(current_step, total_steps)


        
        if (returnValue==True):
            logger.info("Redémarrage du service")
            success, stdout, stderr = run_command(['systemctl', 'restart', 'cups'])
            current_step += 1
            print_progress(current_step, total_steps)

            if not success:
                logger.error(f"Erreur lors du redémarrage du service: {stderr}")
                return False, "Erreur lors du redémarrage de Cups"
            logger.info("Redémarrage du service réussi")
            
        if (returnValue==True):
            return True, "Ajout de l'imprimante effectué avec succès"
        else:
            return False, "Erreur lors de l'ajout de l'imprimante"
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Erreur lors de l'exécution de la commande: {e}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        logger.exception(error_msg)
        return False, error_msg

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: exec.py <config_json>")
        sys.exit(1)
        
    try:
        config = json.loads(sys.argv[1])
        success, message = execute_plugin(config)
        
        if success:
            print(f"Succès: {message}")
            sys.exit(0)
        else:
            print(f"Erreur: {message}")
            sys.exit(1)
            
    except json.JSONDecodeError:
        print("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur inattendue: {e}")
        sys.exit(1)
