"""
Utilitaires de journalisation pour le module d'exécution.
Traite les messages standardisés pour l'affichage dans l'interface utilisateur.
"""

import time
import threading
import logging
import re
from rich.text import Text
from textual.widgets import Static
from textual.containers import ScrollableContainer

from ..utils.logging import get_logger
from ..utils.messaging import Message, MessageType, parse_message, MessageFormatter

logger = get_logger('executor_logger')

class LoggerUtils:
    """Classe utilitaire pour la gestion des logs dans l'interface et le fichier de log"""
    
    @staticmethod
    def escape_markup(text):
        """Échapper les caractères spéciaux qui pourraient être interprétés comme du markup"""
        if text is None:
            return ""
        
        # Convertir en chaîne si ce n'est pas déjà le cas
        if not isinstance(text, str):
            text = str(text)
            
        # Échapper les caractères spéciaux Textual/Rich
        escaped = text.replace("[", "\\[").replace("]", "\\]")
        return escaped
    
    @staticmethod
    async def display_message(app, message_obj: Message):
        """
        Affiche un message dans la zone de logs.
        
        Args:
            app: Application ou widget contenant les éléments d'UI
            message_obj: Objet Message à afficher
        """
        try:
            # Vérifier si nous sommes dans le thread principal
            if hasattr(app, '_thread_id') and app._thread_id != threading.get_ident():
                # Dans un thread différent, utiliser call_from_thread
                if hasattr(app, 'call_from_thread'):
                    await app.call_from_thread(LoggerUtils.display_message, app, message_obj)
                    return
                else:
                    # Fallback: log uniquement dans le fichier
                    logger.info(f"Thread différent sans call_from_thread: {message_obj.content}")
                    return
            
            # Ignorer les messages PROGRESS pour l'affichage de logs
            if message_obj.type == MessageType.PROGRESS:
                return
                
            # Échapper les caractères spéciaux pour le markup
            safe_content = LoggerUtils.escape_markup(message_obj.content)
            
            # Couleurs explicites pour les différents types de messages
            # Ces couleurs sont supportées par Rich et Textual
            colors = {
                MessageType.INFO: "cyan",
                MessageType.WARNING: "yellow",
                MessageType.ERROR: "red",
                MessageType.SUCCESS: "green",
                MessageType.DEBUG: "gray70",
                MessageType.UNKNOWN: "white"
            }
            color = colors.get(message_obj.type, "white")
            
            # Générer le message formaté avec des balises de couleur explicites
            timestamp = time.strftime("%H:%M:%S")
            level_str = f"{message_obj.type.name:7}"
            
            # Format lisible et coloré
            formatted_message = f"[cyan]{timestamp}[/cyan]  [{color}]{level_str}[/{color}]  [{color}]{safe_content}[/{color}]"
            
            # Mise à jour des logs dans l'interface
            logs = app.query_one("#logs-text", Static)
            if logs:
                current_text = logs.renderable or ""
                if current_text:
                    current_text += "\n"
                logs.update(current_text + formatted_message)
                
                # Forcer le défilement vers le bas
                logs_container = app.query_one("#logs-container", ScrollableContainer)
                if logs_container:
                    logs_container.scroll_end(animate=False)
            
            # S'assurer que logs-container est visible
            logs_container = app.query_one("#logs-container", ScrollableContainer)
            if logs_container and "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                if hasattr(app, 'show_logs'):
                    app.show_logs = True
            
            # Journalisation dans le fichier
            log_methods = {
                MessageType.INFO: logger.info,
                MessageType.WARNING: logger.warning,
                MessageType.ERROR: logger.error,
                MessageType.DEBUG: logger.debug,
                MessageType.SUCCESS: logger.info,
                MessageType.UNKNOWN: logger.info
            }
            log_method = log_methods.get(message_obj.type, logger.info)
            log_method(message_obj.content)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage d'un message: {str(e)}")
            try:
                # Tenter une approche plus simple en cas d'erreur
                logs = app.query_one("#logs-text")
                if logs:
                    error_text = f"\nERREUR DE LOG: {message_obj.content}"
                    logs.update(logs.renderable + error_text)
            except:
                pass
    
    @staticmethod
    async def add_log(app, message, level='info'):
        """
        Méthode de compatibilité avec l'ancien système.
        Convertit un message au format texte en Message puis l'affiche.
        
        Args:
            app: Application contenant les éléments d'UI
            message: Message à afficher
            level: Niveau de log (info, warning, error, success, debug)
        """
        try:
            # Convertir en Message
            if isinstance(message, Message):
                message_obj = message
            else:
                # Map des anciens niveaux aux nouveaux types
                level_map = {
                    'info': MessageType.INFO,
                    'warning': MessageType.WARNING,
                    'error': MessageType.ERROR,
                    'success': MessageType.SUCCESS,
                    'debug': MessageType.DEBUG
                }
                message_obj = Message(
                    type=level_map.get(level.lower(), MessageType.INFO),
                    content=message
                )
            
            # Afficher le message
            await LoggerUtils.display_message(app, message_obj)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un log: {str(e)}")
    
    @staticmethod
    async def process_output_line(app, line, plugin_widget=None, executed=0, total_plugins=1):
        """
        Traite une ligne de sortie d'un plugin et la dirige vers le gestionnaire approprié.
        
        Args:
            app: Application contenant les éléments d'UI
            line: Ligne à traiter
            plugin_widget: Widget du plugin qui a émis la ligne
            executed: Nombre de plugins déjà exécutés
            total_plugins: Nombre total de plugins à exécuter
            
        Returns:
            bool: True si la ligne a été traitée, False sinon
        """
        try:
            if not line or not isinstance(line, str):
                return False
                
            line = line.strip()
            if not line:
                return False
            
            # Parser le message
            message_obj = parse_message(line)
            
            # Traiter selon le type
            if message_obj.type == MessageType.PROGRESS:
                if plugin_widget:
                    # Mettre à jour la barre de progression
                    progress = message_obj.progress
                    step_text = f"Étape {message_obj.step}/{message_obj.total_steps}" if message_obj.step else f"{int(progress*100)}%"
                    
                    plugin_widget.update_progress(progress, step_text)
                    
                    # Mettre à jour la progression globale
                    global_progress = (executed + progress) / total_plugins
                    if hasattr(app, 'update_global_progress'):
                        app.update_global_progress(global_progress)
                return True
            else:
                # Pour les autres types, afficher dans les logs
                await LoggerUtils.display_message(app, message_obj)
                return True
                
        except Exception as e:
            logger.error(f"Erreur lors du traitement d'une ligne: {str(e)}")
            return False
    
    @staticmethod
    async def clear_logs(app):
        """Effacement des logs"""
        try:
            logs_widget = app.query_one("#logs-text")
            if logs_widget:
                logs_widget.update("")
        except Exception as e:
            logger.error(f"Erreur lors de l'effacement des logs: {str(e)}")
    
    @staticmethod
    def toggle_logs(app) -> None:
        """Afficher/Masquer les logs"""
        try:
            logs_container = app.query_one("#logs-container")
            if logs_container:
                if "hidden" in logs_container.classes:
                    logs_container.remove_class("hidden")
                    if hasattr(app, 'show_logs'):
                        app.show_logs = True
                else:
                    logs_container.add_class("hidden")
                    if hasattr(app, 'show_logs'):
                        app.show_logs = False
        except Exception as e:
            logger.error(f"Erreur lors du toggle des logs: {str(e)}")