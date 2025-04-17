"""
Utilitaires de journalisation pour le module d'exécution.
Version optimisée pour améliorer la réactivité de l'interface et le traitement des messages.
"""

import time
import threading
import json
import asyncio
from datetime import datetime
import traceback
from typing import Optional, Dict, Any, List, Deque, Union # Ajout Union
from collections import deque

# Imports Textual prudents (essayer/échouer pour compatibilité si Textual n'est pas là?)
try:
    from textual.widgets import Static
    from textual.containers import ScrollableContainer
    # Importer ProgressBar si votre PluginContainer l'utilise directement
    # from textual.widgets import ProgressBar
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    # Définir des classes factices si Textual n'est pas disponible
    class Static: pass
    class ScrollableContainer: pass
    # class ProgressBar: pass

# Imports internes (adapter les chemins si nécessaire)
try:
    from ..utils.logging import get_logger
    from ..utils.messaging import Message, MessageType, MessageFormatter
except ImportError:
    # Fallback si exécuté hors contexte
    import logging
    get_logger = logging.getLogger
    # Définir des classes Message factices
    class MessageType:
        INFO, WARNING, ERROR, DEBUG, SUCCESS, PROGRESS, PROGRESS_TEXT, UNKNOWN, START, END = range(10)
    class Message:
        def __init__(self, type=MessageType.INFO, content="", source=None, instance_id=None, target_ip=None, **kwargs):
            self.type = type; self.content = content; self.source = source;
            self.instance_id = instance_id; self.target_ip = target_ip
            # Ajouter d'autres attributs potentiels pour éviter les erreurs
            for k, v in kwargs.items(): setattr(self, k, v)
    class MessageFormatter:
        @staticmethod
        def format_for_rich_textual(msg): return f"[{msg.type}] {msg.content}"
        @staticmethod
        def format_for_log_file(msg): return f"{msg.content}"


logger = get_logger('executor_logger')


class LoggerUtils:
    """Classe utilitaire optimisée pour la gestion des logs dans l'interface Textual."""

    # Files d'attente et caches
    _pending_messages: Deque[Message] = deque()
    _priority_queue: Deque[Message] = deque()
    _message_cache = deque(maxlen=200) # Pour déduplication de logs
    _seen_messages = {} # Pour déduplication de logs
    _seen_messages_maxlen = 50

    # Throttling et rafraîchissement
    _logs_timer_running = False
    _last_update_time = time.time()
    _refresh_interval = 0.05 # Augmenté légèrement pour éviter trop de refresh UI
    _message_count = 0
    _refresh_scheduled = False

    # Traitement par lots
    _batch_size = 10 # Augmenté pour traiter plus de messages par flush
    _batch_time = 0.1 # Temps max entre flushes

    @staticmethod
    async def _periodic_logs_display(app):
        """Affiche périodiquement les messages en attente."""
        if not TEXTUAL_AVAILABLE: return # Ne rien faire si Textual n'est pas là
        try:
            LoggerUtils._logs_timer_running = True
            last_flush_time = time.time()

            while LoggerUtils._logs_timer_running:
                current_time = time.time()
                queue_size = len(LoggerUtils._pending_messages) + len(LoggerUtils._priority_queue)
                should_flush = queue_size >= LoggerUtils._batch_size
                time_to_flush = (current_time - last_flush_time) >= LoggerUtils._batch_time

                if queue_size > 0 and (should_flush or time_to_flush):
                    await LoggerUtils.flush_pending_messages(app)
                    last_flush_time = current_time

                # Attente courte pour céder le contrôle
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.error(f"Erreur dans le timer d'affichage des logs: {e}", exc_info=True)
        finally:
            LoggerUtils._logs_timer_running = False

    @staticmethod
    async def start_logs_timer(app):
        """Démarre le timer d'affichage."""
        if not LoggerUtils._logs_timer_running and TEXTUAL_AVAILABLE:
            asyncio.create_task(LoggerUtils._periodic_logs_display(app))
            logger.debug("Timer d'affichage des logs démarré")

    @staticmethod
    async def stop_logs_timer():
        """Arrête le timer d'affichage."""
        LoggerUtils._logs_timer_running = False
        logger.debug("Timer d'affichage des logs arrêté")

    @staticmethod
    def _is_duplicate_message(message_obj: Message) -> bool:
        """Vérifie si un message est un doublon (pour logs standard)."""
        # Ne pas dédupliquer les erreurs, fins, ou progressions
        if message_obj.type in [MessageType.PROGRESS, MessageType.PROGRESS_TEXT, MessageType.ERROR, MessageType.END]:
            return False
        if not isinstance(message_obj.content, str): # Ne dédupliquer que les str
             return False

        # Clé basée sur type, contenu, source, instance, target
        message_key = (message_obj.type, message_obj.content, message_obj.source, message_obj.instance_id, message_obj.target_ip)

        now = time.monotonic()
        last_time, count = LoggerUtils._seen_messages.get(message_key, (0.0, 0))

        # Règle : ignorer si vu > 2 fois dans la dernière seconde
        if now - last_time < 1.0 and count >= 3:
            LoggerUtils._seen_messages[message_key] = (now, count + 1)
            # Logguer un résumé occasionnel
            if count % 20 == 0:
                summary_msg = f"Message répété {count+1} fois: {message_obj.content}"
                # Créer un message warning (difficile d'appeler add_log d'ici)
                logger.warning(f"[DEDUP] {summary_msg}")
            return True # C'est un doublon à ignorer

        # Mettre à jour le cache
        LoggerUtils._seen_messages[message_key] = (now, count + 1)
        if len(LoggerUtils._seen_messages) > LoggerUtils._seen_messages_maxlen:
            try:
                oldest_key = min(LoggerUtils._seen_messages, key=lambda k: LoggerUtils._seen_messages[k][0])
                del LoggerUtils._seen_messages[oldest_key]
            except ValueError: pass # Ignorer si vide

        return False # Pas un doublon (ou première occurrence)

    @staticmethod
    async def _find_plugin_widget(app, message_obj: Message) -> Optional[Any]:
        """Trouve le widget PluginContainer."""
        if not TEXTUAL_AVAILABLE: return None
        # Vérifier les prérequis
        if not all(hasattr(message_obj, attr) for attr in ['source', 'instance_id']) or \
           not hasattr(app, 'plugins') or message_obj.source is None or message_obj.instance_id is None:
            logger.debug(f"Données widget manquantes: source={getattr(message_obj, 'source', 'N/A')}, instance={getattr(message_obj, 'instance_id', 'N/A')}")
            return None

        target_plugin_id_part = f"{message_obj.source}_{message_obj.instance_id}"
        logger.debug(f"Recherche widget contenant: {target_plugin_id_part}")

        found_widget = None
        # Chercher par ID dans le dictionnaire des plugins de l'app
        for plugin_id, widget in app.plugins.items():
            if target_plugin_id_part in plugin_id:
                 # Duck typing pour vérifier si c'est le bon type de widget
                 if hasattr(widget, 'update_progress') and hasattr(widget, 'plugin_name') and hasattr(widget, 'instance_id'):
                    logger.debug(f"Widget trouvé par ID: {plugin_id}")
                    found_widget = widget
                    break

        # Fallback si non trouvé par ID (moins fiable)
        if not found_widget:
            logger.debug("Widget non trouvé par ID, recherche par classe/attributs...")
            try:
                for widget in app.query("PluginContainer"): # Attention: peut être coûteux
                    if hasattr(widget, 'plugin_name') and widget.plugin_name == message_obj.source and \
                       hasattr(widget, 'instance_id') and str(widget.instance_id) == str(message_obj.instance_id):
                       if hasattr(widget, 'update_progress'):
                            logger.debug(f"Widget trouvé par classe/attributs: {getattr(widget, 'id', 'NO ID')}")
                            found_widget = widget
                            break
            except Exception as query_err: logger.warning(f"Erreur recherche PluginContainer: {query_err}")

        if not found_widget: logger.warning(f"Widget plugin non trouvé pour {target_plugin_id_part}")
        return found_widget

    @staticmethod
    async def _update_plugin_widget_display(app, message_obj: Message):
        """Met à jour la barre NUMÉRIQUE et le TEXTE de statut du widget plugin."""
        if not TEXTUAL_AVAILABLE: return
        plugin_widget = await LoggerUtils._find_plugin_widget(app, message_obj)
        if not plugin_widget: return

        try:
            percent = 0.0
            status_text = ""

            if message_obj.type == MessageType.PROGRESS:
                if hasattr(message_obj, 'progress'): percent = message_obj.progress * 100
                if hasattr(message_obj, 'total_steps') and message_obj.total_steps > 1 and hasattr(message_obj, 'step'):
                    status_text = f"Étape {message_obj.step}/{message_obj.total_steps}"
                elif percent > 0: status_text = f"{int(percent)}%"
                # logger.debug(f"MAJ Widget NUMÉRIQUE {getattr(plugin_widget,'id','?')}: Pct={percent:.1f}%, Text='{status_text}'")

            elif message_obj.type == MessageType.PROGRESS_TEXT:
                if hasattr(message_obj, 'data') and isinstance(message_obj.data, dict):
                    data = message_obj.data
                    status = data.get("status", "running")
                    if status == "stop":
                        percent = 100.0
                        status_text = f"{data.get('pre_text', 'Tâche')} terminée." # Message de fin clair
                        # logger.debug(f"MAJ Widget TEXTE (stop) {getattr(plugin_widget,'id','?')}: Pct={percent:.1f}%, Text='{status_text}'")
                    else: # status == "running"
                        percent = float(data.get("percentage", 0))
                        pre_text = data.get("pre_text", "")
                        post_text = data.get("post_text", "")
                        # Combiner pre/post text
                        status_text = f"{pre_text}: {post_text}".strip(': ')
                        if not status_text: status_text = f"{int(percent)}%" # Fallback
                        # logger.debug(f"MAJ Widget TEXTE (run) {getattr(plugin_widget,'id','?')}: Pct={percent:.1f}%, Text='{status_text}'")

            # Appeler la méthode de mise à jour du widget (elle doit exister!)
            if hasattr(plugin_widget, 'update_progress'):
                percent = max(0.0, min(100.0, percent)) # Clamp 0-100
                plugin_widget.update_progress(percent, status_text)
            else: logger.warning(f"Widget {getattr(plugin_widget,'id','?')} n'a pas de méthode 'update_progress'")

        except Exception as e:
            widget_id_str = getattr(plugin_widget, 'id', 'ID inconnu')
            logger.error(f"Erreur MAJ widget plugin {widget_id_str}: {e}", exc_info=True)

    @staticmethod
    async def process_output_line(app, line: str, plugin_widget=None, target_ip: Optional[str] = None, is_priority: bool = False):
        """Traite une ligne de sortie JSONL et met à jour l'UI."""
        if not line or not TEXTUAL_AVAILABLE: return
        # plugin_widget n'est plus utilisé, on le trouve via _find_plugin_widget

        # Vérifier l'écran actuel pour la mise en file d'attente
        try:
            screen_name = app.screen.__class__.__name__ if hasattr(app, 'screen') else "Unknown"
            needs_queue = "ExecutionScreen" not in screen_name
        except Exception: # Erreur si app n'est pas prêt
             needs_queue = True

        message_obj: Optional[Message] = None
        try:
            log_entry = json.loads(line)
            log_level = log_entry.get("level", "info").lower()
            message_content = log_entry.get("message", "")
            plugin_name = log_entry.get("plugin_name")
            instance_id = log_entry.get("instance_id")

            # Créer l'objet Message de base
            message_obj = Message(
                type=MessageType.UNKNOWN, content=str(message_content),
                source=plugin_name, instance_id=instance_id, target_ip=target_ip
            )

            # Traiter les types de progression
            if log_level == "progress":
                message_obj.type = MessageType.PROGRESS
                data = message_content.get("data", {}) if isinstance(message_content, dict) else {}
                message_obj.progress = float(data.get("percentage", 0.0))
                message_obj.step = data.get("current_step", 0)
                message_obj.total_steps = data.get("total_steps", 1)
                if not needs_queue: await LoggerUtils._update_plugin_widget_display(app, message_obj)
                return # Ne pas afficher comme log texte

            elif log_level == "progress-text":
                message_obj.type = MessageType.PROGRESS_TEXT
                data = message_content.get("data", {}) if isinstance(message_content, dict) else {}
                message_obj.data = data
                if not needs_queue: await LoggerUtils._update_plugin_widget_display(app, message_obj)
                return # Ne pas afficher comme log texte

            # Traiter les logs standards
            else:
                message_obj.type = {
                    "info": MessageType.INFO, "warning": MessageType.WARNING, "error": MessageType.ERROR,
                    "success": MessageType.SUCCESS, "debug": MessageType.DEBUG, "start": MessageType.START,
                    "end": MessageType.END
                }.get(log_level, MessageType.INFO)
                # Adapter contenu
                if message_obj.type == MessageType.END and not str(message_obj.content).startswith("✓"):
                    message_obj.content = f"✓ {message_obj.content}"
                if isinstance(message_content, dict): message_obj.content = str(message_content)

                # Mettre en queue ou afficher
                if needs_queue:
                    queue_target = LoggerUtils._priority_queue if is_priority else LoggerUtils._pending_messages
                    queue_target.append(message_obj)
                else:
                    await LoggerUtils.display_message(app, message_obj, is_priority)

        except json.JSONDecodeError:
            # Ligne non-JSON: traiter comme texte brut
            message_obj = Message(type=MessageType.INFO, content=line, target_ip=target_ip)
            line_lower = line.lower()
            if any(term in line_lower for term in ['error', 'erreur', 'failed', 'échec', 'traceback']): message_obj.type = MessageType.ERROR
            elif any(term in line_lower for term in ['success', 'succès', 'terminé']): message_obj.type = MessageType.SUCCESS
            elif any(term in line_lower for term in ['warning', 'attention', 'avertissement']): message_obj.type = MessageType.WARNING

            if needs_queue:
                queue_target = LoggerUtils._priority_queue if is_priority else LoggerUtils._pending_messages
                queue_target.append(message_obj)
            else:
                await LoggerUtils.display_message(app, message_obj, is_priority)

        except Exception as e:
            logger.error(f"Erreur process_output_line: {e}", exc_info=True)
            # Essayer de logguer l'erreur elle-même
            try:
                error_message = Message(type=MessageType.ERROR, content=f"Erreur traitement log: {str(e)}", target_ip=target_ip)
                if needs_queue: LoggerUtils._pending_messages.append(error_message)
                else: await LoggerUtils.display_message(app, error_message)
            except: pass

    @staticmethod
    async def display_message(app, message_obj: Message, is_priority: bool = False):
        """Affiche un message formaté dans #logs-text."""
        if not TEXTUAL_AVAILABLE: return
        try:
            # Ignorer les types de progression qui sont gérés ailleurs
            if message_obj.type in [MessageType.PROGRESS, MessageType.PROGRESS_TEXT]:
                return

            # Ne pas afficher DEBUG sauf si mode debug activé (logique applicative)
            # if message_obj.type == MessageType.DEBUG and not getattr(app, 'debug_mode', False): return

            # Vérifier les doublons (logs standard uniquement)
            if LoggerUtils._is_duplicate_message(message_obj):
                return

            # Formater pour Rich/Textual
            formatted_message = MessageFormatter.format_for_rich_textual(message_obj)
            if not formatted_message: return

            # Mettre à jour le widget #logs-text
            try:
                logs = app.query_one("#logs-text", Static)
                current_text = logs.renderable if logs.renderable else "" # Assurer str
                # Éviter les doubles sauts de ligne
                if current_text and not current_text.endswith("\n"): current_text += "\n"
                logs.update(current_text + formatted_message) # Le formateur ajoute \n? Non, ajoutons ici.

                # Gérer le défilement et le rafraîchissement
                logs_container = app.query_one("#logs-container", ScrollableContainer)
                logs_container.scroll_end(animate=False)

                # Planifier rafraîchissement UI (limité)
                now = time.time()
                if (now - LoggerUtils._last_update_time) >= LoggerUtils._refresh_interval:
                    if not LoggerUtils._refresh_scheduled:
                        LoggerUtils._refresh_scheduled = True
                        LoggerUtils._schedule_refresh(app)
                    LoggerUtils._last_update_time = now
            except Exception as e_ui:
                 logger.debug(f"Impossible MAJ widget logs: {e_ui}. Message mis en attente.")
                 # Mettre en attente si l'UI n'est pas prête
                 queue_target = LoggerUtils._priority_queue if is_priority else LoggerUtils._pending_messages
                 queue_target.append(message_obj)


        except Exception as e:
            logger.error(f"Erreur display_message: {e}", exc_info=True)

    @staticmethod
    async def flush_pending_messages(app):
        """Traite les messages Message en attente."""
        if not TEXTUAL_AVAILABLE or (not LoggerUtils._pending_messages and not LoggerUtils._priority_queue):
            return

        try:
            # S'assurer que le widget de logs existe
            logs = app.query_one("#logs-text", Static)
            logs_container = app.query_one("#logs-container", ScrollableContainer)
        except Exception:
            logger.debug("Widget logs non trouvé pendant flush.")
            return

        messages_to_process: List[Message] = []
        while LoggerUtils._priority_queue: messages_to_process.append(LoggerUtils._priority_queue.popleft())
        while LoggerUtils._pending_messages: messages_to_process.append(LoggerUtils._pending_messages.popleft())

        if messages_to_process:
            logger.debug(f"Flush de {len(messages_to_process)} messages en attente...")
            # Construire le texte formaté pour tous les messages non-progression
            log_lines_to_add = []
            for msg_obj in messages_to_process:
                 if msg_obj.type not in [MessageType.PROGRESS, MessageType.PROGRESS_TEXT]:
                      # Vérifier doublon avant formatage
                      if not LoggerUtils._is_duplicate_message(msg_obj):
                          formatted = MessageFormatter.format_for_rich_textual(msg_obj)
                          if formatted: log_lines_to_add.append(formatted)
                 elif not app.is_screen_installed("execution_screen"): # Si pas sur l'écran, MAJ widget ne fonctionnera pas
                      pass # Ignorer la mise à jour de progression si écran non actif
                 else: # Essayer de mettre à jour le widget de progression même pendant flush
                      # (peut être redondant si process_output_line l'a déjà fait)
                      await LoggerUtils._update_plugin_widget_display(app, msg_obj)


            # Mettre à jour le widget logs si des lignes texte existent
            if log_lines_to_add:
                current_text = logs.renderable if logs.renderable else ""
                if current_text and not current_text.endswith("\n"): current_text += "\n"
                # Ajouter toutes les nouvelles lignes
                logs.update(current_text + "\n".join(log_lines_to_add)) # Assurer une seule MAJ du widget
                logs_container.scroll_end(animate=False)

            # Planifier un rafraîchissement UI
            if not LoggerUtils._refresh_scheduled:
                LoggerUtils._refresh_scheduled = True
                LoggerUtils._schedule_refresh(app)

    @staticmethod
    def _schedule_refresh(app):
        """Planifie un rafraîchissement différé."""
        if hasattr(app, 'call_later'):
            # Utiliser call_later pour différer et éviter les appels trop rapprochés
            app.call_later(lambda: LoggerUtils._do_refresh(app))
        else: # Fallback si call_later n'existe pas
            LoggerUtils._do_refresh(app)

    @staticmethod
    def _do_refresh(app):
        """Effectue le rafraîchissement."""
        try:
            if hasattr(app, 'is_mounted') and app.is_mounted: # Vérifier si monté
                if hasattr(app, 'refresh'): app.refresh()
        except Exception as e: logger.debug(f"Erreur refresh: {e}")
        finally: LoggerUtils._refresh_scheduled = False

    @staticmethod
    async def add_log(app, message: str, level: str = "info", target_ip: Optional[str] = None):
        """Ajoute un message au log via LoggerUtils."""
        try:
            message_type = {
                "info": MessageType.INFO, "warning": MessageType.WARNING, "error": MessageType.ERROR,
                "success": MessageType.SUCCESS, "debug": MessageType.DEBUG, "start": MessageType.START,
                "end": MessageType.END
            }.get(level.lower(), MessageType.INFO)

            if message_type == MessageType.END and not message.startswith("✓"): message = f"✓ {message}"

            message_obj = Message(type=message_type, content=message, target_ip=target_ip)
            is_priority = message_type in [MessageType.ERROR, MessageType.END]

            # Vérifier écran et mettre en queue ou afficher
            screen_name = app.screen.__class__.__name__ if hasattr(app, 'screen') else "Unknown"
            if "ExecutionScreen" not in screen_name:
                 queue_target = LoggerUtils._priority_queue if is_priority else LoggerUtils._pending_messages
                 queue_target.append(message_obj)
            else:
                 await LoggerUtils.display_message(app, message_obj, is_priority)

        except Exception as e:
            logger.error(f"Erreur add_log: {e}", exc_info=True)

    # --- Autres méthodes ---
    @staticmethod
    async def clear_logs(app):
        """Effacement des logs et réinitialisation."""
        try:
            LoggerUtils._pending_messages.clear(); LoggerUtils._priority_queue.clear()
            LoggerUtils._processed_lines.clear(); LoggerUtils._seen_messages.clear()
            LoggerUtils._message_count = 0
            if TEXTUAL_AVAILABLE:
                try: app.query_one("#logs-text", Static).update("")
                except Exception: pass # Ignorer si widget non trouvé
        except Exception as e: logger.error(f"Erreur clear_logs: {e}")

    @staticmethod
    def toggle_logs(app) -> None:
        """Afficher/Masquer les logs."""
        if not TEXTUAL_AVAILABLE: return
        try:
            logs_container = app.query_one("#logs-container")
            logs_container.toggle_class("hidden")
            if hasattr(app, 'show_logs'): app.show_logs = not logs_container.has_class("hidden")
            if not LoggerUtils._refresh_scheduled:
                 LoggerUtils._refresh_scheduled = True
                 LoggerUtils._schedule_refresh(app)
        except Exception as e: logger.error(f"Erreur toggle_logs: {e}")

    @staticmethod
    async def ensure_logs_widget_exists(app):
        """S'assure que le widget de logs existe."""
        if not TEXTUAL_AVAILABLE: return False
        try:
            app.query_one("#logs-text", Static); return True
        except Exception: pass # N'existe pas encore
        try: # Essayer de le créer
            logs_container = app.query_one("#logs-container", ScrollableContainer)
            logs_text = Static(id="logs-text", classes="logs")
            await logs_container.mount(logs_text) # Utiliser await pour mount
            logs_container.remove_class("hidden")
            if hasattr(app, 'show_logs'): app.show_logs = True
            if not LoggerUtils._refresh_scheduled:
                 LoggerUtils._refresh_scheduled = True
                 LoggerUtils._schedule_refresh(app)
            return True
        except Exception as e: logger.debug(f"Impossible créer widget logs: {e}")
        return False