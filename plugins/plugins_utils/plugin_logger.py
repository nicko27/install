#!/usr/bin/env python3
"""
Module utilitaire pour les logs standardisés en format JSONL.
"""

import os
import sys
import logging
import time
import tempfile
import json
from datetime import datetime

class PluginLogger:
    def __init__(self, plugin_name=None, instance_id=None, ssh_mode=False):
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.total_steps = 1
        self.current_step = 0
        self.ssh_mode = ssh_mode
        
        # Gestion des progressbars
        self.progressbars = {}
        self.default_pb = "main"
        self.progressbars[self.default_pb] = {
            "total_steps": 1,
            "current_step": 0
        }
        
        self.init_logs()

    def init_logs(self):
        if self.plugin_name is not None and self.instance_id is not None:
            # Déterminer le répertoire des logs
            env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
            
            if env_log_dir:
                log_dir = env_log_dir
            elif self.ssh_mode:
                log_dir = "/tmp/pcUtils_logs"
            else:
                log_dir = "logs"

            try:
                os.makedirs(log_dir, exist_ok=True)
                try:
                    os.chmod(log_dir, 0o777)
                except Exception as perm_error:
                    self._emit_log("warning", f"Impossible de modifier les permissions du répertoire {log_dir}: {perm_error}")
            except Exception as e:
                log_dir = os.path.join(tempfile.gettempdir(), 'pcUtils_logs')
                os.makedirs(log_dir, exist_ok=True)

            # Configuration du fichier de log
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            if self.ssh_mode:
                self.log_file = f"{log_dir}/plugin_{timestamp}.jsonl"
            else:
                self.log_file = f"{log_dir}/{self.plugin_name}.jsonl"

            if self.ssh_mode:
                self._emit_log("info", f"LOG_FILE:{self.log_file}")

    def _emit_log(self, level, message):
        """Émet un log au format JSONL"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "plugin_name": self.plugin_name,
            "instance_id": self.instance_id,
            "message": message
        }
        
        # Forcer le flush pour les messages de progression
        force_flush = level == "progress"
        
        # Écrire dans le fichier
        if hasattr(self, 'log_file'):
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    json.dump(log_entry, f)
                    f.write('\n')
                    if force_flush:
                        f.flush()
                        os.fsync(f.fileno())  # Force l'écriture sur le disque
            except Exception as e:
                print(f"Erreur d'écriture dans le fichier de log: {e}", file=sys.stderr)

        # Toujours émettre sur stdout pour la compatibilité
        print(json.dumps(log_entry), flush=True)
        if force_flush:
            sys.stdout.flush()

    def update_progress(self, percentage, current_step=None, total_steps=None):
        """Met à jour la progression"""
        if current_step is None:
            current_step = self.current_step
        if total_steps is None:
            total_steps = self.total_steps

        # S'assurer que le pourcentage est entre 0 et 1
        percentage = max(0.0, min(1.0, float(percentage)))

        # Créer le message de progression
        progress_message = {
            "type": "progress",
            "data": {
                "percentage": percentage,
                "current_step": current_step,
                "total_steps": total_steps
            }
        }

        # Utiliser _emit_log pour garantir le flush immédiat
        self._emit_log("progress", progress_message)

    def info(self, message):
        self._emit_log("info", message)

    def warning(self, message):
        self._emit_log("warning", message)

    def error(self, message):
        self._emit_log("error", message)

    def success(self, message):
        self._emit_log("success", message)

    def debug(self, message):
        self._emit_log("debug", message)

    def next_step(self, pb_id=None, current_step=None):
        """Passe à l'étape suivante pour une progressbar donnée"""
        if pb_id is None:
            # Comportement existant pour la compatibilité
            self.current_step += 1
            current = min(self.current_step, self.total_steps)
            self.update_progress(current / self.total_steps, current, self.total_steps)
            return current
        else:
            # Nouvelle gestion avec ID de progressbar
            if pb_id in self.progressbars:
                if current_step is not None:
                    self.progressbars[pb_id]["current_step"] = current_step
                else:
                    self.progressbars[pb_id]["current_step"] += 1
                
                current = self.progressbars[pb_id]["current_step"]
                total = self.progressbars[pb_id]["total_steps"]
                self.update_progress(current / total, current, total)
                return current
            return 0

    def set_total_steps(self, total, pb_id=None):
        """Définit le nombre total d'étapes pour une progressbar"""
        if pb_id is None:
            # Comportement existant
            self.total_steps = max(1, total)
            self.current_step = 0
        else:
            # Nouvelle gestion avec ID
            if pb_id in self.progressbars:
                self.progressbars[pb_id]["total_steps"] = max(1, total)
                self.progressbars[pb_id]["current_step"] = 0

    def new_pb(self, pb_id: str, total: int = 1) -> None:
        """Crée une nouvelle progressbar avec l'ID spécifié"""
        self.progressbars[pb_id] = {
            "total_steps": max(1, total),
            "current_step": 0
        }