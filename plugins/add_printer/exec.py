#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import logging
import traceback
import re
from datetime import datetime

# Classe autonome pour le logging des plugins
class PluginLogger:
    def __init__(self, plugin_name=None):
        self.plugin_name = plugin_name
        self.total_steps = 1
        self.current_step = 0
        
    def set_total_steps(self, total):
        self.total_steps = max(1, total)
        self.current_step = 0
        
    def next_step(self):
        self.current_step += 1
        current = min(self.current_step, self.total_steps)
        self.update_progress(current / self.total_steps, current, self.total_steps)
        return current
    
    def info(self, message):
        print(f"[LOG] [INFO] {message}", flush=True)
        
    def warning(self, message):
        print(f"[LOG] [WARNING] {message}", flush=True)
        
    def error(self, message):
        print(f"[LOG] [ERROR] {message}", flush=True)
        
    def success(self, message):
        print(f"[LOG] [SUCCESS] {message}", flush=True)
        
    def debug(self, message):
        print(f"[LOG] [DEBUG] {message}", flush=True)
        
    def update_progress(self, percentage, current_step=None, total_steps=None):
        percent = int(max(0, min(100, percentage * 100)))
        if current_step is None:
            current_step = self.current_step
        if total_steps is None:
            total_steps = self.total_steps
        print(f"[PROGRESS] {percent} {current_step} {total_steps}", flush=True)

# Fonction pour analyser le YAML sans dépendances externes
def self_parse_yaml(yaml_content):
    """Parse YAML content without external dependencies.
    This is a simple parser that handles basic YAML structures.
    It doesn't support all YAML features but should work for our printer model files.
    """
    result = {}
    
    # Pour les fichiers de configuration d'imprimante, nous avons une structure simple
    # avec des paires clé-valeur sur chaque ligne
    for line in yaml_content.split('\n'):
        # Ignorer les lignes vides et les commentaires
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('#'):
            continue
        
        # Traiter les paires clé-valeur
        if ':' in stripped_line:
            key, value = stripped_line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            # Traiter les différents types de valeurs
            if not value:  # Valeur vide
                result[key] = ''
            # Chaînes entre guillemets
            elif (value.startswith('"') and value.endswith('"')) or \
                 (value.startswith('\'') and value.endswith('\'')):
                result[key] = value[1:-1]  # Enlever les guillemets
            # Booléens
            elif value.lower() in ['true', 'yes', 'on']:
                result[key] = True
            elif value.lower() in ['false', 'no', 'off']:
                result[key] = False
            # Null/None
            elif value.lower() in ['null', 'none', '~']:
                result[key] = None
            # Nombres
            elif re.match(r'^-?\d+(\.\d+)?$', value):
                if '.' in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)
            else:
                result[key] = value
    
    return result

# Initialiser le logger du plugin
log = PluginLogger("add_printer")

def run_command(cmd, input_data=None, no_output=False, print_command=False):
    """Exécute une commande en utilisant Popen avec affichage en temps réel"""
    if print_command==True:
        log.info(" ".join(cmd))
        
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
                log.info(stdout_line.rstrip())
            stdout_lines.append(stdout_line)
        
        if stderr_line:
            if no_output==False:
                log.error(stderr_line.rstrip())
            stderr_lines.append(stderr_line)
        
        if process.poll() is not None:
            for line in process.stdout:
                if no_output==False:
                    log.info(line.rstrip())
                stdout_lines.append(line)
            for line in process.stderr:
                if no_output==False:
                    log.error(line.rstrip())
                stderr_lines.append(line)
            break
    
    stdout = ''.join(stdout_lines)
    stderr = ''.join(stderr_lines)
    return process.returncode == 0, stdout, stderr


def add_printer(printer_name, printer_mode, printer_file, printer_socket, bases_options, specials_options):
    options="-o cupsIPPSuplies=true -o printer-is-shared=false"
    opt=f"{options} {bases_options} {specials_options}"
    
    # Vérifier si le mode et le fichier sont valides
    if not printer_mode:
        printer_mode = "-m"  # Mode par défaut
    
    if printer_mode=="ppd" or printer_mode=="-P":
        mode_param = "-P"
    else:
        mode_param = "-m"
    
    # Construire la commande avec les paramètres séparés
    cmd=["lpadmin", "-p", printer_name]
    
    # Ajouter le mode et le fichier d'imprimante s'ils sont spécifiés
    if printer_file:
        cmd.extend([mode_param, printer_file])
    
    # Ajouter les autres paramètres
    cmd.extend(["-v", printer_socket, "-u", "allow:all", "-o", opt, '-E'])
    
    returnValue,stdout,stderr = run_command(cmd, print_command=True)
    if returnValue==0:
        cmd=["lpadmin","-d",printer_name]
        returnValue,stdout,stderr = run_command(cmd, print_command=True)    	
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
        
        # Vérifier si le contenu du modèle est directement fourni dans la configuration
        # Afficher les clés disponibles pour le débogage
        log.debug(f"Clés disponibles dans la configuration: {list(config.keys())}")
        if 'config' in config:
            log.debug(f"Clés disponibles dans config['config']: {list(config['config'].keys())}")
            
        # D'abord chercher au niveau racine
        model_content = config.get('printer_model_content')
        if model_content:
            log.debug(f"Trouvé printer_model_content au niveau racine, type: {type(model_content)}")
        
        # Si non trouvé, chercher dans le sous-dictionnaire config
        if not model_content and 'config' in config and isinstance(config['config'], dict):
            model_content = config['config'].get('printer_model_content')
            if model_content:
                log.debug(f"Trouvé printer_model_content dans config, type: {type(model_content)}")
        
        if model_content:
            # Utiliser le contenu fourni directement
            try:
                # Vérifier si le contenu est déjà un dictionnaire
                if isinstance(model_content, dict):
                    printer_settings = model_content
                    log.info(f"Utilisation du dictionnaire de paramètres fourni directement pour le modèle {printer_model}")
                    log.debug(f"Contenu du dictionnaire: {json.dumps(printer_settings, indent=2)}")
                else:
                    # Essayer d'abord de le charger comme JSON
                    try:
                        printer_settings = json.loads(model_content)
                        log.info(f"Contenu JSON parsé avec succès pour le modèle {printer_model}")
                    except (json.JSONDecodeError, TypeError):
                        # Si ce n'est pas du JSON valide, le traiter comme YAML simple
                        log.info(f"Tentative de parsing YAML pour le modèle {printer_model}")
                        printer_settings = self_parse_yaml(model_content)
                        log.info(f"Contenu YAML parsé avec succès pour le modèle {printer_model}")
                    
                log.info(f"Utilisation des paramètres fournis directement pour le modèle {printer_model}")
            except Exception as e:
                log.warning(f"Problème lors du chargement des paramètres fournis pour {printer_model}: {e}")
                log.debug(f"Type de model_content: {type(model_content)}")
                if isinstance(model_content, str) and len(model_content) > 100:
                    log.debug(f"Début du contenu: {model_content[:100]}...")
                else:
                    log.debug(f"Contenu: {model_content}")
                # Continuer pour essayer de charger le fichier depuis le disque
                model_content = None
                
        # Si pas de contenu valide, charger le fichier depuis le disque (méthode traditionnelle)
        if not model_content:
            model_path = os.path.join(os.path.dirname(__file__), "models", printer_model)
            try:
                with open(model_path, 'r') as f:
                    content = f.read()
                    # Essayer d'abord de le charger comme JSON
                    try:
                        printer_settings = json.loads(content)
                    except json.JSONDecodeError:
                        # Si ce n'est pas du JSON valide, le traiter comme YAML simple
                        printer_settings = self_parse_yaml(content)
            except Exception as e:
                log.error(f"Erreur lors du chargement des paramètres pour {printer_model}: {e}")
                return False, f"Erreur lors du chargement des paramètres pour {printer_model}: {e}"

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

        # Calculer le nombre total d'étapes
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

        # Définir le nombre total d'étapes dans le logger
        log.set_total_steps(total_steps)
        
        # Débuter avec la première étape
        log.next_step()
        log.info(f"Installation de l'imprimante {printer_name} avec ip {printer_ip}")
        
        log.next_step()
        log.info("Suppression de la config evince pour éviter bug avec nouvelle imprimante")
        userList=os.listdir("/home")
        for user in userList:
            if os.path.exists("/home/{user}/.evince".format(user=user)):
                os.rmdir("/home/{user}/.evince".format(user=user))
        
        log.next_step()
        name=f"{baseName}_{printer_name}_Recto_NB"
        log.info(f"Installation de {name}")
        returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa4} {onb}")
        log.next_step()

        if (couleurs==1) and (returnValue==True):
            name=f"{baseName}_{printer_name}_Recto_Couleurs"
            log.info(f"Installation de {name}")
            returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa4} {ocouleurs}")
            log.next_step()

            if (rectoverso==1) and (returnValue==True):
                name=f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                log.info(f"Installation de {name}")
                returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa4} {ocouleurs}")
                log.next_step()

        if (rectoverso==1) and (returnValue==True):
            name=f"{baseName}_{printer_name}_RectoVerso_NB"
            log.info(f"Installation de {name}")
            returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa4} {onb}")
            log.next_step()

        if (agraffes==1) and (returnValue==True):
            name=f"{baseName}_{printer_name}_Recto_NB_Agraffes"
            log.info(f"Installation de {name}")
            returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {onb}")
            log.next_step()

            if (rectoverso==1) and (returnValue==True):
                name=f"{baseName}_{printer_name}_RectoVerso_NB_Agraffes"
                log.info(f"Installation de {name}")
                returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {onb}")
                log.next_step()

                if (couleurs==1) and (returnValue==True):
                    name=f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                    log.info(f"Installation de {name}")
                    returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {ocouleurs}")
                    log.next_step()

            if (couleurs==1) and (returnValue==True):
                name=f"{baseName}_{printer_name}_Recto_Couleurs_Agraffes"
                log.info(f"Installation de {name}")
                returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {ocouleurs}")
                log.next_step()

        if (a3==1) and (returnValue==True):
            name=f"{baseName}_{printer_name}_Recto_NB_A3"
            log.info(f"Installation de {name}")
            returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa3} {onb}")
            log.next_step()

            if (rectoverso==1) and (returnValue==True):
                name=f"{baseName}_{printer_name}_RectoVerso_NB_A3"
                log.info(f"Installation de {name}")
                returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa3} {onb}")
                log.next_step()

                if(couleurs==1) and (returnValue==True):
                    name=f"{baseName}_{printer_name}_RectoVerso_Couleurs_A3"
                    log.info(f"Installation de {name}")
                    returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa3} {ocouleurs}")
                    log.next_step()

            if (couleurs==1) and (returnValue==True):
                name=f"{baseName}_{printer_name}_Recto_Couleurs_A3"
                log.info(f"Installation de {name}")
                returnValue=add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa3} {ocouleurs}")
                log.next_step()

        if (returnValue==True):
            log.info("Redémarrage du service")
            success, stdout, stderr = run_command(['systemctl', 'restart', 'cups'])

            if not success:
                log.error(f"Erreur lors du redémarrage du service: {stderr}")
                return False, "Erreur lors du redémarrage de Cups"
            log.success("Redémarrage du service réussi")
            
        if (returnValue==True):
            log.success("Ajout de l'imprimante effectué avec succès")
            return True, "Ajout de l'imprimante effectué avec succès"
        else:
            log.error("Erreur lors de l'ajout de l'imprimante")
            return False, "Erreur lors de l'ajout de l'imprimante"
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Erreur lors de l'exécution de la commande: {e}"
        log.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        log.error(error_msg)
        log.error(traceback.format_exc())
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