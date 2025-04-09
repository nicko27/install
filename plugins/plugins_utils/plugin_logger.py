# install/plugins/plugins_utils/plugin_logger.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour les logs standardisés en format JSONL ou texte standard.
Supporte plusieurs barres de progression avec styles personnalisables.
Compatible avec l'intégration dans PluginUtilsBase.
"""

import os
import sys
import logging # Utiliser le logger standard si besoin pour les erreurs internes
import time
import tempfile
import json
from datetime import datetime
from pathlib import Path # Utiliser pathlib pour la gestion des chemins
from typing import Dict, Any, Optional, Union, List

# Logger interne pour les problèmes du PluginLogger lui-même
internal_logger = logging.getLogger(__name__)
internal_logger.setLevel(logging.WARNING) # Ne logguer que les problèmes internes

class PluginLogger:
    """
    Gère la journalisation structurée (JSONL) ou en texte standard 
    et les barres de progression pour les plugins et l'interface Textual.
    """
    def __init__(self, plugin_name: Optional[str] = None, instance_id: Optional[Union[str, int]] = None,
                 ssh_mode: bool = False, bar_width: int = 20, text_mode: bool = False):
        """
        Initialise le logger.

        Args:
            plugin_name (Optional[str]): Nom du plugin source.
            instance_id (Optional[Union[str, int]]): ID de l'instance du plugin.
            ssh_mode (bool): Indique si l'exécution est via SSH (affecte le chemin des logs).
            bar_width (int): Largeur par défaut des barres de progression visuelles.
            text_mode (bool): Active le mode texte standard (désactive JSONL).
        """
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.ssh_mode = ssh_mode
        self.text_mode = text_mode
        self.bar_width = max(5, bar_width) # Largeur minimale de 5

        # Gestion des progressbars numériques (pourcentage)
        self.progressbars: Dict[str, Dict[str, int]] = {}
        # Générer un ID par défaut plus unique
        default_id_suffix = f"{self.plugin_name or 'plugin'}_{self.instance_id or 0}_{int(time.time())}"
        self.default_pb_id = f"pb_default_{default_id_suffix}"
        self._init_default_pb()

        # Gestion des barres de progression visuelles (texte)
        self.bars: Dict[str, Dict[str, Any]] = {}

        # Styles par défaut pour les barres visuelles
        self.default_filled_char = "■"
        self.default_empty_char = "□"

        self.log_file: Optional[str] = None
        self.init_logs() # Initialiser le chemin du fichier log

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
             internal_logger.warning("Nom du plugin ou ID d'instance manquant, impossible de créer un fichier log spécifique.")
             return

        # Déterminer le répertoire des logs
        env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
        log_dir_path: Optional[Path] = None

        if env_log_dir and os.path.isdir(env_log_dir):
            log_dir_path = Path(env_log_dir)
        elif self.ssh_mode:
            # En mode SSH, utiliser un chemin temporaire standard
            log_dir_path = Path(tempfile.gettempdir()) / 'pcUtils_logs'
        else:
            # En mode local, essayer de remonter depuis le fichier actuel
            try:
                # __file__ -> plugin_logger.py
                # parent -> plugins_utils
                # parent -> plugins
                # parent -> install (racine du projet?)
                project_root = Path(__file__).resolve().parent.parent.parent
                log_dir_path = project_root / "logs"
            except NameError:
                 # Fallback si __file__ n'est pas défini (ex: interactif)
                 log_dir_path = Path("logs") # Relatif au CWD

        if log_dir_path:
            try:
                log_dir_path.mkdir(parents=True, exist_ok=True)
                # Essayer de rendre le dossier accessible en écriture (utile en mode SSH)
                if self.ssh_mode or (hasattr(os, 'geteuid') and os.geteuid() == 0):
                    try:
                        os.chmod(log_dir_path, 0o777)
                    except Exception as perm_error:
                         internal_logger.warning(f"Impossible de modifier les permissions de {log_dir_path}: {perm_error}")

                # Configuration du fichier de log
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Utiliser un nom de fichier plus unique, surtout en mode SSH
                log_filename = f"plugin_{self.plugin_name}_{self.instance_id}_{timestamp}"
                log_filename += ".txt" if self.text_mode else ".jsonl"
                self.log_file = str(log_dir_path / log_filename)

                # En mode SSH, émettre le chemin du log pour que l'executor puisse le récupérer
                if self.ssh_mode:
                    # Utiliser print direct car _emit_log n'est peut-être pas prêt
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
        # Préparer le message
        if isinstance(message, dict):
            # Pour les messages de progression, convertir en chaîne lisible
            message = str(message)
        
        # Timestamp pour le mode texte
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if self.text_mode:
            # Mode texte standard
            log_message = f"[{timestamp}] [{level.upper()}] {message}"
            
            # Écrire dans le fichier si configuré
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(log_message + '\n')
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")
            
            # Toujours afficher sur stdout
            print(log_message)
        
        else:
            # Mode JSONL (inchangé)
            log_entry: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "level": level.lower(),
                "plugin_name": self.plugin_name,
                "instance_id": self.instance_id,
                "target_ip": target_ip,
                "message": str(message)
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
            except Exception as e:
                internal_logger.error(f"Erreur lors de l'écriture sur stdout: {e}")

    def _create_text_progress_bar(self, current: int, total: int, width: int = 20, 
                                  pre_text: str = "", post_text: str = "", color: str = "blue") -> str:
        """
        Crée une barre de progression en texte.
        
        Args:
            current (int): Étape actuelle.
            total (int): Nombre total d'étapes.
            width (int): Largeur de la barre.
            pre_text (str): Texte avant la barre.
            post_text (str): Texte après la barre.
            color (str): Couleur (ignorée en mode texte).
        
        Returns:
            str: Chaîne représentant la barre de progression.
        """
        # Calculer le pourcentage
        percentage = (current / total) * 100 if total > 0 else 0
        
        # Calculer la partie remplie de la barre
        filled_length = int(width * current / total)
        
        # Construire la barre
        bar = '█' * filled_length + '-' * (width - filled_length)
        
        # Texte complet de la barre
        return f"{pre_text} [{bar}] {percentage:.1f}% {post_text}".strip()

    def _emit_bar(self, id: str, current: int):
        """Construit et émet le message de barre de progression."""
        if id not in self.bars: 
            return

        bar_data = self.bars[id]
        total = bar_data["total_steps"]
        current_clamped = min(max(0, current), total)
        
        if self.text_mode:
            # Mode texte : afficher la barre directement
            bar_str = self._create_text_progress_bar(
                current_clamped, 
                total, 
                width=bar_data["bar_width"], 
                pre_text=bar_data["pre_text"], 
                post_text=bar_data["post_text"]
            )
            
            # Afficher en texte
            print(bar_str)
            
            # Optionnel : écrire dans le fichier log
            if self.log_file:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(bar_str + '\n')
                except Exception as e:
                    internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")
        
        else:
            # Mode JSONL (inchangé, logique actuelle)
            percentage = (float(current_clamped) / total * 100.0) if total > 0 else 100.0

            width = bar_data["bar_width"]
            filled_width = int(width * current_clamped / total) if total > 0 else width
            filled_width = min(max(0, filled_width), width)
            bar_str = (bar_data["filled_char"] * filled_width +
                       bar_data["empty_char"] * (width - filled_width))

            progress_message = {
                "type": "progress-text",
                "data": {
                    "id": id,
                    "percentage": int(round(percentage)),
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
            self._emit_log("progress-text", progress_message)

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
        total_steps = max(1, total) # Assurer au moins 1 étape
        
        # Créer ou mettre à jour la barre
        self.progressbars[bar_id] = {"total_steps": total_steps, "current_step": 0}
        
        if self.text_mode:
            # En mode texte, on n'émet pas de message spécial
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
            # Créer la barre par défaut si elle manque et qu'on essaie de l'utiliser
            if bar_id == self.default_pb_id:
                 self._init_default_pb()
            else:
                 return 0 # Ne peut pas avancer une barre inconnue non-défaut

        pb_data = self.progressbars[bar_id]
        if current_step is not None:
            pb_data["current_step"] = min(max(0, current_step), pb_data["total_steps"])
        else:
            pb_data["current_step"] = min(pb_data["current_step"] + 1, pb_data["total_steps"])

        if self.text_mode:
            # En mode texte, afficher la progression
            current = pb_data["current_step"]
            total = pb_data["total_steps"]
            percentage = (current / total) * 100
            print(f"Progression : {current}/{total} ({percentage:.1f}%)")
            
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
            # En mode texte, ne rien faire
            return

        progress_message = {
            "type": "progress", # Type spécifique pour l'UI
            "data": {
                "id": bar_id, # Inclure l'ID pour l'UI
                "percentage": percentage,
                "current_step": current,
                "total_steps": total
            }
        }
        self._emit_log("progress", progress_message) # Utiliser le dict comme message

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
                print(fin_text)
                
                # Écrire dans le fichier log si configuré
                if self.log_file:
                    try:
                        with open(self.log_file, 'a', encoding='utf-8') as f:
                            f.write(fin_text + '\n')
                    except Exception as e:
                        internal_logger.error(f"Erreur d'écriture dans le fichier de log {self.log_file}: {e}")
            else:
                # Mode JSONL : émettre un message spécial
                progress_message = {
                    "type": "progress-text",
                    "data": {
                        "id": id,
                        "status": "stop", # Indique la suppression
                        "pre_text": bar_data["pre_text"],
                        "post_text": bar_data["post_text"],
                        "color": bar_data["color"],
                    }
                }
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