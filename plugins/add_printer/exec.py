#!/usr/bin/env python3
"""
Plugin pour l'ajout d'imprimantes à un système Linux.
Utilise CUPS via lpadmin pour configurer différentes options d'impression.
"""

import os
import sys
import json
import time
import logging
import subprocess
import traceback
import re
from datetime import datetime

class PluginLogger:
    """
    Classe utilitaire pour les logs standardisés compatibles avec le système principal.
    Utilise le format [LOG] [TYPE] message attendu par LoggerUtils.
    """
    
    def __init__(self, plugin_name=None):
        """Initialise le logger avec un nom de plugin optionnel"""
        self.plugin_name = plugin_name
        self.total_steps = 1
        self.current_step = 0
        
    def set_total_steps(self, total):
        """Définit le nombre total d'étapes pour calculer les pourcentages"""
        self.total_steps = max(1, total)
        self.current_step = 0
        
    def next_step(self):
        """Passe à l'étape suivante et met à jour la progression"""
        self.current_step += 1
        current = min(self.current_step, self.total_steps)
        
        # Mettre à jour la progression
        self.update_progress(current / self.total_steps, current, self.total_steps)
        
        # Vidage explicite de stdout pour s'assurer que le message est transmis
        sys.stdout.flush()
        
        return current
    
    def info(self, message):
        """Envoie un message d'information"""
        # Format exact attendu par LoggerUtils.process_output_line selon messaging.py
        stdout_msg = f"[LOG] [INFO] {message}"
        print(stdout_msg, flush=True)
    
    def warning(self, message):
        """Envoie un message d'avertissement"""
        stdout_msg = f"[LOG] [WARNING] {message}"
        print(stdout_msg, flush=True)
    
    def error(self, message):
        """Envoie un message d'erreur"""
        stdout_msg = f"[LOG] [ERROR] {message}"
        print(stdout_msg, flush=True)
    
    def success(self, message):
        """Envoie un message de succès"""
        stdout_msg = f"[LOG] [SUCCESS] {message}"
        print(stdout_msg, flush=True)
    
    def debug(self, message):
        """Envoie un message de débogage"""
        stdout_msg = f"[LOG] [DEBUG] {message}"
        print(stdout_msg, flush=True)
    
    def update_progress(self, percentage, current_step=None, total_steps=None):
        """
        Met à jour la progression avec le format strict [PROGRESS] attendu par le système.
        
        Args:
            percentage: Progression (0.0 à 1.0)
            current_step: Étape actuelle (optionnel)
            total_steps: Nombre total d'étapes (optionnel)
        """
        percent = int(max(0, min(100, percentage * 100)))
        if current_step is None:
            current_step = self.current_step
        if total_steps is None:
            total_steps = self.total_steps
        
        # Format strict requis par le regex dans LoggerUtils.process_output_line
        # Inclure le nom du plugin pour permettre l'identification
        stdout_msg = f"[PROGRESS] {percent} {current_step} {total_steps} {self.plugin_name}"
        print(f"DEBUG: Envoi du message de progression: {stdout_msg}", flush=True)
        print(stdout_msg, flush=True)
        
        # S'assurer que le message est envoyé immédiatement
        sys.stdout.flush()

# Initialiser le logger du plugin
log = PluginLogger("add_printer")

def self_parse_yaml(yaml_content):
    """
    Parse YAML content without external dependencies.
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

def run_command(cmd, input_data=None, no_output=False, print_command=False):
    """
    Exécute une commande et retourne le résultat, en traitant les messages de déprécation comme des avertissements.
    
    Args:
        cmd: Commande à exécuter (liste d'arguments)
        input_data: Données à envoyer sur stdin (optionnel)
        no_output: Si True, n'affiche pas la sortie
        print_command: Si True, affiche la commande complète
        
    Returns:
        Tuple (success, stdout, stderr)
    """
    if print_command:
        log.info(f"Exécution de: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            check=False  # Ne pas lever d'exception si la commande échoue
        )
        
        if not no_output:
            # Traiter stdout ligne par ligne
            for line in result.stdout.splitlines():
                if line.strip():
                    # Vérifier si la ligne est déjà au format standard [LOG]
                    if not line.strip().startswith("[LOG]"):
                        log.info(line.strip())
                    else:
                        # Si déjà au format [LOG], l'envoyer directement à stdout
                        print(line.strip(), flush=True)
            
            # Traiter stderr ligne par ligne, en distinguant erreurs et avertissements
            for line in result.stderr.splitlines():
                if not line.strip():
                    continue
                
                # Vérifier si la ligne est déjà au format standard [LOG]
                if line.strip().startswith("[LOG]"):
                    # Si déjà au format [LOG], l'envoyer directement à stdout
                    print(line.strip(), flush=True)
                    continue
                
                # Détecter si c'est un avertissement ou une erreur
                if "deprecated" in line.lower() or "warning" in line.lower():
                    log.warning(line.strip())
                else:
                    log.error(line.strip())
        
        # Si le code de retour est non-zéro mais que stderr contient uniquement des messages
        # de déprécation, considérer comme un succès
        success = result.returncode == 0
        
        if result.returncode != 0 and result.stderr:
            deprecation_only = True
            for line in result.stderr.splitlines():
                line = line.strip()
                if line and "deprecated" not in line.lower() and "warning" not in line.lower():
                    deprecation_only = False
                    break
            
            if deprecation_only:
                log.warning("La commande a renvoyé des avertissements de déprécation mais est considérée comme réussie")
                success = True
        
        return success, result.stdout, result.stderr
    
    except Exception as e:
        log.error(f"Erreur lors de l'exécution de la commande: {str(e)}")
        return False, "", str(e)

def add_printer(printer_name, printer_mode, printer_file, printer_socket, bases_options, specials_options):
    """
    Ajoute une imprimante au système CUPS.
    
    Args:
        printer_name: Nom de l'imprimante
        printer_mode: Mode d'installation (-m ou -P)
        printer_file: Fichier de pilote
        printer_socket: Socket de l'imprimante (avec IP)
        bases_options: Options de base
        specials_options: Options spéciales
        
    Returns:
        bool: True si l'ajout a réussi, False sinon
    """
    options = "-o cupsIPPSuplies=true -o printer-is-shared=false"
    opt = f"{options} {bases_options} {specials_options}"
    
    # Vérifier si le mode et le fichier sont valides
    if not printer_mode:
        printer_mode = "-m"  # Mode par défaut
    
    if printer_mode == "ppd" or printer_mode == "-P":
        mode_param = "-P"
    else:
        mode_param = "-m"
    
    # Construire la commande avec les paramètres séparés
    cmd = ["lpadmin", "-p", printer_name]
    
    # Ajouter le mode et le fichier d'imprimante s'ils sont spécifiés
    if printer_file:
        cmd.extend([mode_param, printer_file])
    
    # Ajouter les autres paramètres
    cmd.extend(["-v", printer_socket, "-u", "allow:all", "-o", opt, '-E'])
    
    # Journaliser la commande complète
    
    # Exécuter la commande d'ajout d'imprimante
    success, stdout, stderr = run_command(cmd, print_command=True)
    
    if success:
        # Définir comme imprimante par défaut
        default_cmd = ["lpadmin", "-d", printer_name]
        default_success, stdout, stderr = run_command(default_cmd, print_command=True)
        return default_success
    else:
        return False

def execute_plugin(config):
    """
    Point d'entrée principal pour l'exécution du plugin.
    
    Args:
        config: Configuration du plugin (dictionnaire)
        
    Returns:
        Tuple (success, message)
    """
    try:
        # Log de débogage pour indiquer le début de l'exécution
        log.debug(f"Début de l'exécution du plugin add_printer")
        
        # Récupérer la configuration
        if 'config' in config and isinstance(config['config'], dict):
            printer_conf = config['config']
            printer_name = printer_conf.get('printer_name')
            printer_model = printer_conf.get('printer_model')
            printer_ip = printer_conf.get('printer_ip')
        else:
            # Fallback au niveau racine si 'config' n'existe pas
            printer_name = config.get('printer_name')
            printer_model = config.get('printer_model')
            printer_ip = config.get('printer_ip')
                
        # Validation des paramètres obligatoires
        if not printer_name:
            log.error("Erreur: Nom d'imprimante (printer_name) manquant")
            return False, "Nom d'imprimante manquant"
        
        if not printer_ip:
            log.error("Erreur: Adresse IP (printer_ip) manquante")
            return False, "Adresse IP manquante"
        
        if not printer_model:
            log.error("Erreur: Modèle d'imprimante (printer_model) manquant")
            return False, "Modèle d'imprimante manquant"
        
        # Log de débogage pour les paramètres extraits
        log.debug(f"Paramètres extraits: printer_name={printer_name}, printer_model={printer_model}, printer_ip={printer_ip}")
        
        # Vérifier si le contenu du modèle est directement fourni dans la configuration
        log.debug(f"Recherche des paramètres de modèle d'imprimante")
        
        model_content = config.get('printer_model_content')
        if not model_content and 'config' in config and isinstance(config['config'], dict):
            model_content = config['config'].get('printer_model_content')
        
        if model_content:
            log.debug("Contenu du modèle trouvé dans la configuration")
            # Utiliser le contenu fourni directement
            try:
                # Vérifier si le contenu est déjà un dictionnaire
                if isinstance(model_content, dict):
                    printer_settings = model_content
                    log.info(f"Utilisation du dictionnaire de paramètres fourni pour le modèle {printer_model}")
                    # file_logger.info("Contenu du modèle est déjà un dictionnaire")
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
            except Exception as e:
                log.warning(f"Problème lors du chargement des paramètres fournis: {e}")
                model_content = None
        
        # Si pas de contenu valide, charger le fichier depuis le disque
        if not model_content:
            log.info(f"Chargement des paramètres depuis le fichier de modèle {printer_model}")
            model_path = os.path.join(os.path.dirname(__file__), "models", printer_model)
            
            try:
                with open(model_path, 'r') as f:
                    content = f.read()
                    # file_logger.info(f"Fichier modèle chargé, taille: {len(content)} caractères")
                    # Essayer d'abord de le charger comme JSON
                    try:
                        printer_settings = json.loads(content)
                        log.info(f"Fichier JSON chargé avec succès")
                        # file_logger.info("Fichier modèle parsé comme JSON")
                    except json.JSONDecodeError:
                        # Si ce n'est pas du JSON valide, le traiter comme YAML simple
                        printer_settings = self_parse_yaml(content)
                        log.info(f"Fichier YAML chargé avec succès")
                        # file_logger.info("Fichier modèle parsé comme YAML")
            except Exception as e:
                log.error(f"Erreur lors du chargement du fichier modèle: {e}")
                return False, f"Erreur lors du chargement des paramètres pour {printer_model}: {e}"
        
        couleurs = int(printer_settings.get('couleurs', 0))
        a3 = int(printer_settings.get('a3', 0))
        rectoverso = int(printer_settings.get('rectoverso', 0))
        ppdFile = printer_settings.get('ppdFile', '')
        agraffes = int(printer_settings.get('agraffes', 0))
        orecto = printer_settings.get('orecto', '')
        orectoverso = printer_settings.get('orectoverso', '')
        onb = printer_settings.get('onb', '')
        ocouleurs = printer_settings.get('ocouleurs', '')
        oagraffes = printer_settings.get('oagraffes', '')
        oa4 = printer_settings.get('oa4', '')
        oa3 = printer_settings.get('oa3', '')
        ocommun = printer_settings.get('ocommun', '')
        mode = printer_settings.get('mode', '')
        baseName = printer_settings.get('nom', '')
        socket = printer_settings.get('socket', '')
        
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
        userList = os.listdir("/home")
        
        for user in userList:
            evince_path = f"/home/{user}/.evince"
            if os.path.exists(evince_path):
                try:
                    os.rmdir(evince_path)
                    log.info(f"Répertoire {evince_path} supprimé")
                except Exception as e:
                    log.warning(f"Impossible de supprimer {evince_path}: {e}")
        
        # Progresser pour chaque configuration d'imprimante
        log.next_step()
        name = f"{baseName}_{printer_name}_Recto_NB"
        log.info(f"Installation de {name}")
        returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa4} {onb}")
        
        # Configurations supplémentaires en fonction des options
        if couleurs == 1 and returnValue:
            log.next_step()
            name = f"{baseName}_{printer_name}_Recto_Couleurs"
            log.info(f"Installation de {name}")
            returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa4} {ocouleurs}")
            
            if rectoverso == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_RectoVerso_Couleurs"
                log.info(f"Installation de {name}")
                returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa4} {ocouleurs}")
        
        if rectoverso == 1 and returnValue:
            log.next_step()
            name = f"{baseName}_{printer_name}_RectoVerso_NB"
            log.info(f"Installation de {name}")
            returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa4} {onb}")
        
        if agraffes == 1 and returnValue:
            log.next_step()
            name = f"{baseName}_{printer_name}_Recto_NB_Agraffes"
            log.info(f"Installation de {name}")
            returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {onb}")
            
            if rectoverso == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_RectoVerso_NB_Agraffes"
                log.info(f"Installation de {name}")
                returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {onb}")
                if couleurs == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_Agraffes"
                    log.info(f"Installation de {name}")
                    returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oagraffes} {oa4} {ocouleurs}")

            if couleurs == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_Recto_Couleurs_Agraffes"
                log.info(f"Installation de {name}")
                returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oagraffes} {oa4} {ocouleurs}")
        
        if a3 == 1 and returnValue:
            log.next_step()
            name = f"{baseName}_{printer_name}_Recto_NB_A3"
            log.info(f"Installation de {name}")
            returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa3} {onb}")
            
            if rectoverso == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_RectoVerso_NB_A3"
                log.info(f"Installation de {name}")
                returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa3} {onb}")
                
                if couleurs == 1 and returnValue:
                    log.next_step()
                    name = f"{baseName}_{printer_name}_RectoVerso_Couleurs_A3"
                    log.info(f"Installation de {name}")
                    returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orectoverso} {oa3} {ocouleurs}")
            
            if couleurs == 1 and returnValue:
                log.next_step()
                name = f"{baseName}_{printer_name}_Recto_Couleurs_A3"
                log.info(f"Installation de {name}")
                returnValue = add_printer(name, mode, ppdFile, ip, ocommun, f"{orecto} {oa3} {ocouleurs}")
        
        # Redémarrer le service CUPS si l'installation a réussi
        if returnValue:
            log.info("Redémarrage du service CUPS")
            # file_logger.info("Tentative de redémarrage du service CUPS")
            try:
                cups_restart_success, stdout, stderr = run_command(['systemctl', 'restart', 'cups'])
                if cups_restart_success:
                    log.success("Service CUPS redémarré avec succès")
                else:
                    # Vérifier si c'est une erreur non critique
                    if stderr and all(("deprecated" in line.lower() or "warning" in line.lower()) for line in stderr.splitlines() if line.strip()):
                        log.warning("Le service CUPS a été redémarré avec des avertissements")
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
    # Configurer pour unbuffered output
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # Signaler le démarrage du plugin
    log.info("Démarrage du plugin add_printer")
    
    # Vérifier les arguments
    if len(sys.argv) != 2:
        log.error("Usage: exec.py <config_json>")
        sys.exit(1)
    
    try:
        # Charger la configuration
        config = json.loads(sys.argv[1])
        
        # Exécuter le plugin
        success, message = execute_plugin(config)
        
        # Attendre un court instant pour s'assurer que tous les logs sont traités
        time.sleep(0.2)
        
        # Afficher le résultat final
        if success:
            log.success(f"Succès: {message}")
            sys.exit(0)
        else:
            log.error(f"Échec: {message}")
            sys.exit(1)
    
    except json.JSONDecodeError as je:
        log.error("Erreur: Configuration JSON invalide")
        sys.exit(1)
    except Exception as e:
        log.error(f"Erreur inattendue: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)