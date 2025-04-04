#!/usr/bin/env python3
"""
Module utilitaire pour l'exécution de commandes système.
Fournit une classe Commands pour exécuter des commandes shell de manière sécurisée
et avec une gestion appropriée des erreurs et des logs.
"""

import subprocess
import traceback
import re
import time
import os
from typing import Union, Optional, List, Tuple, Dict, Any

from .plugin_utils_base import PluginUtilsBase


class Commands(PluginUtilsBase):
    """
    Classe utilitaire pour l'exécution de commandes système.
    Permet d'exécuter des commandes shell avec une gestion appropriée des logs et des erreurs.
    """

    def __init__(self, logger=None, target_ip=None):
        """
        Initialise un gestionnaire de commandes.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel)
            target_ip: Adresse IP cible pour les logs (optionnel, pour les exécutions SSH)
        """
        # Appel du constructeur de la classe parente
        super().__init__(logger, target_ip)

    # Les méthodes set_total_steps, next_step, update_progress, log_info, log_warning, log_error, log_debug, log_success
    # sont héritées de PluginUtilsBase et n'ont pas besoin d'être redéfinies

    def run(self, cmd, input_data=None, no_output=False, print_command=False, real_time_output=True, error_as_warning=False,re_error_ignore=None, no_log=True):
        """
        Exécute une commande et retourne le résultat, en traitant les messages de déprécation comme des avertissements.

        Args:
            cmd: Commande à exécuter (liste d'arguments)
            input_data: Données à envoyer sur stdin (optionnel)
            no_output: Si True, n'affiche pas la sortie
            print_command: Si True, affiche la commande complète
            real_time_output: Si True, affiche la sortie en temps réel

        Returns:
            Tuple (success, stdout, stderr)
        """
        if print_command and not no_log:
            self.log_info(f"Exécution de: {' '.join(cmd)}")

        try:
            if real_time_output == True and no_output==False:
                # Utiliser Popen pour un affichage en temps réel
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1  # Line buffered
                )

                stdout_data = []
                stderr_data = []

                # Gérer l'entrée si fournie
                if input_data:
                    process.stdin.write(input_data)
                    process.stdin.close()

                # Lire la sortie en temps réel
                for line in process.stdout:
                    line = line.rstrip()
                    if line and not no_output:
                        if not no_log:
                            self.log_info(line)
                    stdout_data.append(line)

                # Lire les erreurs
                for line in process.stderr:
                    line = line.rstrip()
                    if line and not no_output:
                        if "deprecated" in line.lower() or "warning" in line.lower():
                            if not no_log:
                                self.log_warning(line)
                        else:
                            if error_as_warning:
                                if not no_log:
                                    self.log_warning(line)
                            else:
                                if not no_log:
                                    self.log_error(line)
                    stderr_data.append(line)

                process.wait()
                success = process.returncode == 0

                stdout = "\n".join(stdout_data)
                stderr = "\n".join(stderr_data)

            else:
                # Comportement actuel pour les commandes où l'affichage en temps réel n'est pas nécessaire
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
                                if not no_log:
                                    self.log_info(line.strip())
                            else:
                                # Si déjà au format [LOG], l'envoyer directement à stdout
                                if not no_log:
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
                            if not no_log:
                                self.log_warning(line.strip())
                        else:
                            if error_as_warning:
                                if not no_log:
                                    self.log_warning(line)
                            else:
                                if not no_log:
                                    self.log_error(line)

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
                        if not no_log:
                            self.log_warning("La commande a renvoyé des avertissements de déprécation mais est considérée comme réussie")
                        success = True

                stdout = result.stdout
                stderr = result.stderr

            if re_error_ignore!=None:
                if re.compile(re_error_ignore).search(stderr) or re.compile(re_error_ignore).search(stdout):
                    success = 0
            if error_as_warning:
                success=0

            return success, stdout, stderr

        except Exception as e:
            error_msg = f"Erreur lors de l'exécution de la commande: {str(e)}"
            if not no_log:
                self.log_error(error_msg)
                self.log_error(traceback.format_exc())
            return False, "", str(e)

    def run_as_root(self, cmd, input_data=None, no_output=False, print_command=False, root_credentials=None):
        """
        Exécute une commande avec les privilèges sudo.

        Args:
            cmd: Commande à exécuter (liste d'arguments)
            input_data: Données à envoyer sur stdin (optionnel)
            no_output: Si True, n'affiche pas la sortie
            print_command: Si True, affiche la commande complète
            root_credentials: Dictionnaire contenant les informations d'identification root (optionnel)
                              Format: {'user': 'root_username', 'password': 'root_password'}

        Returns:
            Tuple (success, stdout, stderr)
        """
        # Utiliser l'option -S pour permettre à sudo de lire le mot de passe depuis stdin
        # quand il est exécuté sans terminal
        sudo_cmd = ["sudo", "-S"] + cmd

        # Vérifier si nous avons des informations d'identification root
        if root_credentials and isinstance(root_credentials, dict) and 'password' in root_credentials:
            sudo_password = root_credentials.get('password', '')
            sudo_user = root_credentials.get('user', 'root')

            if sudo_password:
                # Construire une commande qui utilise echo pour passer le mot de passe à sudo
                if sudo_user and sudo_user != 'root':
                    # Si un utilisateur spécifique est fourni, utiliser sudo -u
                    echo_cmd = ["bash", "-c", f"echo '{sudo_password}' | sudo -S -u {sudo_user} {' '.join(cmd)}"]
                else:
                    # Sinon, utiliser sudo standard
                    echo_cmd = ["bash", "-c", f"echo '{sudo_password}' | sudo -S {' '.join(cmd)}"]
                return self.run(echo_cmd, None, no_output, print_command)

        # Si nous sommes en mode d'exécution SSH, nous devons gérer le mot de passe différemment
        # car nous n'avons pas de terminal interactif
        import os
        if os.environ.get("SSH_EXECUTION") == "1":
            # Dans ce cas, nous utilisons echo pour passer le mot de passe à sudo
            # Récupérer le mot de passe depuis l'environnement ou utiliser une valeur par défaut
            sudo_password = os.environ.get("SUDO_PASSWORD", "")
            if sudo_password:
                # Construire une commande qui utilise echo pour passer le mot de passe à sudo
                echo_cmd = ["bash", "-c", f"echo '{sudo_password}' | sudo -S {' '.join(cmd)}"]
                return self.run(echo_cmd, None, no_output, print_command)

        # Si nous ne sommes pas en mode SSH ou si nous n'avons pas de mot de passe,
        # exécuter normalement avec sudo
        return self.run(sudo_cmd, input_data, no_output, print_command)

    def run_and_parse_json(self, cmd, print_command=False):
        """
        Exécute une commande et tente de parser la sortie comme du JSON.

        Args:
            cmd: Commande à exécuter (liste d'arguments)
            print_command: Si True, affiche la commande complète

        Returns:
            Tuple (success, data) où data est le JSON parsé ou None si erreur
        """
        import json
        success, stdout, _ = self.run(cmd, no_output=True, print_command=print_command)

        if not success:
            self.log_error(f"Erreur lors de l'exécution de la commande: {stderr}")
            return False, None

        try:
            data = json.loads(stdout)
            return True, data
        except json.JSONDecodeError as e:
            self.log_error(f"Erreur lors du parsing JSON: {str(e)}")
            return False, None