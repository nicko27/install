#!/usr/bin/env python3
import os
import sys
import glob
# Get the absolute path to the libs folder
# Assuming main.py is at the same level as the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Look for directories containing Python packages
    # Typically where .dist-info or .py files are stored
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Add the parent directory to the search path
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

        # Also add the main package directory to the path
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)


import json
import subprocess
import logging
from datetime import datetime
from ruamel.yaml import YAML

# Configuration du logging
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('lara_install')

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


def execute_plugin(config):
    """Point d'entrée pour l'exécution du plugin"""
    try:
        total_steps = 4
        current_step = 0


        returnValue=True
        if not os.path.exists("/etc/apt/sources.list.d/lara.list"):
            logger.info("Création du fichier /etc/apt/sources.list.d/lara.list")
            with open("/etc/apt/sources.list.d/lara.list", "w") as f:
                f.write("deb http://gendbuntu.gendarmerie.fr/jammy/gendarmerie-dev/lara-waiting jammy main")
            logger.info("Fichier /etc/apt/sources.list.d/lara.list créé")
        else:
            logger.info("Le fichier /etc/apt/sources.list.d/lara.list existe déjà")
        current_step += 1
        print_progress(current_step, total_steps)

        if returnValue==True:
            logger.info("Vérification de l'installation de lara v2")
            returnValue, stdout, stderr = run_command(['dpkg', '-l', 'lara-vosk-model'],no_output=True)
            if returnValue==True:
                logger.info("Lara est déjà installé, désinstallation")
                returnValue, stdout, stderr = run_command(['apt', 'purge', '-y', 'lara-*'])
                if returnValue==True:
                    logger.info("Désinstallation de lara effectuée avec succès")
                    returnValueLaraV2=True
                else:
                    logger.error("Erreur lors de la désinstallation de LARA")
                    returnValueLaraV2=False
            else:
                logger.info("Lara v2 n'est pas installé")
                returnValueLaraV2=True

                current_step += 1
                total_steps += 1
                print_progress(current_step, total_steps)

        if returnValueLaraV2==True:
            logger.info("Vérification de l'installation de lara v3")
            returnValue, stdout, stderr = run_command(['dpkg', '-l', 'lara-program'],no_output=True)
            if returnValue==True:
                logger.info("Lara est déjà installé, réinstallation")
                reinstall = False
            else:
                logger.info("Lara n'est pas installé, installation")
                reinstall = True

            current_step += 1
            print_progress(current_step, total_steps)

        if returnValue==True:
            logger.info("Mise à jour des paquets")
            returnValue, stdout, stderr = run_command(['apt-get', 'update'])
            if returnValue==True:
                logger.info("Mise à jour des paquets effectuée avec succès")
            else:
                logger.error("Erreur lors de la mise à jour des paquets")

        current_step += 1
        print_progress(current_step, total_steps)

        if returnValue==True:
            if reinstall:
                logger.info("Installation de lara")
                returnValue, stdout, stderr = run_command(['apt-get', 'install', '-y', 'lara-program'])
            else:
                logger.info("Mise à jour de lara")
                returnValue, stdout, stderr = run_command(['apt-get', 'install', '-y', 'lara-program', 'lara-pip-*', '--reinstall'])
        current_step += 1
        print_progress(current_step, total_steps)
        if (returnValue==True):
            if reinstall:
                return True, "Installation de lara effectuée avec succès"
            else:
                return True, "Réinstallation de lara effectuée avec succès"
        else:
            if reinstall:
                return False, "Erreur lors de le l'installation de LARA"
            else:
                return False, "Erreur lors de la réinstallation de LARA"

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
