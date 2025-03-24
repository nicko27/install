"""
Utilitaires de journalisation pour le module d'exécution.
Traite les messages standardisés pour l'affichage dans l'interface utilisateur.
"""

import time
import threading
import logging
import re
from typing import Optional, Union
from collections import deque
from rich.text import Text
from textual.widgets import Static
from textual.containers import ScrollableContainer

from ..utils.logging import get_logger
from ..utils.messaging import (Message, MessageType, parse_message, MessageFormatter, escape_markup,
                            create_info, create_warning, create_error, create_success, create_debug)

logger = get_logger('executor_logger')

class LoggerUtils:
    """Classe utilitaire pour la gestion des logs dans l'interface et le fichier de log"""
    
    # Cache pour éviter les duplications
    _message_cache = deque(maxlen=100)
    _processed_lines = set()

    @staticmethod
    def _is_duplicate_message(message_obj: Message) -> bool:
        """
        Vérifie si un message est un doublon.
        
        Args:
            message_obj: Message à vérifier
        
        Returns:
            bool: True si le message est un doublon, False sinon
        """
        # Créer une clé unique basée sur le type et le contenu
        message_key = (message_obj.type, message_obj.content)
        
        # Si le message a déjà été traité récemment, le considérer comme un doublon
        if message_key in LoggerUtils._processed_lines:
            return True
        
        # Ajouter le message aux lignes traitées
        LoggerUtils._processed_lines.add(message_key)
        
        return False

    @staticmethod
    async def _update_progress_widget(app, message_obj: Message, plugin_widget=None, step_text=None):
        """
        Met à jour la progression d'un widget de plugin.
        
        Args:
            app: Application contenant les éléments d'UI
            message_obj: Message de progression
            plugin_widget: Widget spécifique à mettre à jour (optionnel)
            step_text: Texte à afficher pour l'étape (optionnel)
        
        Returns:
            bool: True si un widget a été mis à jour, False sinon
        """
        # Si pas de progression, rien à faire
        if not hasattr(message_obj, 'progress'):
            return False
            
        progress = message_obj.progress
        
        # Génère le texte d'étape s'il n'est pas fourni
        if step_text is None:
            step_text = (f"Étape {message_obj.step}/{message_obj.total_steps}" 
                         if hasattr(message_obj, 'total_steps') and hasattr(message_obj, 'step') and message_obj.total_steps > 1
                         else f"{int(progress*100)}%")
        
        # Si nous avons un widget spécifique, l'utiliser
        if plugin_widget:
            plugin_widget.update_progress(progress, step_text)
            return True
            
        # Sinon, chercher le widget correspondant dans l'application
        if hasattr(message_obj, 'plugin_name'):
            plugin_widgets = app.query("PluginContainer")
            
            # D'abord essayer avec instance_id si disponible
            if hasattr(message_obj, 'instance_id'):
                match_found = False
                for plugin_id, widget in app.plugins.items() if hasattr(app, 'plugins') else []:
                    # Vérifier si l'identifiant d'instance correspond à plugin_id
                    if message_obj.instance_id in plugin_id:
                        widget.update_progress(progress, step_text)
                        match_found = True
                        logger.debug(f"Widget trouvé par plugin_id contenant instance_id: {message_obj.instance_id}")
                        return True
                            
                # Si aucun widget trouvé par instance_id, essayer par nom de plugin
                if not match_found:
                    for widget in plugin_widgets:
                        if hasattr(widget, 'plugin_name') and widget.plugin_name == message_obj.plugin_name:
                            widget.update_progress(progress, step_text)
                            logger.debug(f"Widget trouvé par plugin_name: {message_obj.plugin_name}")
                            return True
            # Si pas d'instance_id, essayer juste avec le nom du plugin
            else:
                for widget in plugin_widgets:
                    if hasattr(widget, 'plugin_name') and widget.plugin_name == message_obj.plugin_name:
                        widget.update_progress(progress, step_text)
                        logger.debug(f"Widget trouvé par plugin_name: {message_obj.plugin_name}")
                        return True
        
        return False

    @staticmethod
    async def _update_global_progress(app, progress: float, executed: int, total_plugins: int):
        """
        Met à jour la progression globale de l'application.
        
        Args:
            app: Application contenant la barre de progression globale
            progress: Progression du plugin actuel (0.0 à 1.0)
            executed: Nombre de plugins déjà exécutés
            total_plugins: Nombre total de plugins à exécuter
        """
        # Calcul de la progression globale
        global_progress = (executed + progress) / total_plugins
        logger.debug(f"Mise à jour de la progression globale: executed={executed}, progress={progress}, total_plugins={total_plugins}, global_progress={global_progress}")
        
        # Vérifier si app a la méthode update_global_progress
        if hasattr(app, 'update_global_progress'):
            logger.debug(f"Appel de app.update_global_progress({global_progress})")
            try:
                app.update_global_progress(global_progress)
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de la progression globale: {e}")
        else:
            logger.warning(f"app n'a pas de méthode update_global_progress: {type(app)}")

    @staticmethod
    async def display_message(app, message_obj: Message):
        """
        Affiche un message dans la zone de logs.
        Ne traite pas les messages de progression - utilisez process_output_line pour cela.
        
        Args:
            app: Application ou widget contenant les éléments d'UI
            message_obj: Objet Message à afficher
        """
        try:
            # Vérifier les doublons
            if LoggerUtils._is_duplicate_message(message_obj):
                return
            
            # Vérifier si nous sommes dans le thread principal
            if hasattr(app, '_thread_id') and app._thread_id != threading.get_ident():
                if hasattr(app, 'call_from_thread'):
                    await app.call_from_thread(LoggerUtils.display_message, app, message_obj)
                    return
                else:
                    logger.info(f"Thread différent sans call_from_thread: {message_obj.content}")
                    return
            
            # Ignorer les messages de type PROGRESS, ils sont traités par process_output_line
            if message_obj.type == MessageType.PROGRESS:
                logger.debug("Message de type PROGRESS ignoré dans display_message")
                return
                
            # Utiliser le formateur de message du module messaging
            formatted_message = MessageFormatter.format_for_rich_textual(message_obj)
            
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
                MessageType.PROGRESS: logger.debug,  # Utiliser debug pour les messages de progression
                MessageType.UNKNOWN: logger.info
            }
            
            # Utiliser le formateur de message pour fichier de log du module messaging
            content = MessageFormatter.format_for_log_file(message_obj)
                
            log_method = log_methods.get(message_obj.type, logger.info)
            log_method(content)
            
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
    async def add_log(app, message: Union[str, Message], level: str = 'info', target_ip: str = None):
        """
        Méthode de compatibilité avec l'ancien système.
        Convertit un message au format texte en Message puis l'affiche.
        
        Args:
            app: Application contenant les éléments d'UI
            message: Message à afficher (str ou Message)
            level: Niveau de log (info, warning, error, success, debug)
            target_ip: Adresse IP cible pour les plugins SSH (optionnel)
        """
        try:
            # Convertir en Message
            if isinstance(message, Message):
                message_obj = message
            else:
                # Créer le message en fonction du niveau
                if level.lower() == "info":
                    message_obj = create_info(message, target_ip=target_ip)
                elif level.lower() == "warning":
                    message_obj = create_warning(message, target_ip=target_ip)
                elif level.lower() == "error":
                    message_obj = create_error(message, target_ip=target_ip)
                elif level.lower() == "debug":
                    message_obj = create_debug(message, target_ip=target_ip)
                elif level.lower() == "success":
                    message_obj = create_success(message, target_ip=target_ip)
                else:
                    message_obj = create_info(message, target_ip=target_ip)
            
            # Afficher le message
            await LoggerUtils.process_output_line(app, message_obj.to_string())
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un log: {str(e)}")

    @staticmethod
    async def process_output_line(
        app, 
        line: str, 
        plugin_widget=None, 
        executed: int = 0, 
        total_plugins: int = 1,
        target_ip: str = None
    ):
        """
        Traite une ligne de sortie d'un plugin et la dirige vers le gestionnaire approprié.
        Cette méthode est la principale pour le traitement des logs.
        
        Args:
            app: Application contenant les éléments d'UI
            line: Ligne à traiter ou objet Message
            plugin_widget: Widget du plugin qui a émis la ligne
            executed: Nombre de plugins déjà exécutés
            total_plugins: Nombre total de plugins à exécuter
            
        Returns:
            bool: True si la ligne a été traitée, False sinon
        """
        try:
            # Si la ligne est vide, rien à faire
            if not line:
                return False
                
            # Traiter différemment selon le type de ligne
            if isinstance(line, str):
                line = line.strip()
                if not line:
                    return False
                
                logger.debug(f"Traitement de la ligne: {line}")

                # Parser la ligne en Message
                try:
                    logger.debug(f"Parsing du message: {line}")
                    message_obj = parse_message(line)
                    plugin_name = message_obj.plugin_name if hasattr(message_obj, 'plugin_name') else None
                    instance_id = message_obj.instance_id if hasattr(message_obj, 'instance_id') else None
                    
                    # Si une IP cible est fournie, l'ajouter au message
                    if target_ip and not hasattr(message_obj, 'target_ip'):
                        message_obj.target_ip = target_ip
                    
                    logger.debug(f"Message parsé: type={message_obj.type.name}, progress={getattr(message_obj, 'progress', None)}, plugin_name={getattr(message_obj, 'plugin_name', None) if hasattr(message_obj, 'plugin_name') else 'Non défini'}, target_ip={getattr(message_obj, 'target_ip', None)}")
                    
                    # Ajouter l'information sur le plugin pour les messages PROGRESS
                    if message_obj.type == MessageType.PROGRESS and plugin_widget and hasattr(plugin_widget, f"{plugin_name}_{instance_id}"):
                        message_obj.plugin_name = plugin_widget.plugin_name
                        logger.debug(f"Ajout du nom du plugin depuis le widget: {message_obj.plugin_name}")
                except Exception as e:
                    logger.debug(f"Impossible de parser le message: {e}")
                    return False
            elif isinstance(line, Message):
                # La ligne est déjà un Message
                message_obj = line
            else:
                # Type non supporté
                logger.warning(f"Type de ligne non supporté: {type(line)}")
                return False

            # Traitement spécifique en fonction du type de message
            if message_obj.type == MessageType.PROGRESS:
                # Vérifier si le message contient un identifiant d'instance
                plugin_name = message_obj.plugin_name if hasattr(message_obj, 'plugin_name') else None
                instance_id = message_obj.instance_id if hasattr(message_obj, 'instance_id') else None
                
                # Mise à jour de la progression du plugin
                step_text = (f"Étape {message_obj.step}/{message_obj.total_steps}" 
                            if message_obj.total_steps > 1 
                            else f"{int(message_obj.progress*100)}%")
                
                # Mettre à jour le widget de progression
                await LoggerUtils._update_progress_widget(app, message_obj, plugin_widget, step_text)
                
                # Mettre à jour la progression globale
                await LoggerUtils._update_global_progress(app, message_obj.progress, executed, total_plugins)
                
                return True
            
            # Pour les autres types de messages, utiliser display_message
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
                
            # Réinitialiser le cache de messages
            LoggerUtils._processed_lines.clear()
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