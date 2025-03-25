#!/usr/bin/env python3
"""
Module utilitaire pour les logs standardisés compatibles avec le système principal.
Fournit une classe PluginLogger qui utilise le format [LOG] [TYPE] message attendu par LoggerUtils.
"""

import os
import sys
import logging
import time
import tempfile

class PluginLogger:
    """
    Classe utilitaire pour les logs standardisés compatibles avec le système principal.
    Utilise le format [LOG] [TYPE] message attendu par LoggerUtils.
    """

    def __init__(self, plugin_name=None, instance_id=None, ssh_mode=False):
        """
        Initialise le logger avec un nom de plugin optionnel
        
        Args:
            plugin_name: Nom du plugin
            instance_id: ID de l'instance du plugin
            ssh_mode: Si True, utilise le mode SSH avec logs dans /tmp/pcUtils/logs/
        """
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.total_steps = 1
        self.current_step = 0
        self.ssh_mode = ssh_mode
        self.init_logs()

    def init_logs(self):
        if self.plugin_name != None and self.instance_id != None:
            # Déterminer le répertoire des logs selon le mode ou l'environnement
            # Vérifier si la variable d'environnement PCUTILS_LOG_DIR est définie
            env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
            
            if env_log_dir:
                # Utiliser le répertoire spécifié par l'environnement
                log_dir = env_log_dir
                print(f"Utilisation du répertoire de logs défini par l'environnement: {log_dir}", flush=True)
            elif self.ssh_mode:
                # Fallback pour le mode SSH
                log_dir = "/tmp/pcUtils_logs"
            else:
                # Mode local par défaut
                log_dir = "logs"

            # Créer le répertoire des logs s'il n'existe pas
            try:
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                    # Essayer de définir les permissions pour que tout le monde puisse écrire
                    try:
                        os.chmod(log_dir, 0o777)  # Permissions complètes pour tous les utilisateurs
                    except Exception as perm_error:
                        print(f"Avertissement: Impossible de modifier les permissions du répertoire {log_dir}: {perm_error}", flush=True)
                    print(f"Répertoire de logs créé: {log_dir}", flush=True)
                # Vérifier si le répertoire est accessible en écriture
                if not os.access(log_dir, os.W_OK):
                    print(f"Avertissement: Le répertoire {log_dir} n'est pas accessible en écriture", flush=True)
                    raise PermissionError(f"Le répertoire {log_dir} n'est pas accessible en écriture")
            except Exception as e:
                # En cas d'erreur, utiliser /tmp comme fallback
                print(f"Erreur lors de la création/accès du répertoire de logs {log_dir}: {e}", flush=True)
                # Essayer d'abord un répertoire dans /tmp/pcUtils_logs
                try:
                    fallback_dir = os.path.join(tempfile.gettempdir(), 'pcUtils_logs')
                    os.makedirs(fallback_dir, exist_ok=True)
                    try:
                        os.chmod(fallback_dir, 0o777)
                    except Exception:
                        pass  # Ignorer les erreurs de chmod sur le répertoire temporaire
                    log_dir = fallback_dir
                    print(f"Utilisation du répertoire de fallback: {log_dir}", flush=True)
                except Exception as e2:
                    # En dernier recours, utiliser un répertoire temporaire unique
                    print(f"Erreur lors de la création du répertoire de fallback: {e2}", flush=True)
                    log_dir = tempfile.mkdtemp(prefix="pcUtils_logs_")
                    print(f"Utilisation du répertoire temporaire unique: {log_dir}", flush=True)

            # Configuration du logger
            if self.ssh_mode:
                # En mode SSH, on utilise un fichier unique avec timestamp
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_file = f"{log_dir}/plugin_{timestamp}.log"
            else:
                # En mode local, on utilise un fichier par plugin
                log_file = f"{log_dir}/{self.plugin_name}.log"
                
            # Vérifier si le fichier de log existe et est accessible en écriture
            # Si le fichier existe déjà mais n'est pas accessible en écriture, utiliser un nom de fichier alternatif
            if os.path.exists(log_file) and not os.access(log_file, os.W_OK):
                print(f"Avertissement: Le fichier {log_file} existe mais n'est pas accessible en écriture", flush=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                log_file = f"{log_dir}/{self.plugin_name}_{timestamp}.log"
                print(f"Utilisation d'un fichier alternatif: {log_file}", flush=True)

            self.logger = logging.getLogger(self.plugin_name)
            self.logger.setLevel(logging.DEBUG)

            # Création d'un handler pour le fichier avec gestion d'erreur
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setLevel(logging.DEBUG)
            except Exception as e:
                print(f"Erreur lors de la création du handler de fichier pour {log_file}: {e}", flush=True)
                # Fallback sur un fichier dans le répertoire temporaire
                temp_log_file = os.path.join(tempfile.gettempdir(), f"pcUtils_{self.plugin_name}_{time.strftime('%Y%m%d_%H%M%S')}.log")
                print(f"Utilisation d'un fichier de log temporaire: {temp_log_file}", flush=True)
                file_handler = logging.FileHandler(temp_log_file)
                file_handler.setLevel(logging.DEBUG)

            # Création d'un formatter
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
            file_handler.setFormatter(formatter)

            # Ajouter le handler au logger
            self.logger.addHandler(file_handler)

            # En mode SSH, on affiche aussi le chemin du fichier de log
            if self.ssh_mode:
                print(f"LOG_FILE:{log_file}", flush=True)

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