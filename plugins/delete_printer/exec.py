#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import logging
import threading
from datetime import datetime

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


def delete_printer(printer_name):
    cmd=["lpadmin", "-x", printer_name]
    logger.info(f"Commande lpadmin: {cmd}")
    returnValue,stdout,stderr = run_command(cmd)
    return returnValue

def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:
        printer_all =config.get('printer_all')
        printer_ip = config.get('printer_ip')
        
        current_step =0
        total_step=1
        
        logger.info("Listage des imprimantes à supprimer")
        current_step+=1
        if printer_all:
            # Get the list of printers and count them
            returnValue, stdout, stderr = run_command(["lpstat", "-p"], no_output=True)
            printers_list = [line.split()[1] for line in stdout.splitlines()]
            nb_impr = len(printers_list)  # Count the number of printers
            total_step += nb_impr  # Add this count to total_step
        else:
            # Get the count of printers matching the given printer_ip
            returnValue, stdout, stderr = run_command(["lpstat", "-t"], no_output=True)
            printers_list = [line.split()[2] for line in stdout.splitlines() if printer_ip in line]
            nb_impr = len(printers_list)  # Count the matching printers
            total_step += nb_impr  # Set the total step count

        # Log the number of printers to delete
        logger.info(f"{nb_impr} imprimante(s) à supprimer")

        # Update progress
        print_progress(current_step, total_step)
       	returnValue=True
       	print(printers_list)
       	for printer_name in printers_list:
       	    if returnValue==True:
       	        returnValue,stdout,stderr=run_command(["lpadmin","-x",printer_name])
       	        print(returnValue)
       	        msg=f"Suppression de {printer_name}"
       	        if returnValue==True:
       	            logger.info(msg)
       	        else:
       	            logger.error(msg)
       	    current_step+=1
       	    print_progress(current_step, total_step)    
       	
            
        if (returnValue==True):
            return True, "Suppression(s) d'imprimante(s) effectué(s) avec succès"
        else:
            return False, "Erreur lors de la suppression d'imprimante(s)"
        
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
