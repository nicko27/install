"""
Utilitaires de journalisation pour le module d'exécution.
Traite les messages standardisés pour l'affichage dans l'interface utilisateur.
"""

import time
import threading
import logging
import re
import json
from typing import Optional, Union, Dict
from collections import deque
from rich.text import Text
from textual.widgets import Static
from textual.containers import ScrollableContainer
from datetime import datetime
import traceback

from ..utils.logging import get_logger
from ..utils.messaging import (Message, MessageType, parse_message, MessageFormatter, escape_markup,
                            create_info, create_warning, create_error, create_success, create_debug)

logger = get_logger('executor_logger')

class LoggerUtils:
    """Classe utilitaire pour la gestion des logs dans l'interface et le fichier de log"""
    
    # Cache pour éviter les duplications
    _message_cache = deque(maxlen=100)
    _processed_lines = set()
    
    # Dictionnaire pour suivre les barres de progression textuelles actives
    _active_text_progress_bars = {}

    @staticmethod
    def _is_duplicate_message(message_obj: Message) -> bool:
        """
        Vérifie si un message est un doublon.
        
        Args:
            message_obj: Message à vérifier
        
        Returns:
            bool: True si le message est un doublon, False sinon
        """
        # Pour les messages de progression, ne pas vérifier les doublons
        if message_obj.type == MessageType.PROGRESS or message_obj.type == MessageType.PROGRESS_TEXT:
            return False
            
        # Créer une clé unique basée sur le type et le contenu
        try:
            # Si le contenu est un dict, le convertir en tuple de tuples
            if isinstance(message_obj.content, dict):
                content = tuple(sorted(message_obj.content.items()))
            else:
                content = str(message_obj.content)
                
            message_key = (message_obj.type, content)
            
            # Si le message a déjà été traité récemment, le considérer comme un doublon
            if message_key in LoggerUtils._processed_lines:
                return True
            
            # Ajouter le message aux lignes traitées
            LoggerUtils._processed_lines.add(message_key)
            return False
            
        except Exception as e:
            logger.warning(f"Erreur lors de la vérification des doublons: {e}")
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
    async def _display_text_progress_bar(app, progress_key: str, bar_display: str, status: str = "running", color: str = "blue"):
        """
        Affiche ou met à jour une barre de progression textuelle.
        
        Args:
            app: Application ou widget contenant les éléments d'UI
            progress_key: Clé unique identifiant cette barre de progression
            bar_display: Texte complet de la barre à afficher
            status: État de la barre ("running" ou "stop")
            color: Couleur de la barre
        """
        try:
            # Vérifier si app est valide
            if app is None:
                logger.error("Erreur: app est None dans _display_text_progress_bar")
                return
                
            # Obtenir le widget de logs
            logs = app.query_one("#logs-text", Static)
            if not logs:
                logger.error("Widget de logs non trouvé dans _display_text_progress_bar")
                return
            
            # Échapper les caractères spéciaux pour éviter les problèmes de markup
            safe_bar_display = bar_display.replace("[", "\\[").replace("]", "\\]")
            
            # Générer l'horodatage et le type de message
            timestamp = time.strftime("%H:%M:%S")
            level_str = "PROGRESS"  # Conserver l'indication PROGRESS
                
            if status == "stop":
                # Supprimer cette barre du suivi
                if progress_key in LoggerUtils._active_text_progress_bars:
                    # Récupérer les infos de la barre
                    bar_info = LoggerUtils._active_text_progress_bars[progress_key]
                    line_index = bar_info.get("line_index")
                    del LoggerUtils._active_text_progress_bars[progress_key]
                    
                    # Vérifier si c'est la dernière barre active pour ce plugin
                    plugin_id = progress_key.split('_')[0] if '_' in progress_key else progress_key
                    active_bars_for_plugin = [k for k in LoggerUtils._active_text_progress_bars.keys() 
                                            if k.startswith(f"{plugin_id}_") or k == plugin_id]
                    
                    if not active_bars_for_plugin and line_index is not None:
                        # C'est la dernière barre pour ce plugin
                        current_text = logs.renderable or ""
                        if current_text:
                            # Si nous connaissons l'index de ligne, nous pouvons être plus précis
                            lines = current_text.split("\n")
                            if 0 <= line_index < len(lines):
                                # Supprimer cette ligne uniquement
                                del lines[line_index]
                                new_text = "\n".join(lines)
                                if new_text and not new_text.endswith("\n"):
                                    new_text += "\n"
                                logs.update(new_text)
            else:  # status == "running"
                current_text = logs.renderable or ""
                
                # Vérifier si cette barre est déjà active
                is_active = progress_key in LoggerUtils._active_text_progress_bars
                
                if is_active:
                    # Récupérer les informations de la barre active
                    bar_info = LoggerUtils._active_text_progress_bars[progress_key]
                    line_index = bar_info.get("line_index")
                    
                    if line_index is not None and "\n" in current_text:
                        # Diviser le texte en lignes
                        lines = current_text.split("\n")
                        
                        # Vérifier que l'index est valide
                        if 0 <= line_index < len(lines):
                            # Vérifier si cette ligne contient déjà une barre de progression
                            # Format: [cyan]hh:mm:ss[/cyan]  [blue]PROGRESS[/blue]  [color]bar_display[/color]
                            
                            # Nous cherchons à remplacer uniquement la partie après "PROGRESS]  "
                            old_line = lines[line_index]
                            progress_marker = "[/blue]  "
                            progress_pos = old_line.find(progress_marker)
                            
                            if progress_pos != -1:
                                # Trouvé l'indicateur PROGRESS
                                prefix = old_line[:progress_pos + len(progress_marker)]
                                # Remplacer tout ce qui suit par la nouvelle barre
                                lines[line_index] = f"{prefix}[{color}]{safe_bar_display}[/{color}]"
                            else:
                                # Format inconnu, créer une nouvelle ligne complète
                                formatted_bar = f"[cyan]{timestamp}[/cyan]  [blue]{level_str:7}[/blue]  [{color}]{safe_bar_display}[/{color}]"
                                lines[line_index] = formatted_bar
                            
                            # Reconstruire le texte
                            new_text = "\n".join(lines)
                            logs.update(new_text)
                        else:
                            # L'index n'est plus valide
                            is_active = False
                    else:
                        # Pas d'index valide ou pas de sauts de ligne
                        is_active = False
                
                if not is_active:
                    # Ajouter une nouvelle barre avec préfixe complet
                    formatted_bar = f"[cyan]{timestamp}[/cyan]  [blue]{level_str:7}[/blue]  [{color}]{safe_bar_display}[/{color}]"
                    
                    # Ajouter la barre comme nouvelle ligne
                    if current_text and not current_text.endswith("\n"):
                        current_text += "\n"
                    new_text = current_text + formatted_bar
                    logs.update(new_text)
                    
                    # Déterminer l'index de la ligne pour cette barre
                    line_index = len(new_text.split("\n")) - 1 if "\n" in new_text else 0
                    
                    # Stocker les informations de la barre
                    LoggerUtils._active_text_progress_bars[progress_key] = {
                        "line_index": line_index,
                        "color": color
                    }
                
                # Forcer le défilement vers le bas
                logs_container = app.query_one("#logs-container", ScrollableContainer)
                if logs_container:
                    logs_container.scroll_end(animate=False)
                    
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage de la barre de progression textuelle: {str(e)}")
            logger.error(traceback.format_exc())

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
                
            # Pour les messages de type PROGRESS_TEXT, utiliser la fonction spéciale
            if message_obj.type == MessageType.PROGRESS_TEXT:
                # Extraire les données du message
                if hasattr(message_obj, 'data') and isinstance(message_obj.data, dict):
                    status = message_obj.data.get("status", "running")
                    # Créer une clé unique pour cette barre
                    progress_key = f"{message_obj.source}_{message_obj.instance_id}"
                    # Afficher la barre de progression textuelle
                    await LoggerUtils._display_text_progress_bar(app, progress_key, message_obj.content, status)
                return
            
            # Vérifier si app est valide
            if app is None:
                logger.error("Erreur: app est None dans display_message")
                return
                
            # Vérifier si message_obj contient un target_ip (important pour le debug SSH)
            has_target_ip = message_obj.target_ip is not None
            if has_target_ip:
                logger.debug(f"Message avec target_ip: {message_obj.target_ip}")
                
            # Utiliser le formateur de message du module messaging
            formatted_message = MessageFormatter.format_for_rich_textual(message_obj)
            
            # Mise à jour des logs dans l'interface
            try:
                logs = app.query_one("#logs-text", Static)
                if logs:
                    current_text = logs.renderable or ""
                    
                    # Vérifier s'il y a des barres de progression actives
                    has_active_bars = bool(LoggerUtils._active_text_progress_bars)
                    
                    if has_active_bars:
                        # Terminer toutes les barres de progression actives
                        LoggerUtils._active_text_progress_bars.clear()
                        # Ajouter un saut de ligne avant le message
                        if current_text and not current_text.endswith("\n"):
                            current_text += "\n"
                    elif current_text and not current_text.endswith("\n"):
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
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de l'interface: {str(e)}")
            
            # Journalisation dans le fichier
            log_methods = {
                MessageType.INFO: logger.info,
                MessageType.WARNING: logger.warning,
                MessageType.ERROR: logger.error,
                MessageType.DEBUG: logger.debug,
                MessageType.SUCCESS: logger.info,
                MessageType.PROGRESS: logger.debug,  # Utiliser debug pour les messages de progression
                MessageType.PROGRESS_TEXT: logger.debug,  # Utiliser debug pour les barres textuelles
                MessageType.UNKNOWN: logger.info
            }
            
            # Utiliser le formateur de message pour fichier de log du module messaging
            content = MessageFormatter.format_for_log_file(message_obj)
                
            log_method = log_methods.get(message_obj.type, logger.info)
            log_method(content)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage d'un message: {str(e)}")
            logger.error(f"Message: {str(message_obj.__dict__)}")
            logger.error(traceback.format_exc())
            try:
                # Tenter une approche plus simple en cas d'erreur
                logs = app.query_one("#logs-text")
                if logs:
                    error_text = f"\nERREUR DE LOG: {message_obj.content}"
                    logs.update(logs.renderable + error_text)
            except:
                pass

    @staticmethod
    async def add_log(app, message: str, level: str = "info", target_ip: Optional[str] = None):
        """Ajoute un message au log de l'application"""
        try:
            # Créer le message au format JSON pour l'interface
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message
            }
            
            if target_ip:
                log_entry["target_ip"] = target_ip
                
            # Convertir en JSON
            log_json = json.dumps(log_entry)
            
            # Traiter avec process_output_line pour assurer un traitement cohérent
            await LoggerUtils.process_output_line(app, log_json, None, target_ip)
                
            # Envoyer également à la méthode add_log_message de l'application si disponible
            if hasattr(app, "add_log_message"):
                await app.add_log_message(log_json)
                
            # Logger pour le débogage
            logger.debug(f"Log ajouté: {log_entry}")
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du log: {e}")
            logger.error(traceback.format_exc())

    @staticmethod
    async def process_output_line(app, line: str, plugin_widget, target_ip: Optional[str] = None):
        """Traite une ligne de sortie au format JSONL"""
        try:
            # Tenter de parser la ligne comme JSON
            log_entry = json.loads(line)
            
            # Vérifier s'il s'agit d'un message imbriqué
            if log_entry.get('plugin_name') == 'ssh_wrapper' and isinstance(log_entry.get('message'), str):
                if log_entry['message'].startswith('{') and log_entry['message'].endswith('}'):
                    try:
                        # Extraire le message interne
                        inner_message = json.loads(log_entry['message'])
                        # Si c'est un message JSON valide, le traiter récursivement avec le même target_ip
                        await LoggerUtils.process_output_line(app, log_entry['message'], plugin_widget, target_ip)
                        return  # Ne pas continuer le traitement après avoir traité le message imbriqué
                    except (json.JSONDecodeError, Exception) as e:
                        # Si l'extraction échoue, continuer avec le traitement normal
                        logger.debug(f"Échec de l'extraction du message imbriqué: {e}")
            
            # Si c'est un message de progression standard
            if log_entry.get("level") == "progress":
                current_step = log_entry.get("current_step", 0)
                total_steps = log_entry.get("total_steps", 0)
                
                # Récupérer le pourcentage directement du message
                message_data = log_entry.get("message", {})
                if isinstance(message_data, dict) and "data" in message_data:
                    percentage = message_data["data"].get("percentage", 0.0)
                else:
                    percentage = 0.0
                
                # Créer un objet Message avec les informations de progression
                message_obj = Message(
                    type=MessageType.PROGRESS,
                    content="",  # Pas de message texte pour la progression
                    source=log_entry.get("plugin_name"),
                    progress=float(percentage),  # Le pourcentage est déjà entre 0 et 1
                    step=current_step,
                    total_steps=total_steps,
                    instance_id=log_entry.get("instance_id"),
                    target_ip=target_ip
                )
                
                # Mettre à jour le widget de progression immédiatement
                # Utiliser le widget spécifique si disponible, sinon chercher le bon widget
                if plugin_widget:
                    # Le pourcentage est déjà entre 0 et 1, pas besoin de diviser par 100
                    await plugin_widget.update_progress_async(percentage, f"Étape {current_step}/{total_steps}")
                else:
                    await LoggerUtils._update_progress_widget(app, message_obj)
                
                # Ne pas afficher le message de progression dans les logs pour éviter la duplication
                return
                
            # Si c'est un message de progression textuelle
            elif log_entry.get("level") == "progress-text":
                # Extraire les données du message
                message_data = log_entry.get("message", {})
                
                # S'assurer que nous avons un dictionnaire data
                if isinstance(message_data, dict) and "data" in message_data:
                    data = message_data["data"]
                else:
                    # Fallback si les données ne sont pas correctement formatées
                    data = {}
                
                status = data.get("status", "running")
                pre_text = data.get("pre_text", "")
                post_text = data.get("post_text", "")
                pb_id = data.get("id", "default")  # ID de la barre, "default" par défaut
                color = data.get("color", "blue")  # Couleur, "blue" par défaut
                filled_char = data.get("filled_char", "■")  # Caractère rempli
                empty_char = data.get("empty_char", "□")  # Caractère vide
                
                # Pour contourner le problème d'affichage, utiliser directement la barre
                # fournie par l'émetteur au lieu de la reconstruire
                bar = data.get("bar", "")
                percentage = data.get("percentage", 0)
                
                # Créer une clé unique pour cette barre de progression
                # Inclure l'ID de la barre dans la clé pour supporter plusieurs barres par plugin
                progress_key = f"{log_entry.get('plugin_name')}_{log_entry.get('instance_id')}_{pb_id}"
                
                # Construire l'affichage de la barre
                if status == "running":
                    # Format: pre_text [Barre visuelle] post_text Pourcentage%
                    bar_display = f"{pre_text} {bar} {post_text} {percentage}%"
                    
                    # Créer un message de type PROGRESS_TEXT
                    message_obj = Message(
                        type=MessageType.PROGRESS_TEXT,
                        content=bar_display,
                        source=log_entry.get("plugin_name"),
                        instance_id=log_entry.get("instance_id"),
                        target_ip=target_ip,
                        data={
                            "status": status,
                            "id": pb_id,
                            "color": color,
                            "bar": bar,
                            "percentage": percentage
                        }
                    )
                    
                    # Afficher la barre de progression avec la couleur spécifiée
                    await LoggerUtils._display_text_progress_bar(app, progress_key, bar_display, status, color)
                else:  # status == "stop"
                    # Indiquer la fin de la barre
                    await LoggerUtils._display_text_progress_bar(app, progress_key, "", "stop", color)
                
                return
            else:
                # Pour les autres types de messages
                level = log_entry.get("level", "info")
                # Convertir le niveau en MessageType
                message_type = {
                    "info": MessageType.INFO,
                    "warning": MessageType.WARNING,
                    "error": MessageType.ERROR,
                    "success": MessageType.SUCCESS,
                    "debug": MessageType.DEBUG
                }.get(level, MessageType.INFO)
                
                # Récupérer le message, qui peut être un objet ou une chaîne
                message_content = log_entry.get("message", "")
                if isinstance(message_content, dict):
                    # Si c'est un dictionnaire, essayer d'extraire la partie pertinente
                    message_content = str(message_content)
                
                message_obj = Message(
                    type=message_type,
                    content=message_content,
                    source=log_entry.get("plugin_name"),
                    instance_id=log_entry.get("instance_id"),
                    target_ip=target_ip
                )
                await LoggerUtils.display_message(app, message_obj)
                
        except json.JSONDecodeError:
            # Si ce n'est pas du JSON, logger un avertissement
            logger.warning(f"Ligne non-JSON reçue: {line}")
            # En mode SSH, on veut quand même afficher les lignes non-JSON
            if target_ip:
                message_obj = Message(
                    type=MessageType.INFO,
                    content=line,
                    target_ip=target_ip
                )
                await LoggerUtils.display_message(app, message_obj)
        except Exception as e:
            logger.error(f"Erreur lors du traitement de la ligne: {e}")
            logger.error(traceback.format_exc())

    @staticmethod
    async def clear_logs(app):
        """Effacement des logs"""
        try:
            logs_widget = app.query_one("#logs-text")
            if logs_widget:
                logs_widget.update("")
                
            # Réinitialiser le cache de messages et les barres actives
            LoggerUtils._processed_lines.clear()
            LoggerUtils._active_text_progress_bars.clear()
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