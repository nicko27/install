#!/usr/bin/env python3
"""
Module utilitaire pour les logs standardisés compatibles avec le système principal.
Fournit une classe PluginLogger qui utilise le format [LOG] [TYPE] message attendu par LoggerUtils.
"""

import os
import sys
import logging

class PluginLogger:
    """
    Classe utilitaire pour les logs standardisés compatibles avec le système principal.
    Utilise le format [LOG] [TYPE] message attendu par LoggerUtils.
    """

    def __init__(self, plugin_name=None, instance_id=None):
        """Initialise le logger avec un nom de plugin optionnel"""
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.total_steps = 1
        self.current_step = 0
        self.init_logs()

    def init_logs(self):
        if self.plugin_name != None and self.instance_id != None:
            # Créer le répertoire des logs s'il n'existe pas
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # Configuration du logger
            log_file = f"logs/{self.plugin_name}.log"
            self.logger = logging.getLogger(self.plugin_name)
            self.logger.setLevel(logging.DEBUG)

            # Création d'un handler pour le fichier
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)

            # Création d'un formatter
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            file_handler.setFormatter(formatter)

            # Ajouter le handler au logger
            self.logger.addHandler(file_handler)


    def set_plugin_name(self, plugin_name):
        self.plugin_name = plugin_name

    def set_instance_id(self, instance_id):
        """Définit l'ID de l'instance du plugin"""
        self.instance_id = instance_id

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
        self.logger.info(message)
        print(f"[LOG] [INFO] {message}", flush=True)

    def warning(self, message):
        """Envoie un message d'avertissement"""
        self.logger.warning(message)
        print(f"[LOG] [WARNING] {message}", flush=True)

    def error(self, message):
        """Envoie un message d'erreur"""
        self.logger.error(message)
        print(f"[LOG] [ERROR] {message}", flush=True)

    def success(self, message):
        """Envoie un message de succès"""
        self.logger.info(f"[SUCCESS] {message}")
        print(f"[LOG] [SUCCESS] {message}", flush=True)

    def debug(self, message):
        """Envoie un message de débogage"""
        self.logger.debug(message)
        print(f"[LOG] [DEBUG] {message}", flush=True)

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
        stdout_msg = f"[PROGRESS] {percent} {current_step} {total_steps} {self.plugin_name} {self.instance_id}"
        self.logger.info(stdout_msg)
        print(stdout_msg, flush=True)

        # S'assurer que le message est envoyé immédiatement
        sys.stdout.flush()