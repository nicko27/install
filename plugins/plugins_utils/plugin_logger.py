#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module utilitaire pour les logs standardisés en format JSONL ou texte standard.
Supporte plusieurs barres de progression avec styles personnalisables.
Version optimisée pour améliorer la réactivité des logs et permettre
l'affichage en temps réel dans l'interface Textual ou en mode texte.
"""

import os
import logging
import time
import tempfile
import json
import sys
import queue
import threading
import traceback
import shlex # Importer shlex ici si nécessaire (même si pas utilisé directement)
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple, Deque
from collections import deque

# Logger interne pour les problèmes du PluginLogger lui-même
internal_logger = logging.getLogger(__name__)
internal_logger.setLevel(logging.WARNING)
# Configuration simple pour voir les logs internes si besoin (à ajuster)
# logging.basicConfig()
# internal_logger.addHandler(logging.StreamHandler(sys.stderr))


# Couleurs ANSI pour le mode texte
ANSI_COLORS = {
    "reset": "\033[0m",
    "info": "\033[0;37m",      # Blanc
    "warning": "\033[0;33m",   # Jaune
    "error": "\033[0;31m",     # Rouge
    "success": "\033[0;32m",   # Vert
    "debug": "\033[0;36m",     # Cyan
    "start": "\033[0;34m",     # Bleu
    "end": "\033[0;35m",       # Magenta
    "timestamp": "\033[0;90m", # Gris
    "target_ip": "\033[0;95m", # Magenta clair
    "progress_bar": "\033[0;34m", # Bleu pour la barre par défaut
    "progress_text": "\033[0;37m"  # Blanc pour le texte autour
}
# Couleurs pour les barres visuelles (peut être étendu)
BAR_COLORS = {
    "blue": "\033[0;34m",
    "green": "\033[0;32m",
    "red": "\033[0;31m",
    "yellow": "\033[0;33m",
    "cyan": "\033[0;36m",
    "magenta": "\033[0;35m",
    "white": "\033[0;37m",
}


def is_debugger_active() -> bool:
    """Détecte si un débogueur est actif."""
    if hasattr(sys, 'gettrace') and sys.gettrace(): return True
    debug_env_vars = ['PYTHONBREAKPOINT', 'VSCODE_DEBUG', 'PYCHARM_DEBUG', 'PYDEVD_USE_FRAME_EVAL', 'DEBUG']
    if any(os.environ.get(var) for var in debug_env_vars): return True
    if 'pydevd' in sys.modules or 'debugpy' in sys.modules: return True
    return False


class PluginLogger:
    """
    Gère la journalisation standardisée et les barres de progression
    pour les plugins avec optimisations pour l'affichage en temps réel.
    """

    def __init__(self, plugin_name: Optional[str] = None,
                 instance_id: Optional[Union[str, int]] = None,
                 text_mode: bool = False,
                 debug_mode: bool = False,
                 ssh_mode: bool = False,
                 debugger_mode: Optional[bool] = None,
                 bar_width: int = 20):
        """Initialise le logger."""
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.debug_mode = debug_mode
        self.ssh_mode = ssh_mode
        self.bar_width = max(5, bar_width)
        self.text_mode = text_mode # Initialiser avant la détection debugger

        # Auto-détection du mode debugger
        if debugger_mode is None:
            self.debugger_mode = is_debugger_active()
        else:
            self.debugger_mode = debugger_mode

        # Détection auto mode texte si pas SSH, pas déjà texte, et TTY
        if not self.text_mode and not self.ssh_mode and sys.stdout.isatty():
            if not os.environ.get("TEXTUAL_APP"): # Ne pas activer si dans Textual
                self.text_mode = True
                internal_logger.debug("PluginLogger: Mode texte détecté automatiquement")

        # Forcer mode texte si debugger actif
        if self.debugger_mode:
            if not self.text_mode:
                internal_logger.debug("PluginLogger: Mode débogueur détecté, forçage du mode texte.")
            self.text_mode = True

        # Barres numériques (pourcentage, principalement pour JSONL)
        self.progressbars: Dict[str, Dict[str, Any]] = {}
        self.default_pb_id = (
            f"pb_default_{self.plugin_name or 'plugin'}_{self.instance_id or '0'}"
            f"_{int(time.time()*1000)}" # Plus de précision pour éviter collisions
        )
        self._init_default_pb()

        # Barres visuelles (texte)
        self.bars: Dict[str, Dict[str, Any]] = {}
        self.use_visual_bars = True # Activé par défaut, peut être changé via enable_visual_bars
        self.default_filled_char = "■"
        self.default_empty_char = "□"

        # Fichiers de logs
        self.log_file: Optional[str] = None
        self.init_logs()

        # Verrou pour la synchronisation des écritures (surtout stdout/stderr)
        self._write_lock = threading.RLock()

        # Anti-duplication (pour logs texte classiques)
        self._seen_messages: Dict[tuple, tuple] = {}
        self._seen_messages_maxlen = 50

        # Throttling pour la progression
        self._last_progress_update: Dict[str, float] = {}
        # Réduire le throttle pour une meilleure réactivité visuelle
        self._progress_throttle = 0.03 if not self.debug_mode else 0.01

        # File d'attente pour le traitement chronologique des messages
        self._message_queue: queue.Queue[Tuple[str, Any, Optional[str], bool, int, float]] = queue.Queue()
        self._flush_interval = 0.015 if not self.debug_mode else 0.005
        self._last_flush_time = 0.0
        self._batch_size = 5 if not self.debug_mode else 1

        # Thread de traitement
        self._running = True
        self._message_thread: Optional[threading.Thread] = None
        if not self.debugger_mode: # Ne pas démarrer en mode débogueur pour éviter les blocages
            self._message_thread = threading.Thread(
                target=self._process_message_queue, daemon=True
            )
            self._message_thread.start()
            internal_logger.debug("PluginLogger: Thread de traitement des messages démarré.")
        else:
            internal_logger.debug("PluginLogger: Thread de traitement non démarré (mode débogueur).")

        # Compteur pour ordre chronologique strict
        self._message_counter = 0
        self._message_counter_lock = threading.Lock()

    def _init_default_pb(self):
        """Initialise la barre de progression numérique par défaut."""
        if self.default_pb_id not in self.progressbars:
            self.progressbars[self.default_pb_id] = {
                "total_steps": 1,
                "current_step": 0
            }

    def init_logs(self):
        """Initialise le chemin du fichier log."""
        if self.plugin_name is None or self.instance_id is None:
            internal_logger.debug("PluginLogger: Nom ou ID de plugin manquant, initialisation logs ignorée.")
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
                # Essayer de remonter depuis __file__
                project_root = Path(__file__).resolve().parents[2] # Remonter de plugins_utils -> plugins -> pcUtils
                log_dir_path = project_root / "logs"
            except (NameError, IndexError):
                # Fallback si __file__ n'est pas défini ou structure inattendue
                log_dir_path = Path("logs") # Relatif au CWD

        if log_dir_path:
            try:
                log_dir_path.mkdir(parents=True, exist_ok=True)
                # Permissions larges en mode SSH ou root pour l'accès par l'interface
                if self.ssh_mode or (hasattr(os, 'geteuid') and os.geteuid() == 0):
                    try:
                        os.chmod(log_dir_path, 0o777)
                    except Exception as perm_error:
                        internal_logger.warning(f"PluginLogger: Impossible de chmod 777 {log_dir_path}: {perm_error}")

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"plugin_{self.plugin_name}_{self.instance_id}_{timestamp}.jsonl"
                self.log_file = str(log_dir_path / log_filename)

                # Émettre le chemin en mode SSH pour récupération
                if self.ssh_mode:
                    log_path_msg = {"level": "info", "message": f"LOG_FILE:{self.log_file}"}
                    print(json.dumps(log_path_msg), flush=True)
                internal_logger.info(f"PluginLogger: Fichier log configuré: {self.log_file}")

            except Exception as e:
                internal_logger.error(f"PluginLogger: Erreur config logs {log_dir_path}: {e}", exc_info=True)
                self.log_file = None
        else:
            internal_logger.error("PluginLogger: Impossible de déterminer un répertoire de logs valide.")
            self.log_file = None

    def _get_next_message_id_and_time(self) -> Tuple[int, float]:
        """Obtient un ID unique et le timestamp précis pour un message."""
        with self._message_counter_lock:
            self._message_counter += 1
            # Utiliser time.monotonic() pour un timestamp précis et croissant
            return self._message_counter, time.monotonic()

    def _process_message_queue(self):
        """Processus de traitement continu des messages en file d'attente."""
        while self._running:
            try:
                batch: List[Tuple[str, Any, Optional[str], bool, int, float]] = []
                # Attendre le premier message (avec timeout pour vérifier _running)
                try:
                    first_message = self._message_queue.get(timeout=0.1)
                    batch.append(first_message)
                    self._message_queue.task_done()
                except queue.Empty:
                    continue # Pas de message, revérifier _running

                # Collecter d'autres messages disponibles (non bloquant)
                while len(batch) < self._batch_size:
                    try:
                        message = self._message_queue.get_nowait()
                        batch.append(message)
                        self._message_queue.task_done()
                    except queue.Empty:
                        break # Plus de messages pour l'instant

                # Trier les messages par ID pour garantir l'ordre chronologique
                batch.sort(key=lambda x: x[4]) # Tri par message_id (index 4)

                # Traiter le lot
                if batch:
                    self._process_message_batch(batch)

            except Exception as e:
                internal_logger.error(f"PluginLogger: Erreur traitement queue: {e}", exc_info=True)
                time.sleep(0.1) # Éviter boucle d'erreur

    def _process_message_batch(self, messages: List[Tuple[str, Any, Optional[str], bool, int, float]]):
        """Traite un lot de messages, écrivant sur stdout et/ou fichier."""
        # Les messages sont déjà triés par ID chronologique
        log_lines_to_write = []
        console_outputs = []

        for level, message, target_ip, _, msg_id, _ in messages:
            # Préparer l'entrée pour le fichier log JSONL
            if self.log_file:
                log_entry_file = {
                    "timestamp": datetime.now().isoformat(), # Timestamp de traitement
                    "level": level.lower(),
                    "plugin_name": self.plugin_name,
                    "instance_id": self.instance_id,
                    "target_ip": target_ip,
                    "message_id": msg_id, # Ajouter l'ID pour débogage
                    "message": message # Peut être str ou dict (pour progress)
                }
                log_entry_file = {k: v for k, v in log_entry_file.items() if v is not None}
                try:
                    log_lines_to_write.append(json.dumps(log_entry_file, ensure_ascii=False))
                except Exception as json_err:
                    internal_logger.warning(f"PluginLogger: Erreur JSON sérialisation log file: {json_err} - Data: {log_entry_file}")


            # Préparer la sortie console (Texte ou JSONL)
            if self.text_mode:
                # Mode texte: formatage avec couleurs ANSI
                timestamp_txt = datetime.now().strftime("%H:%M:%S")
                color = ANSI_COLORS.get(level.lower(), ANSI_COLORS["info"])
                target_info = f"{ANSI_COLORS['target_ip']}@{target_ip}{ANSI_COLORS['reset']} " if target_ip else ""

                # Traitement spécial pour les barres de progression (qui ne sont pas gérées ici en mode texte)
                if level.lower() in ["progress", "progress-text"]:
                    # Ne rien afficher sur la console pour les mises à jour de barres
                    # Elles sont gérées par _emit_bar directement sur sys.stdout
                    continue

                # Traiter les messages standard
                msg_str = str(message) # Convertir message en str pour affichage
                console_line = (
                    f"{ANSI_COLORS['timestamp']}{timestamp_txt}{ANSI_COLORS['reset']} "
                    f"{color}[{level.upper():<7}]{ANSI_COLORS['reset']} " # Niveau sur 7 caractères
                    f"{target_info}{msg_str}"
                )
                console_outputs.append(console_line)
            else:
                # Mode JSONL pour stdout (compatible Textual)
                log_entry_stdout = {
                    "timestamp": datetime.now().isoformat(),
                    "level": level.lower(),
                    "plugin_name": self.plugin_name,
                    "instance_id": self.instance_id,
                    "target_ip": target_ip,
                    "message": message # Garder le message tel quel (str ou dict)
                }
                log_entry_stdout = {k: v for k, v in log_entry_stdout.items() if v is not None}
                try:
                    console_outputs.append(json.dumps(log_entry_stdout, ensure_ascii=False))
                except Exception as json_err:
                     internal_logger.warning(f"PluginLogger: Erreur JSON sérialisation stdout: {json_err} - Data: {log_entry_stdout}")

        # Écrire sur les sorties avec verrou pour éviter l'entrelacement
        with self._write_lock:
            # Écrire dans le fichier log
            if self.log_file and log_lines_to_write:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        for line in log_lines_to_write:
                            f.write(line + '\n')
                except Exception as e:
                    internal_logger.error(f"PluginLogger: Erreur écriture log {self.log_file}: {e}", exc_info=True)

            # Écrire sur stdout
            if console_outputs:
                try:
                    output_str = "\n".join(console_outputs) + "\n"
                    sys.stdout.write(output_str)
                    sys.stdout.flush()
                except Exception as e:
                    internal_logger.error(f"PluginLogger: Erreur écriture stdout: {e}", exc_info=True)

    def _emit_log(self, level: str, message: Any, target_ip: Optional[str] = None):
        """Met un message dans la file d'attente pour traitement chronologique."""
        msg_id, timestamp = self._get_next_message_id_and_time()

        # En mode débogueur, traiter immédiatement et de manière synchrone
        if self.debugger_mode:
            batch = [(level, message, target_ip, True, msg_id, timestamp)]
            self._process_message_batch(batch)
            return

        # Vérifier duplication pour les messages texte simples
        is_progress = level.lower() in ["progress", "progress-text"]
        allow_dedup = not is_progress and isinstance(message, str) and not self.debug_mode

        if allow_dedup:
            message_key = (level, message, target_ip)
            now = time.monotonic()
            last_seen_time, count = self._seen_messages.get(message_key, (0.0, 0))

            # Règle de déduplication : ignorer si vu > 2 fois dans la dernière seconde
            if now - last_seen_time < 1.0 and count >= 3:
                 # Mettre à jour le compteur mais ne pas émettre
                 self._seen_messages[message_key] = (now, count + 1)
                 # Logguer occasionnellement un résumé
                 if count % 20 == 0: # Logguer toutes les 20 répétitions ignorées
                     summary_msg = f"Message répété {count+1} fois: {message}"
                     summary_id, summary_ts = self._get_next_message_id_and_time()
                     self._message_queue.put(("warning", summary_msg, target_ip, False, summary_id, summary_ts))
                 return # Ignorer le message original

            # Mettre à jour le cache de messages vus
            self._seen_messages[message_key] = (now, count + 1)
            # Limiter la taille du cache
            if len(self._seen_messages) > self._seen_messages_maxlen:
                try:
                    oldest_key = min(self._seen_messages, key=lambda k: self._seen_messages[k][0])
                    del self._seen_messages[oldest_key]
                except ValueError: # Peut arriver si le dict est vide, très rare
                    pass

        # Mettre en file d'attente : (level, message, target_ip, force_flush, message_id, timestamp)
        # force_flush n'est plus vraiment utilisé ici, on traite par lots
        self._message_queue.put((level, message, target_ip, False, msg_id, timestamp))

    # --- Méthodes publiques de logging ---
    # Elles appellent toutes _emit_log

    def info(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'information."""
        self._emit_log("info", message, target_ip)

    def warning(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'avertissement."""
        self._emit_log("warning", message, target_ip)

    def error(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message d'erreur."""
        self._emit_log("error", message, target_ip)

    def success(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de succès."""
        self._emit_log("success", message, target_ip)

    def debug(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de débogage (uniquement si debug_mode=True)."""
        if self.debug_mode:
            self._emit_log("debug", message, target_ip)

    def start(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de début d'opération."""
        self._emit_log("start", message, target_ip)

    def end(self, message: str, target_ip: Optional[str] = None):
        """Enregistre un message de fin d'opération."""
        self._emit_log("end", message, target_ip)

    # --- Gestion Progression Numérique (pour JSONL) ---

    def set_total_steps(self, total: int, pb_id: Optional[str] = None):
        """Définit le nombre total d'étapes pour une progression numérique."""
        bar_id = pb_id or self.default_pb_id
        total_steps = max(1, total)
        self.progressbars[bar_id] = {"total_steps": total_steps, "current_step": 0}
        internal_logger.debug(f"PluginLogger: Progression numérique '{bar_id}' initialisée: {total_steps} étapes.")
        # Émettre un message initial à 0% (sera mis en queue)
        self._emit_progress_update(bar_id)

    def next_step(self, pb_id: Optional[str] = None, current_step: Optional[int] = None) -> int:
        """Avance la progression numérique ou la définit."""
        bar_id = pb_id or self.default_pb_id
        if bar_id not in self.progressbars:
            internal_logger.warning(f"PluginLogger: next_step pour barre numérique inconnue: {bar_id}")
            if bar_id == self.default_pb_id: self._init_default_pb()
            else: return 0

        pb_data = self.progressbars[bar_id]
        total = pb_data["total_steps"]
        if current_step is not None:
            pb_data["current_step"] = min(max(0, current_step), total)
        else:
            pb_data["current_step"] = min(pb_data["current_step"] + 1, total)

        current = pb_data["current_step"]

        # Appliquer le throttling (sauf en mode debug)
        if not self.debug_mode:
            now = time.monotonic()
            last_time = self._last_progress_update.get(bar_id, 0.0)
            if now - last_time < self._progress_throttle:
                return current
            self._last_progress_update[bar_id] = now

        # Mettre en file d'attente la mise à jour
        self._emit_progress_update(bar_id)
        return current

    def _emit_progress_update(self, bar_id: str):
        """Met en queue le message JSONL pour la progression numérique."""
        if bar_id not in self.progressbars: return
        if self.text_mode: return # Pas de log numérique en mode texte

        pb_data = self.progressbars[bar_id]
        current = pb_data["current_step"]
        total = pb_data["total_steps"]
        percentage = (float(current) / total) if total > 0 else 1.0

        progress_message = {
            "type": "progress",
            "data": {
                "id": bar_id,
                "percentage": percentage,
                "current_step": current,
                "total_steps": total
            }
        }
        self._emit_log("progress", progress_message)

    # --- Gestion Progression Visuelle (Texte ou JSONL) ---

    def enable_visual_bars(self, enable: bool = True):
        """Active/désactive l'utilisation des barres de progression visuelles."""
        self.use_visual_bars = enable
        internal_logger.debug(f"PluginLogger: Barres visuelles {'activées' if enable else 'désactivées'}.")


    def create_bar(self, id: str, total: int = 1, description: str = "",
                   pre_text: Optional[str] = None, # Nouveau : texte avant la barre
                   post_text: str = "",
                   color: str = "blue",
                   filled_char: Optional[str] = None,
                   empty_char: Optional[str] = None,
                   bar_width: Optional[int] = None):
        """Crée et affiche une nouvelle barre de progression visuelle."""
        if not self.use_visual_bars: return # Ne rien faire si désactivé
        if id in self.bars:
            internal_logger.warning(f"PluginLogger: Recréation barre visuelle existante: {id}")

        width = bar_width if bar_width is not None else self.bar_width
        f_char = filled_char or self.default_filled_char
        e_char = empty_char or self.default_empty_char

        # Utiliser description comme pre_text par défaut si pre_text n'est pas fourni
        final_pre_text = pre_text if pre_text is not None else description

        self.bars[id] = {
            "total_steps": max(1, total),
            "current_step": 0,
            "pre_text": final_pre_text,
            "post_text": post_text,
            "color": color,
            "filled_char": f_char,
            "empty_char": e_char,
            "bar_width": width,
            "_last_line_len": 0 # Pour le mode texte
        }
        internal_logger.debug(f"PluginLogger: Barre visuelle '{id}' créée: {total} étapes, pre='{final_pre_text}'.")
        # Afficher la barre initiale à 0% (sera mis en queue)
        self._emit_bar(id, 0)

    def update_bar(self, id: str, current: int, total: Optional[int] = None,
                   pre_text: Optional[str] = None, post_text: Optional[str] = None,
                   color: Optional[str] = None):
                   # Ne pas permettre de changer le style de la barre en cours de route ici
                   # utiliser delete_bar / create_bar pour ça
        """Met à jour une barre visuelle existante avec throttling."""
        if not self.use_visual_bars or id not in self.bars:
            # Ignorer si barres désactivées ou ID inconnu
            # internal_logger.warning(f"PluginLogger: Tentative update barre visuelle inexistante/désactivée: {id}")
            return

        # Appliquer le throttling (sauf en mode debug)
        if not self.debug_mode:
            now = time.monotonic()
            bar_throttle_id = f"textbar_{id}"
            last_time = self._last_progress_update.get(bar_throttle_id, 0.0)
            if now - last_time < self._progress_throttle:
                return
            self._last_progress_update[bar_throttle_id] = now

        # Mettre à jour les données stockées
        bar_data = self.bars[id]
        bar_data["current_step"] = current
        if total is not None: bar_data["total_steps"] = max(1, total)
        if pre_text is not None: bar_data["pre_text"] = pre_text
        if post_text is not None: bar_data["post_text"] = post_text
        if color is not None: bar_data["color"] = color

        # Émettre la mise à jour (sera mis en queue)
        self._emit_bar(id, current)

    def next_bar(self, id: str, current_step: Optional[int] = None,
                 pre_text: Optional[str] = None, post_text: Optional[str] = None) -> int:
        """Avance ou définit l'étape d'une barre visuelle avec throttling."""
        if not self.use_visual_bars or id not in self.bars:
             # internal_logger.warning(f"PluginLogger: next_bar pour barre visuelle inexistante/désactivée: {id}")
             return 0

        bar_data = self.bars[id]
        total = bar_data["total_steps"]
        if current_step is not None:
            bar_data["current_step"] = min(max(0, current_step), total)
        else:
            bar_data["current_step"] = min(bar_data["current_step"] + 1, total)

        # Mettre à jour les textes si fournis
        if pre_text is not None: bar_data["pre_text"] = pre_text
        if post_text is not None: bar_data["post_text"] = post_text

        current = bar_data["current_step"]

        # Appliquer le throttling (sauf en mode debug)
        if not self.debug_mode:
            now = time.monotonic()
            bar_throttle_id = f"textbar_{id}"
            last_time = self._last_progress_update.get(bar_throttle_id, 0.0)
            if now - last_time < self._progress_throttle:
                return current
            self._last_progress_update[bar_throttle_id] = now

        # Émettre la mise à jour (sera mis en queue)
        self._emit_bar(id, current)
        return current

    def _emit_bar(self, id: str, current: int):
        """Construit et met en queue le message pour la barre visuelle."""
        if id not in self.bars: return

        bar_data = self.bars[id]
        total = bar_data["total_steps"]
        current_clamped = min(max(0, current), total)
        width = bar_data["bar_width"]
        percentage = int((current_clamped / total) * 100) if total > 0 else 100
        filled_width = int(width * current_clamped / total) if total > 0 else width
        filled_width = min(max(0, filled_width), width)

        bar_str = (bar_data["filled_char"] * filled_width +
                   bar_data["empty_char"] * (width - filled_width))

        if self.text_mode:
            with self._write_lock:
                try:
                    timestamp_txt = datetime.now().strftime("%H:%M:%S")
                    # Utiliser un niveau spécifique pour la barre, ex: PROG
                    level_txt = "[PROGRES]" # 7 caractères comme les autres niveaux
                    bar_color_ansi = BAR_COLORS.get(bar_data["color"], ANSI_COLORS["progress_bar"])

                    # Construire la ligne complète AVEC le préfixe standard
                    prefix = (
                        f"{ANSI_COLORS['timestamp']}{timestamp_txt}{ANSI_COLORS['reset']} "
                        f"{ANSI_COLORS['progress_bar']}{level_txt}{ANSI_COLORS['reset']} " # Utiliser couleur progress_bar
                    )
                    bar_content = (
                        f"{ANSI_COLORS['progress_text']}{bar_data['pre_text']} {ANSI_COLORS['reset']}"
                        f"[{bar_color_ansi}{bar_str}{ANSI_COLORS['reset']}]"
                        f"{ANSI_COLORS['progress_text']} {percentage}% {bar_data['post_text']}{ANSI_COLORS['reset']}"
                    )
                    bar_display = prefix + bar_content

                    # Calculer la longueur visible pour l'effacement (sans codes ANSI)
                    visible_len = len(f"{timestamp_txt} {level_txt} {bar_data['pre_text']} [{bar_str}] {percentage}% {bar_data['post_text']}")
                    padding = " " * (bar_data.get("_last_line_len", 0) - visible_len)

                    sys.stdout.write(f"\r{bar_display}{padding}")
                    sys.stdout.flush()
                    bar_data["_last_line_len"] = visible_len
                except Exception as e:
                     internal_logger.error(f"PluginLogger: Erreur écriture barre texte: {e}", exc_info=True)

        else:
            # Mode JSONL : Envoyer via la queue _emit_log
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
                    "bar": bar_str # La chaîne de la barre elle-même
                }
            }
            self._emit_log("progress-text", progress_message)

    def delete_bar(self, id: str):
        """Supprime une barre de progression visuelle."""
        if not self.use_visual_bars: return
        if id in self.bars:
            bar_data = self.bars.pop(id) # Retirer du dict immédiatement
            internal_logger.debug(f"PluginLogger: Suppression barre visuelle: {id}")

            if self.text_mode:
                # Mode texte : Effacer la ligne et passer à la suivante
                with self._write_lock:
                    try:
                        last_len = bar_data.get("_last_line_len", 0)
                        # Effacer la ligne et aller au début
                        sys.stdout.write(f"\r{' ' * last_len}\r")
                        sys.stdout.flush()
                        # Note: Pas besoin de print("\n") ici, le prochain log normal le fera.
                        # Si on voulait un log de complétion spécifique ici, on le ferait via _emit_log:
                        # completion_msg = f"Tâche '{bar_data.get('pre_text', id)}' terminée."
                        # self.info(completion_msg) # Sera mis en queue et affiché normalement
                    except Exception as e:
                         internal_logger.error(f"PluginLogger: Erreur nettoyage barre texte: {e}", exc_info=True)
            else:
                # Mode JSONL : Envoyer un message de statut "stop" via la queue
                stop_message = {
                    "type": "progress-text",
                    "data": { "id": id, "status": "stop" }
                }
                self._emit_log("progress-text", stop_message)
                print("\n")
        else:
            internal_logger.warning(f"PluginLogger: Tentative delete barre visuelle inexistante: {id}")

    def set_default_bar_style(self, filled_char: str, empty_char: str):
        """Définit le style par défaut pour les nouvelles barres visuelles."""
        self.default_filled_char = filled_char
        self.default_empty_char = empty_char

    def set_default_bar_width(self, width: int):
        """Définit la largeur par défaut pour les nouvelles barres visuelles."""
        self.bar_width = max(5, width)

    def flush(self):
        """Force le traitement immédiat des messages en attente."""
        if self.debugger_mode: return # Pas de flush en mode débogueur

        try:
            all_messages = []
            while not self._message_queue.empty():
                try:
                    all_messages.append(self._message_queue.get_nowait())
                    self._message_queue.task_done()
                except queue.Empty:
                    break

            if all_messages:
                internal_logger.debug(f"PluginLogger: Flush manuel de {len(all_messages)} messages.")
                # Trier par ID chronologique
                all_messages.sort(key=lambda x: x[4])
                self._process_message_batch(all_messages)
            else:
                 # Forcer un flush stdout même si la queue est vide (utile après barre texte)
                 with self._write_lock:
                      try:
                           sys.stdout.flush()
                      except Exception: pass

        except Exception as e:
            internal_logger.error(f"PluginLogger: Erreur lors du flush: {e}", exc_info=True)

    def shutdown(self):
        """Arrête proprement le thread de traitement des messages."""
        if self.debugger_mode:
            internal_logger.debug("PluginLogger: Shutdown ignoré (mode débogueur).")
            return

        if not self._running: return # Déjà arrêté

        internal_logger.debug("PluginLogger: Arrêt en cours...")
        self._running = False

        # Donner un peu de temps au thread pour traiter les derniers messages
        if self._message_thread and self._message_thread.is_alive():
             try:
                  self._message_queue.join() # Attendre que la queue soit vide
             except Exception as e:
                  internal_logger.warning(f"PluginLogger: Erreur durant queue.join() : {e}")


        # Flush final explicite (au cas où join n'aurait pas tout traité)
        self.flush()

        # Attendre la fin du thread (avec timeout)
        if self._message_thread and self._message_thread.is_alive():
            self._message_thread.join(timeout=0.5)
            if self._message_thread.is_alive():
                 internal_logger.warning("PluginLogger: Thread de traitement n'a pas pu être arrêté proprement.")

        internal_logger.debug("PluginLogger: Arrêt terminé.")

    def __del__(self):
        """Nettoyage lors de la destruction."""
        try:
            # S'assurer que le logger est arrêté pour éviter les fuites de thread
            if self._running:
                self.shutdown()
        except Exception:
            # Ignorer les erreurs dans le destructeur
            pass