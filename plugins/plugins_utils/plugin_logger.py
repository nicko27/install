#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour les logs standardisés en format JSONL ou texte standard.
Supporte plusieurs barres de progression avec styles personnalisables.
Compatible avec l'intégration dans PluginUtilsBase.
"""

import os
import logging
import time
import tempfile
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

# Logger interne pour les problèmes du PluginLogger lui-même
internal_logger = logging.getLogger(__name__)
internal_logger.setLevel(logging.WARNING)

class PluginLogger:
    """
    Gère la journalisation standardisée et les barres de progression
    pour les plugins.
    """
    def __init__(self, plugin_name: Optional[str] = None, instance_id: Optional[Union[str, int]] = None,
                 ssh_mode: bool = False, bar_width: int = 20, text_mode: bool = False):
        """
        Initialise le logger.

        Args:
            plugin_name (Optional[str]): Nom du plugin source.
            instance_id (Optional[Union[str, int]]): ID de l'instance du plugin.
            ssh_mode (bool): Indique si l'exécution est via SSH.
            bar_width (int): Largeur par défaut des barres de progression visuelles.
            text_mode (bool): Active le mode texte standard (désactive JSONL).
        """
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.ssh_mode = ssh_mode
        self.text_mode = text_mode
        self.bar_width = max(5, bar_width)

        # Gestion des progressbars numériques (pourcentage)
        self.progressbars: Dict[str, Dict[str, int]] = {}
        self.default_pb_id = f"pb_default_{self.plugin_name or 'plugin'}_{self.instance_id or '0'}_{int(time.time())}"
        self._init_default_pb()

        # Gestion des barres de progression visuelles (texte)
        self.bars: Dict[str, Dict[str, Any]] = {}

        # Styles par défaut pour les barres visuelles
        self.default_filled_char = "■"
        self.default_empty_char = "□"

        self.log_file: Optional[str] = None
        self.init_logs()

    def _init_default_pb(self):
        """Initialise la barre de progression numérique par défaut."""
        if self.default_pb_id not in self.progressbars:
            self.progressbars[self.default_pb_id] = {
                "total_steps": 1,
                "current_step": 0
            }

    def init_logs(self):
        """Initialise le chemin du fichier log basé sur le mode."""
        if self.plugin_name is None or self.instance_id is None:
            return

        # Déterminer le répertoire des logs
        env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
        log_dir_path: Optional[Path] = None

        if env_log_dir and os.path.isdir(env_log_dir):
            log_dir_path = Path(env_log_dir)
        elif self.ssh_mode:
            log_dir_path = Path(tempfile.gettempdir()) / 'pcUtils_logs'
        else:
            try:
                project_root = Path(__file__).resolve().parent.parent.parent
                log_dir_path = project_root / "logs"
            except NameError:
                log_dir_path = Path("logs")

        if log_dir_path:
            try:
                log_dir_path.mkdir(parents=True, exist_ok=True)
                if self.ssh_mode or (hasattr(os, 'geteuid') and os.geteuid() == 0):
                    try:
                        os.chmod(log_dir_path, 0o777)
                    except Exception as perm_error:
                        internal_logger.warning(f"Impossible de modifier les permissions de {log_dir_path}: {perm_error}")

                # Configuration du fichier de log
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"plugin_{self.plugin_name}_{self.instance_id}_{timestamp}.jsonl"
                self.log_file = str(log_dir_path / log_filename)

                # En mode SSH, émettre le chemin du log pour que l'executor puisse le récupérer
                if self.ssh_mode:
                    print(json.dumps({"level": "info", "message": f"LOG_FILE:{self.log_file}"}), flush=True)
                internal_logger.info(f"Fichier log configuré: {self.log_file}")

            except Exception as e:
                internal_logger.error(f"Erreur lors de la configuration du répertoire de logs {log_dir_path}: {e}")
                self.log_file = None
        else:
            internal_logger.error("Impossible de déterminer un répertoire de logs valide.")
            self.log_file = None

    def _emit_log(self, level: str, message: Any, target_ip: Optional[str] = None):
        """Émet un log au format JSONL ou texte standard."""
        # Timestamp pour le mode texte
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.text_mode:
            # Mode texte standard
            if isinstance(message, dict) and "type" in message:
                # Message de progression ou spécial
                if message["type"] == "progress":
                    log_message = f"[{timestamp}] [PROGRESS] {int(message['data']['percentage']*100)}%"
                elif message["type"] == "progress-text":
                    log_message = f"[{timestamp}] [PROGRESS] {message['data'].get('bar', '')}"
                else:
                    log_message = f"[{timestamp}] [{level.upper()}] {message}"
            else:
                log_message = f"[{timestamp}] [{level.upper()}] {message}"

            # Écrire dans le fichier si configuré
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(log_message + '\n')
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")

            # Toujours afficher sur stdout
            print(log_message, flush=True)

        else:
            # Mode JSONL (compatible avec logger_utils)
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level.lower(),
                "plugin_name": self.plugin_name,
                "instance_id": self.instance_id,
                "target_ip": target_ip,
                "message": message
            }

            # Écrire dans le fichier si configuré
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        json.dump(log_entry, f, ensure_ascii=False)
                        f.write('\n')
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")

            # Toujours émettre sur stdout
            try:
                print(json.dumps(log_entry, ensure_ascii=False), flush=True)
                # Forcer le flush pour les messages de progression
                if level in ["progress", "progress-text"]:
                    sys.stdout.flush()
            except Exception as e:
                internal_logger.error(f"Erreur lors de l'écriture sur stdout: {e}")

    def info(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'information (niveau 'info')."""
        self._emit_log("info", message, target_ip)

    def warning(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'avertissement (niveau 'warning')."""
        self._emit_log("warning", message, target_ip)

    def error(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'erreur (niveau 'error')."""
        self._emit_log("error", message, target_ip)

    def success(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de succès (niveau 'success')."""
        self._emit_log("success", message, target_ip)

    def debug(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de débogage (niveau 'debug')."""
        self._emit_log("debug", message, target_ip)

    def set_total_steps(self, total: int, pb_id: Optional[str] = None):
        """
        Définit le nombre total d'étapes pour une barre de progression numérique.
        Crée la barre si elle n'existe pas. Émet un message de progression initial.
        """
        bar_id = pb_id or self.default_pb_id
        total_steps = max(1, total)

        # Créer ou mettre à jour la barre
        self.progressbars[bar_id] = {"total_steps": total_steps, "current_step": 0}

        if self.text_mode:
            return

        internal_logger.debug(f"Progression numérique '{bar_id}' initialisée avec {total_steps} étapes.")
        # Émettre un message initial de progression à 0%
        self._emit_progress_update(bar_id)

    def next_step(self, pb_id: Optional[str] = None, current_step: Optional[int] = None) -> int:
        """
        Avance la progression numérique d'une étape ou définit l'étape actuelle.
        Émet un message de progression.
        """
        bar_id = pb_id or self.default_pb_id
        if bar_id not in self.progressbars:
            internal_logger.warning(f"next_step appelé pour une barre de progression numérique inconnue: {bar_id}")
            if bar_id == self.default_pb_id:
                self._init_default_pb()
            else:
                return 0

        pb_data = self.progressbars[bar_id]
        if current_step is not None:
            pb_data["current_step"] = min(max(0, current_step), pb_data["total_steps"])
        else:
            pb_data["current_step"] = min(pb_data["current_step"] + 1, pb_data["total_steps"])

        if self.text_mode:
            current = pb_data["current_step"]
            total = pb_data["total_steps"]
            percentage = (current / total) * 100
            print(f"Progression : {current}/{total} ({percentage:.1f}%)", flush=True)

            # Optionnel : écrire dans le fichier log
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Progression : {current}/{total} ({percentage:.1f}%)\n")
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")

            return pb_data["current_step"]

        # Émettre la mise à jour
        self._emit_progress_update(bar_id)
        return pb_data["current_step"]

    def _emit_progress_update(self, bar_id: str):
        """Émet le message JSONL pour la progression numérique."""
        if bar_id not in self.progressbars:
            return

        pb_data = self.progressbars[bar_id]
        current = pb_data["current_step"]
        total = pb_data["total_steps"]
        # Calculer le pourcentage comme float entre 0.0 et 1.0
        percentage = (float(current) / total) if total > 0 else 1.0

        if self.text_mode:
            return

        # Format exact attendu par logger_utils (original qui fonctionnait)
        progress_message = {
            "type": "progress",
            "data": {
                "id": bar_id,
                "percentage": percentage,
                "current_step": current,
                "total_steps": total
            }
        }
        
        # Utiliser level=progress pour que logger_utils traite correctement le message
        self._emit_log("progress", progress_message)

    def create_bar(self, id: str, total: int = 1, pre_text: str = "", post_text: str = "",
                  color: str = "blue", filled_char: Optional[str] = None, empty_char: Optional[str] = None,
                  bar_width: Optional[int] = None):
        """
        Crée et affiche une nouvelle barre de progression visuelle.
        """
        if id in self.bars:
            internal_logger.warning(f"Recréation d'une barre de progression visuelle existante: {id}")

        width = bar_width if bar_width is not None else self.bar_width
        f_char = filled_char or self.default_filled_char
        e_char = empty_char or self.default_empty_char

        self.bars[id] = {
            "total_steps": max(1, total),
            "current_step": 0,
            "pre_text": pre_text,
            "post_text": post_text,
            "color": color,
            "filled_char": f_char,
            "empty_char": e_char,
            "bar_width": width
        }
        internal_logger.debug(f"Barre visuelle '{id}' créée avec {total} étapes.")
        # Afficher la barre initiale à 0%
        self._emit_bar(id, 0)

    def update_bar(self, id: str, current: int, total: Optional[int] = None,
                  pre_text: Optional[str] = None, post_text: Optional[str] = None,
                  color: Optional[str] = None, filled_char: Optional[str] = None,
                  empty_char: Optional[str] = None, bar_width: Optional[int] = None):
        """
        Met à jour une barre de progression visuelle existante.
        """
        if id not in self.bars:
            internal_logger.warning(f"Tentative de mise à jour d'une barre visuelle inexistante: {id}")
            return

        # Mettre à jour les valeurs stockées
        bar_data = self.bars[id]
        bar_data["current_step"] = current
        if total is not None: bar_data["total_steps"] = max(1, total)
        if pre_text is not None: bar_data["pre_text"] = pre_text
        if post_text is not None: bar_data["post_text"] = post_text
        if color is not None: bar_data["color"] = color
        if filled_char is not None: bar_data["filled_char"] = filled_char
        if empty_char is not None: bar_data["empty_char"] = empty_char
        if bar_width is not None: bar_data["bar_width"] = max(5, bar_width)

        # Émettre la barre mise à jour
        self._emit_bar(id, current)

    def next_bar(self, id: str, current_step: Optional[int] = None,
                 pre_text: Optional[str] = None, post_text: Optional[str] = None) -> int:
        """
        Avance la barre de progression visuelle d'une étape ou la définit à une étape spécifique.
        """
        if id not in self.bars:
            internal_logger.warning(f"next_bar appelé pour une barre visuelle inexistante: {id}")
            return 0

        bar_data = self.bars[id]
        if current_step is not None:
            bar_data["current_step"] = min(max(0, current_step), bar_data["total_steps"])
        else:
            bar_data["current_step"] = min(bar_data["current_step"] + 1, bar_data["total_steps"])

        # Mettre à jour les textes si fournis
        if pre_text is not None: bar_data["pre_text"] = pre_text
        if post_text is not None: bar_data["post_text"] = post_text

        current = bar_data["current_step"]
        self._emit_bar(id, current)
        return current

    def _emit_bar(self, id: str, current: int):
        """Construit et émet le message de barre de progression."""
        if id not in self.bars:
            return

        bar_data = self.bars[id]
        total = bar_data["total_steps"]
        current_clamped = min(max(0, current), total)

        if self.text_mode:
            # Mode texte : utiliser un format simple pour la console
            width = bar_data["bar_width"]
            percentage = int((current_clamped / total) * 100) if total > 0 else 100
            filled_width = int(width * current_clamped / total) if total > 0 else width
            filled_width = min(max(0, filled_width), width)
            
            bar_str = (bar_data["filled_char"] * filled_width +
                       bar_data["empty_char"] * (width - filled_width))
            
            pre_text = bar_data["pre_text"]
            post_text = bar_data["post_text"]
            
            bar_display = f"{pre_text} [{bar_str}] {percentage}% {post_text}"
            
            # Afficher en texte
            print(bar_display, flush=True)

            # Optionnel : écrire dans le fichier log
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(bar_display + '\n')
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")
        else:
            # Mode JSONL compatible avec logger_utils
            percentage = int((current_clamped / total) * 100) if total > 0 else 100

            width = bar_data["bar_width"]
            filled_width = int(width * current_clamped / total) if total > 0 else width
            filled_width = min(max(0, filled_width), width)
            bar_str = (bar_data["filled_char"] * filled_width +
                       bar_data["empty_char"] * (width - filled_width))

            # Utiliser le format exact attendu par logger_utils
            progress_message = {
                "type": "progress-text",
                "data": {
                    "id": id,
                    "percentage": percentage,
                    "current_step": current_clamped,
                    "total_steps": total,
                    "status": "running",
                    "pre_text": bar_data["pre_text"],
                    "post_text": bar_data["post_text"],
                    "color": bar_data["color"],
                    "filled_char": bar_data["filled_char"],
                    "empty_char": bar_data["empty_char"],
                    "bar": bar_str
                }
            }
            
            # Utiliser level=progress-text pour que logger_utils traite correctement le message
            self._emit_log("progress-text", progress_message)

    def delete_bar(self, id: str):
        """
        Supprime une barre de progression visuelle de l'affichage.
        """
        if id in self.bars:
            bar_data = self.bars[id]
            internal_logger.debug(f"Suppression de la barre visuelle: {id}")

            if self.text_mode:
                # En mode texte, ajouter un message de fin
                fin_text = f"Barre de progression '{id}' terminée."
                print(fin_text, flush=True)

                # Écrire dans le fichier log si configuré
                if self.log_file:
                    try:
                        with open(self.log_file, 'a', encoding='utf-8') as f:
                            f.write(fin_text + '\n')
                    except Exception as e:
                        internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")
            else:
                # Mode JSONL : émettre un message spécial pour indiquer la suppression
                progress_message = {
                    "type": "progress-text",
                    "data": {
                        "id": id,
                        "status": "stop",  # Indique la suppression
                        "pre_text": bar_data["pre_text"],
                        "post_text": bar_data["post_text"],
                        "color": bar_data["color"],
                    }
                }
                
                # Utiliser level=progress-text comme dans la version originale
                self._emit_log("progress-text", progress_message)

            # Supprimer du dictionnaire interne
            del self.bars[id]
        else:
            internal_logger.warning(f"Tentative de suppression d'une barre visuelle inexistante: {id}")

    def set_default_bar_style(self, filled_char: str, empty_char: str):
        """Définit le style (caractères rempli/vide) par défaut pour les nouvelles barres visuelles."""
        self.default_filled_char = filled_char
        self.default_empty_char = empty_char

    def set_default_bar_width(self, width: int):
        """Définit la largeur par défaut pour les nouvelles barres visuelles."""
        self.bar_width = max(5, width)