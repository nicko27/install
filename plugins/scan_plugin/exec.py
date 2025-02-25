#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import logging
import pexpect
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

def run_command(cmd, input_data=None, no_output=False):
    """Exécute une commande en utilisant Popen avec affichage en temps réel"""
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



def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:

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

        current_step = 0
        logger.info("📠 Configuration serveur pour Numerisation")


        current_step += 1
        logger.info("Ajout de l'utilisateur scan")
        run_command(["/usr/sbin/useradd",user])
        print_progress(current_step, total_steps)


        current_step += 1
        process= pexpect.spawn("/usr/bin/smbpasswd -a {user}".format(user=user))
        process.expect([pexpect.TIMEOUT,"New SMB password:"])
        process.sendline(password)
        process.expect("Retype new SMB password:")
        process.sendline(password)
        return_value=process.expect([pexpect.EOF,"Added user {user}.".format(user=user)])
        if return_value==0:
            logger.info("Mise à jour du mot de passe")
        else:
            logger.error("Mise à jour du mot de passe")
        print_progress(current_step, total_steps)

        current_step += 1
        if return_value==0:
            return_value,stdout,stderr=run_command(["/usr/bin/smbpasswd", "-e"],no_output=True)
            if return_value==0:
                logger.info("Activation du compte")
            else:
                logger.error("Activation du compte")
        print_progress(current_step, total_steps)

        if confirm:
            current_step += 1
            return_value=True
            if not os.path.isdir(scan_directory):
                try:
                    os.makedirs(scan_directory,mode=0o777)
                    logger.info(f"Creation du dossier {scan_directory}")
                    return_value=True
                except Exception as e:
                    logger.error(f"Creation du dossier {scan_directory}")
                    return_value=False
                print_progress(current_step, total_steps)
            
            current_step += 1
            if return_value==True:
                return_value,stdout,stderr=run_command(["/usr/bin/chown","-R","nobody:nogroup",scan_directory])
                if return_value==False:
                    logger.error("Affectation a nobody:nogroup du dossier {scan_directory}".format(scan_directory=scan_directory))
                else:
                    logger.info("Affectation a nobody:nogroup du dossier {scan_directory}".format(scan_directory=scan_directory))
                    print_progress(current_step, total_steps)
                    current_step += 1
                    return_value,stdout,stderr=run_command(["/usr/bin/chmod","u+t",scan_directory])
                    if return_value==False:
                        logger.error("Interdiction de suppression du dossier {scan_directory}".format(scan_directory=scan_directory))
                    else:
                        logger.info("Interdiction de suppression du dossier {scan_directory}".format(scan_directory=scan_directory))
                        print_progress(current_step, total_steps)
                        current_step += 1
                        path=os.path.abspath(f"{scan_directory}")
                        parts= path.strip(os.sep).split(os.sep)
                        current_path = os.sep
                        for index,part in enumerate(parts):
                            current_path=os.path.join(current_path,part)
                            acl_permission = "rwx" if index==len(parts)-1 else "rx"
                            recursivity="-Rm" if index==len(parts)-1 else "-m"
                            return_value,stdout,stderr=run_command(["/usr/bin/setfacl",recursivity,"u:"+user+":"+acl_permission,current_path])
                            if return_value==True:
                                logger.info("Mise en place des droits sur {current_path}".format(current_path=current_path))
                            else:
                                logger.error("Mise en place des droits sur {current_path}".format(current_path=current_path))
                
        print_progress(total_steps,total_steps)
        if (return_value==True):
            return True,""
        else:
            return False, ""
        
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
