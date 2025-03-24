#!/usr/bin/env python3
"""
Module utilitaire pour l'exécution de commandes système.
Fournit une classe Commands de base pour exécuter des commandes shell de manière sécurisée
et avec une gestion appropriée des erreurs et des logs.
"""

import subprocess
import traceback


class Commands:
    """
    Classe utilitaire pour l'exécution de commandes système.
    Permet d'exécuter des commandes shell avec une gestion appropriée des logs et des erreurs.
    """

    def __init__(self, logger=None):
        """
        Initialise un gestionnaire de commandes.

        Args:
            logger: Instance de PluginLogger à utiliser pour la journalisation (optionnel)
        """
        self.logger = logger

        # Variables pour la gestion de la progression
        self.total_steps = 1
        self.current_step = 0

        # Si aucun logger n'est fourni, essayer d'en créer un temporaire
        if self.logger is None:
            try:
                from .pluginlogger import PluginLogger
                self.logger = PluginLogger()
            except:
                # Fallback si impossible de créer un logger
                pass

    def set_total_steps(self, total):
        """
        Définit le nombre total d'étapes pour calculer les pourcentages.

        Args:
            total: Nombre total d'étapes
        """
        self.total_steps = max(1, total)
        self.current_step = 0

        if self.logger:
            self.logger.set_total_steps(self.total_steps)

    def next_step(self, message=None):
        """
        Passe à l'étape suivante et met à jour la progression.

        Args:
            message: Message optionnel à afficher

        Returns:
            int: Étape actuelle
        """
        self.current_step += 1
        current = min(self.current_step, self.total_steps)

        # Mise à jour de la progression
        if self.logger:
            self.logger.next_step()
            if message:
                self.logger.info(message)
        else:
            progress = int(current / self.total_steps * 100)
            print(f"[PROGRESSION] {progress}% ({current}/{self.total_steps})")
            if message:
                print(f"[INFO] {message}")

        return current

    def update_progress(self, percentage, message=None):
        """
        Met à jour la progression sans passer à l'étape suivante.
        Utile pour les opérations longues avec progression continue.

        Args:
            percentage: Pourcentage de progression (0.0 à 1.0)
            message: Message optionnel à afficher
        """
        if self.logger:
            self.logger.update_progress(percentage)
            if message:
                self.logger.info(message)
        else:
            progress = int(percentage * 100)
            print(f"[PROGRESSION] {progress}%")
            if message:
                print(f"[INFO] {message}")

    def log_info(self, msg):
        """Enregistre un message d'information."""
        if self.logger:
            self.logger.info(msg)
        else:
            print(f"[LOG] [INFO] {msg}")

    def log_warning(self, msg):
        """Enregistre un message d'avertissement."""
        if self.logger:
            self.logger.warning(msg)
        else:
            print(f"[LOG] [WARNING] {msg}")

    def log_error(self, msg):
        """Enregistre un message d'erreur."""
        if self.logger:
            self.logger.error(msg)
        else:
            print(f"[LOG] [ERROR] {msg}")

    def log_debug(self, msg):
        """Enregistre un message de débogage."""
        if self.logger:
            self.logger.debug(msg)
        else:
            print(f"[LOG] [DEBUG] {msg}")

    def log_success(self, msg):
        """Enregistre un message de succès."""
        if self.logger:
            self.logger.success(msg)
        else:
            print(f"[LOG] [SUCCESS] {msg}")

    def run(self, cmd, input_data=None, no_output=False, print_command=False, real_time_output=True):
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
        if print_command:
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
                        self.log_info(line)
                    stdout_data.append(line)

                # Lire les erreurs
                for line in process.stderr:
                    line = line.rstrip()
                    if line and not no_output:
                        if "deprecated" in line.lower() or "warning" in line.lower():
                            self.log_warning(line)
                        else:
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
                                self.log_info(line.strip())
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
                            self.log_warning(line.strip())
                        else:
                            self.log_error(line.strip())

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
                        self.log_warning("La commande a renvoyé des avertissements de déprécation mais est considérée comme réussie")
                        success = True

                stdout = result.stdout
                stderr = result.stderr

            return success, stdout, stderr

        except Exception as e:
            error_msg = f"Erreur lors de l'exécution de la commande: {str(e)}"
            self.log_error(error_msg)
            return False, "", str(e)

    def run_as_root(self, cmd, input_data=None, no_output=False, print_command=False):
        """
        Exécute une commande avec les privilèges sudo.

        Args:
            cmd: Commande à exécuter (liste d'arguments)
            input_data: Données à envoyer sur stdin (optionnel)
            no_output: Si True, n'affiche pas la sortie
            print_command: Si True, affiche la commande complète

        Returns:
            Tuple (success, stdout, stderr)
        """
        sudo_cmd = ["sudo"] + cmd
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