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
import shlex
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple, Deque
from collections import deque

# Logger interne pour les problèmes du PluginLogger lui-même
internal_logger = logging.getLogger(__name__)
internal_logger.setLevel(logging.WARNING)
# Configuration simple pour voir les logs internes si besoin (à ajuster)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
handler.setFormatter(formatter)
internal_logger.addHandler(handler)

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


def is_debugger_active(log_levels: Optional[Dict[str, str]] = None) -> bool:
    """Détecte si un débogueur est actif - version robuste."""
    # Méthode 1: Vérifier sys.gettrace
    if hasattr(sys, 'gettrace') and sys.gettrace():
        internal_logger.debug("Débogueur détecté via sys.gettrace()")
        return True

    # Méthode 2: Vérifier les variables d'environnement
    debug_env_vars = [
        'PYTHONBREAKPOINT', 'VSCODE_DEBUG', 'PYCHARM_DEBUG',
        'PYDEVD_USE_FRAME_EVAL', 'DEBUG', 'TEXTUAL_DEBUG',
        'PYDEVD_LOAD_VALUES_ASYNC', 'DEBUGPY_LAUNCHER_PORT'
    ]
    for var in debug_env_vars:
        if os.environ.get(var):
            internal_logger.debug(f"Débogueur détecté via variable d'environnement: {var}")
            return True

    # Méthode 3: Vérifier les modules de débogage connus
    debug_modules = ['pydevd', 'debugpy', '_pydevd_bundle', 'pdb']
    for mod in debug_modules:
        if mod in sys.modules:
            internal_logger.debug(f"Débogueur détecté via module: {mod}")
            return True

    # Méthode 4: Vérifier si nous sommes sous IPython
    try:
        if 'IPython' in sys.modules:
            internal_logger.debug("IPython détecté")
            return True
        # ou via __IPYTHON__ dans builtins
        import builtins
        if hasattr(builtins, '__IPYTHON__'):
            internal_logger.debug("IPython détecté via __IPYTHON__")
            return True
    except Exception:
        pass

    # Méthode 5: Vérifier si la variable d'environnement FORCE_DEBUG_MODE est définie
    if os.environ.get('FORCE_DEBUG_MODE'):
        internal_logger.debug("Mode débogueur forcé via FORCE_DEBUG_MODE")
        return True

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
        """
        Initialise le logger.

        Args:
            plugin_name: Nom du plugin (utilisé dans les logs)
            instance_id: ID d'instance (utilisé dans les logs)
            text_mode: Si True, affiche du texte formaté ANSI au lieu de JSON
            debug_mode: Mode debug avec plus de verbosité
            ssh_mode: Mode spécial pour l'exécution SSH
            debugger_mode: Force le mode débogueur (détecté automatiquement si None)
            bar_width: Largeur des barres de progression visuelles
        """
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.debug_mode = debug_mode
        self.ssh_mode = ssh_mode
        self.bar_width = max(5, bar_width)
        self.text_mode = text_mode # Initialiser avant la détection debugger

        # Auto-détection du mode debugger
        if debugger_mode is None:
            self.debugger_mode = is_debugger_active()
            if self.debugger_mode:
                internal_logger.info("Mode débogueur détecté automatiquement")
        else:
            self.debugger_mode = debugger_mode
            if self.debugger_mode:
                internal_logger.info("Mode débogueur forcé par l'utilisateur")

        # Détection auto mode texte si pas SSH, pas déjà texte, et TTY
        if not self.text_mode and not self.ssh_mode and sys.stdout.isatty():
            if not os.environ.get("TEXTUAL_APP"): # Ne pas activer si dans Textual
                self.text_mode = True
                internal_logger.debug("Mode texte détecté automatiquement (terminal TTY)")

        # Forcer mode texte si debugger actif pour éviter les blocages
        if self.debugger_mode and not self.text_mode:
            internal_logger.info("Mode débogueur détecté, forçage du mode texte")
            self.text_mode = False

        # Afficher des infos de configuration pour aider au débogage
        internal_logger.info(f"PluginLogger: plugin={plugin_name}, instance={instance_id}, "
                            f"text_mode={self.text_mode}, debug_mode={debug_mode}, "
                            f"ssh_mode={ssh_mode}, debugger_mode={self.debugger_mode}")

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

        # Ne jamais démarrer le thread en mode débogueur pour éviter les blocages
        # ou utiliser un traitement synchrone avec des timeouts courts
        if not self.debugger_mode:
            self._message_thread = threading.Thread(
                target=self._process_message_queue,
                daemon=True  # Toujours daemon pour éviter de bloquer à la sortie
            )
            self._message_thread.start()
            internal_logger.debug("Thread de traitement des messages démarré")
        else:
            internal_logger.debug("Thread de traitement non démarré (mode débogueur)")

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

    def init_logs(self, log_levels: Optional[Dict[str, str]] = None):
        """Initialise le chemin du fichier log."""
        if self.plugin_name is None or self.instance_id is None:
            internal_logger.debug("Plugin name ou ID manquant, initialisation logs ignorée")
            return

        # Déterminer le répertoire des logs
        env_log_dir = os.environ.get('PCUTILS_LOG_DIR')
        log_dir_path: Optional[Path] = None

        if env_log_dir and os.path.isdir(env_log_dir):
            log_dir_path = Path(env_log_dir)
            internal_logger.debug(f"Répertoire logs trouvé via PCUTILS_LOG_DIR: {log_dir_path}")
        elif self.ssh_mode:
            log_dir_path = Path(tempfile.gettempdir()) / 'pcUtils_logs'
            internal_logger.debug(f"Répertoire logs temporaire créé pour SSH: {log_dir_path}")
        else:
            try:
                # Essayer de remonter depuis __file__
                project_root = Path(__file__).resolve().parents[2] # Remonter de plugins_utils -> plugins -> pcUtils
                log_dir_path = project_root / "logs"
                internal_logger.debug(f"Répertoire logs déterminé depuis __file__: {log_dir_path}")
            except (NameError, IndexError):
                # Fallback si __file__ n'est pas défini ou structure inattendue
                log_dir_path = Path("logs") # Relatif au CWD
                internal_logger.debug(f"Répertoire logs fallback au CWD: {log_dir_path}")

        if log_dir_path:
            try:
                log_dir_path.mkdir(parents=True, exist_ok=True)
                internal_logger.debug(f"Répertoire logs créé/vérifié: {log_dir_path}")

                # Permissions larges en mode SSH ou root pour l'accès par l'interface
                if self.ssh_mode or (hasattr(os, 'geteuid') and os.geteuid() == 0):
                    try:
                        os.chmod(log_dir_path, 0o777)
                        internal_logger.debug(f"Permissions étendues appliquées à {log_dir_path}")
                    except Exception as perm_error:
                        internal_logger.warning(f"Impossible de chmod 777 {log_dir_path}: {perm_error}")

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"plugin_{self.plugin_name}_{self.instance_id}_{timestamp}.jsonl"
                self.log_file = str(log_dir_path / log_filename)

                # Émettre le chemin en mode SSH pour récupération
                if self.ssh_mode:
                    log_path_msg = {"level": "info", "message": f"LOG_FILE:{self.log_file}"}
                    print(json.dumps(log_path_msg), flush=True)
                internal_logger.info(f"Fichier log configuré: {self.log_file}")

            except Exception as e:
                internal_logger.error(f"Erreur config logs {log_dir_path}: {e}", exc_info=True)
                self.log_file = None
        else:
            internal_logger.error("Impossible de déterminer un répertoire de logs valide")
            self.log_file = None

    def _get_next_message_id_and_time(self) -> Tuple[int, float]:
        """Obtient un ID unique et le timestamp précis pour un message."""
        with self._message_counter_lock:
            self._message_counter += 1
            # Utiliser time.monotonic() pour un timestamp précis et croissant
            return self._message_counter, time.monotonic()

    def _process_message_queue(self):
        """Processus de traitement continu des messages en file d'attente - version améliorée."""
        internal_logger.debug("Thread de traitement des messages démarré")

        while self._running:
            try:
                batch = []
                # Attendre le premier message (avec timeout court pour vérifier _running)
                try:
                    first_message = self._message_queue.get(timeout=0.05)  # Timeout court pour réactivité
                    batch.append(first_message)
                    self._message_queue.task_done()
                except queue.Empty:
                    # Pas de message, mais faire un flush périodique des sorties pour éviter les blocages
                    with self._write_lock:
                        try:
                            sys.stdout.flush()
                        except Exception:
                            pass
                    # Court délai pour éviter une charge CPU excessive
                    time.sleep(0.01)
                    continue  # Revérifier _running

                # Collecter d'autres messages disponibles (non bloquant)
                max_batch_collect_time = time.time() + 0.01  # Limite de temps pour la collecte (10ms)
                while len(batch) < self._batch_size and time.time() < max_batch_collect_time:
                    try:
                        message = self._message_queue.get_nowait()
                        batch.append(message)
                        self._message_queue.task_done()
                    except queue.Empty:
                        break  # Plus de messages pour l'instant

                # Trier les messages par ID pour garantir l'ordre chronologique
                batch.sort(key=lambda x: x[4])  # Tri par message_id (index 4)

                # Traiter le lot avec une limite de temps
                if batch:
                    self._process_message_batch(batch)

            except Exception as e:
                internal_logger.error(f"Erreur traitement queue: {e}", exc_info=True)
                # En cas d'erreur, pause courte pour éviter boucle d'erreurs à haute fréquence
                time.sleep(0.1)

        internal_logger.debug("Thread de traitement des messages terminé")

    def _process_message_batch(self, messages: List[Tuple[str, Any, Optional[str], bool, int, float]]):
        """
        Traite un lot de messages, écrivant sur stdout et/ou fichier.

        Args:
            messages: Liste de tuples (level, message, target_ip, force_flush, message_id, timestamp)
        """
        # Les messages sont déjà triés par ID chronologique
        log_lines_to_write = []
        console_outputs = []

        for level, message, target_ip, _, msg_id, _ in messages:
            # Préparer l'entrée pour le fichier log JSONL
            if self.log_file:
                log_entry_file = {
                    "timestamp": datetime.now().isoformat(),  # Timestamp de traitement
                    "level": level.lower(),
                    "plugin_name": self.plugin_name,
                    "instance_id": self.instance_id,
                    "target_ip": target_ip,
                    "message_id": msg_id,  # Ajouter l'ID pour débogage/référence
                    "message": message  # Peut être str ou dict (pour progress)
                }
                # Supprimer les champs None pour réduire la taille
                log_entry_file = {k: v for k, v in log_entry_file.items() if v is not None}
                try:
                    log_lines_to_write.append(json.dumps(log_entry_file, ensure_ascii=False))
                except Exception as json_err:
                    internal_logger.warning(f"Erreur JSON sérialisation log file: {json_err} - Data: {log_entry_file}")


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
                # Supprimer les champs None pour réduire la taille
                log_entry_stdout = {k: v for k, v in log_entry_stdout.items() if v is not None}
                try:
                    console_outputs.append(json.dumps(log_entry_stdout, ensure_ascii=False))
                except Exception as json_err:
                     internal_logger.warning(f"Erreur JSON sérialisation stdout: {json_err} - Data: {log_entry_stdout}")

        # Écrire sur les sorties avec verrou pour éviter l'entrelacement
        with self._write_lock:
            # Écrire dans le fichier log
            if self.log_file and log_lines_to_write:
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        for line in log_lines_to_write:
                            f.write(line + '\n')
                except Exception as e:
                    internal_logger.error(f"Erreur écriture log {self.log_file}: {e}", exc_info=True)

            # Écrire sur stdout
            if console_outputs:
                try:
                    output_str = "\n".join(console_outputs) + "\n"
                    sys.stdout.write(output_str)
                    sys.stdout.flush()
                except Exception as e:
                    internal_logger.error(f"Erreur écriture stdout: {e}", exc_info=True)

    def _emit_log(self, level: str, message: Any, target_ip: Optional[str] = None, force_flush: bool = False):
        """
        Met un message dans la file d'attente pour traitement chronologique ou le traite immédiatement en mode débogueur.

        Args:
            level: Niveau du message (info, error, etc.)
            message: Contenu du message (str ou dict pour la progression)
            target_ip: Adresse IP cible pour les logs SSH
            force_flush: Force le traitement immédiat
        """
        msg_id, timestamp = self._get_next_message_id_and_time()

        # En mode débogueur, traiter immédiatement et de manière synchrone
        if self.debugger_mode or force_flush:
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
        self._message_queue.put((level, message, target_ip, force_flush, msg_id, timestamp))

    # --- Méthodes publiques de logging ---
    # Elles appellent toutes _emit_log

    def info(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message d'information.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (bypasse la file d'attente)
        """
        self._emit_log("info", message, target_ip, force_flush)

    def warning(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message d'avertissement.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (bypasse la file d'attente)
        """
        self._emit_log("warning", message, target_ip, force_flush)

    def error(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message d'erreur.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (par défaut True pour les erreurs)
        """
        self._emit_log("error", message, target_ip, force_flush)

    def success(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message de succès.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (par défaut True pour les succès)
        """
        self._emit_log("success", message, target_ip, force_flush)

    def debug(self, message: str, target_ip: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message de débogage (uniquement si debug_mode=True).

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
        """
        if self.debug_mode:
            self._emit_log("debug", message, target_ip)

    def start(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message de début d'opération.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (par défaut True pour début d'opération)
        """
        self._emit_log("start", message, target_ip, force_flush)

    def end(self, message: str, target_ip: Optional[str] = None, force_flush: bool = False, log_levels: Optional[Dict[str, str]] = None):
        """
        Enregistre un message de fin d'opération.

        Args:
            message: Le message à enregistrer
            target_ip: Adresse IP cible optionnelle (pour SSH)
            force_flush: Force l'écriture immédiate (par défaut True pour fin d'opération)
        """
        self._emit_log("end", message, target_ip, force_flush)

    # --- Gestion Progression Numérique (pour JSONL) ---

    def set_total_steps(self, total: int, pb_id: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None):
        """
        Définit le nombre total d'étapes pour une progression numérique.

        Args:
            total: Nombre total d'étapes
            pb_id: Identifiant optionnel de la barre de progression
        """
        bar_id = pb_id or self.default_pb_id
        total_steps = max(1, total)
        self.progressbars[bar_id] = {"total_steps": total_steps, "current_step": 0}
        internal_logger.debug(f"Progression numérique '{bar_id}' initialisée: {total_steps} étapes")
        # Émettre un message initial à 0% (sera mis en queue)
        self._emit_progress_update(bar_id)

    def next_step(self, pb_id: Optional[str] = None, current_step: Optional[int] = None, log_levels: Optional[Dict[str, str]] = None) -> int:
        """
        Avance la progression numérique ou la définit.

        Args:
            pb_id: Identifiant optionnel de la barre de progression
            current_step: Si fourni, définit directement l'étape actuelle

        Returns:
            int: Étape actuelle après mise à jour
        """
        bar_id = pb_id or self.default_pb_id
        if bar_id not in self.progressbars:
            internal_logger.warning(f"next_step pour barre numérique inconnue: {bar_id}")
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
        """
        Met en queue le message JSONL pour la progression numérique.

        Args:
            bar_id: Identifiant de la barre de progression
        """
        if bar_id not in self.progressbars:
            return

        if self.text_mode:
            # En mode texte, on n'émet pas de progression numérique (utilisez les barres visuelles)
            return

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

    def enable_visual_bars(self, enable: bool = True, log_levels: Optional[Dict[str, str]] = None):
        """
        Active/désactive l'utilisation des barres de progression visuelles.

        Args:
            enable: Si True, active les barres visuelles
        """
        self.use_visual_bars = enable
        internal_logger.debug(f"Barres visuelles {'activées' if enable else 'désactivées'}")

    def create_bar(self, id: str, total: int = 1, description: str = "",
                   pre_text: Optional[str] = None, # Texte avant la barre
                   post_text: str = "",
                   color: str = "blue",
                   filled_char: Optional[str] = None,
                   empty_char: Optional[str] = None,
bar_width: Optional[int] = None, log_levels: Optional[Dict[str, str]] = None):
        """
        Crée et affiche une nouvelle barre de progression visuelle.

        Args:
            id: Identifiant unique de la barre
            total: Nombre total d'étapes
            description: Description générale (utilisée comme pre_text par défaut)
            pre_text: Texte à afficher avant la barre
            post_text: Texte à afficher après la barre
            color: Couleur de la barre ("blue", "green", etc.)
            filled_char: Caractère pour les parties remplies
            empty_char: Caractère pour les parties vides
            bar_width: Largeur de la barre en caractères
        """
        if not self.use_visual_bars:
            return # Ne rien faire si désactivé

        if id in self.bars:
            internal_logger.warning(f"Recréation barre visuelle existante: {id}")

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
        internal_logger.debug(f"Barre visuelle '{id}' créée: {total} étapes, pre='{final_pre_text}'")
        # Afficher la barre initiale à 0%
        self._emit_bar(id, 0)

    def update_bar(self, id: str, current: int, total: Optional[int] = None,
                   pre_text: Optional[str] = None, post_text: Optional[str] = None,
color: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None):
        """
        Met à jour une barre visuelle existante avec throttling.

        Args:
            id: Identifiant de la barre
            current: Étape actuelle
            total: Nombre total d'étapes (optionnel)
            pre_text: Nouveau texte avant la barre (optionnel)
            post_text: Nouveau texte après la barre (optionnel)
            color: Nouvelle couleur (optionnel)
        """
        if not self.use_visual_bars or id not in self.bars:
            # Ignorer si barres désactivées ou ID inconnu
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
pre_text: Optional[str] = None, post_text: Optional[str] = None, log_levels: Optional[Dict[str, str]] = None) -> int:
        """
        Avance ou définit l'étape d'une barre visuelle avec throttling.

        Args:
            id: Identifiant de la barre
            current_step: Définit directement l'étape (si None, avance de 1)
            pre_text: Nouveau texte avant la barre (optionnel)
            post_text: Nouveau texte après la barre (optionnel)

        Returns:
            int: Étape actuelle après mise à jour
        """
        if not self.use_visual_bars or id not in self.bars:
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

        # Émettre la mise à jour
        self._emit_bar(id, current)
        return current

    def _emit_bar(self, id: str, current: int):
        """
        Construit et émet le message pour la barre visuelle.

        Args:
            id: Identifiant de la barre
            current: Position actuelle
        """
        if id not in self.bars:
            return

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
                     internal_logger.error(f"Erreur écriture barre texte: {e}", exc_info=True)

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

    def delete_bar(self, id: str, log_levels: Optional[Dict[str, str]] = None):
        """
        Supprime une barre de progression visuelle.

        Args:
            id: Identifiant de la barre à supprimer
        """
        if not self.use_visual_bars:
            return

        if id in self.bars:
            bar_data = self.bars.pop(id) # Retirer du dict immédiatement
            internal_logger.debug(f"Suppression barre visuelle: {id}")

            if self.text_mode:
                # Mode texte : Effacer la ligne et passer à la suivante
                with self._write_lock:
                    try:
                        last_len = bar_data.get("_last_line_len", 0)
                        # Effacer la ligne et aller au début
                        sys.stdout.write(f"\r{' ' * last_len}\r")
                        sys.stdout.flush()
                        # Ajouter un saut de ligne pour la lisibilité
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                    except Exception as e:
                         internal_logger.error(f"Erreur nettoyage barre texte: {e}", exc_info=True)
            else:
                # Mode JSONL : Envoyer un message de statut "stop" via la queue
                stop_message = {
                    "type": "progress-text",
                    "data": {
                        "id": id,
                        "status": "stop",
                        "pre_text": bar_data.get("pre_text", "Tâche"),
                        "percentage": 100
                    }
                }
                self._emit_log("progress-text", stop_message, force_flush=True)
        else:
            internal_logger.warning(f"Tentative delete barre visuelle inexistante: {id}")

    def set_default_bar_style(self, filled_char: str, empty_char: str, log_levels: Optional[Dict[str, str]] = None):
        """
        Définit le style par défaut pour les nouvelles barres visuelles.

        Args:
            filled_char: Caractère pour les parties remplies
            empty_char: Caractère pour les parties vides
        """
        self.default_filled_char = filled_char
        self.default_empty_char = empty_char

    def set_default_bar_width(self, width: int, log_levels: Optional[Dict[str, str]] = None):
        """
        Définit la largeur par défaut pour les nouvelles barres visuelles.

        Args:
            width: Largeur en caractères (minimum 5)
        """
        self.bar_width = max(5, width)

    def flush(self, log_levels: Optional[Dict[str, str]] = None):
        """
        Force le traitement immédiat des messages en attente.

        Cette méthode doit être appelée avant la fin du programme
        pour s'assurer que tous les messages sont traités.
        """
        if self.debugger_mode:
            internal_logger.debug("Flush ignoré en mode débogueur (déjà synchrone)")
            return

        try:
            all_messages = []
            # Vider la file d'attente dans une liste temporaire
            while not self._message_queue.empty():
                try:
                    all_messages.append(self._message_queue.get_nowait())
                    self._message_queue.task_done()
                except queue.Empty:
                    break

            if all_messages:
                internal_logger.debug(f"Flush manuel de {len(all_messages)} messages")
                # Trier par ID chronologique
                all_messages.sort(key=lambda x: x[4])
                self._process_message_batch(all_messages)
            else:
                 # Forcer un flush stdout même si la queue est vide (utile après barre texte)
                 with self._write_lock:
                      try:
                           sys.stdout.flush()
                      except Exception as e:
                           internal_logger.debug(f"Erreur flush stdout vide: {e}")

        except Exception as e:
            internal_logger.error(f"Erreur lors du flush: {e}", exc_info=True)

    def shutdown(self, log_levels: Optional[Dict[str, str]] = None):
        """
        Arrête proprement le thread de traitement des messages.

        Cette méthode doit être appelée avant la fin du programme
        pour s'assurer que le thread est correctement arrêté.
        """
        if self.debugger_mode:
            internal_logger.debug("Shutdown ignoré (mode débogueur)")
            return

        if not self._running:
            internal_logger.debug("Shutdown ignoré (déjà arrêté)")
            return

        internal_logger.debug("Arrêt du logger en cours...")
        self._running = False

        # Donner un peu de temps au thread pour traiter les derniers messages
        if self._message_thread and self._message_thread.is_alive():
             try:
                  # Attendre que la queue soit vide avec timeout de sécurité
                  # pour éviter de bloquer à la sortie
                  wait_start = time.monotonic()
                  while (not self._message_queue.empty() and
                         self._message_thread.is_alive() and
                         time.monotonic() - wait_start < 0.5):
                      time.sleep(0.05)
             except Exception as e:
                  internal_logger.warning(f"Erreur durant la vidange de queue: {e}")

        # Flush final explicite (au cas où join n'aurait pas tout traité)
        self.flush()

        # Attendre la fin du thread (avec timeout court)
        if self._message_thread and self._message_thread.is_alive():
            self._message_thread.join(timeout=0.2)
            if self._message_thread.is_alive():
                 internal_logger.warning("Thread de traitement des messages n'a pas pu être arrêté proprement.")
            else:
                 internal_logger.debug("Thread de traitement des messages arrêté proprement.")

        internal_logger.debug("Arrêt du logger terminé.")

    def __del__(self):
        """Nettoyage lors de la destruction de l'objet."""
        try:
            # S'assurer que le logger est arrêté pour éviter les fuites de thread
            if hasattr(self, '_running') and self._running:
                self.shutdown()
        except Exception:
            # Ignorer les erreurs dans le destructeur
            pass