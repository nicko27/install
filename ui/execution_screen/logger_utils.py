"""
Utilitaires de journalisation pour le module d'exécution.
"""

import time
import threading
import logging
import re
from rich.text import Text
from textual.widgets import Static
from textual.containers import ScrollableContainer

from ..utils.logging import get_logger

logger = get_logger('executor_logger')

class LoggerUtils:
    """Classe utilitaire pour la gestion des logs dans l'interface et le fichier de log"""
    
    @staticmethod
    def escape_markup(text):
        """Échapper les caractères spéciaux qui pourraient être interprétés comme du markup"""
        # Remplacer les crochets et autres caractères spéciaux
        if text is None:
            return ""
        
        # Échapper les caractères spéciaux Textual/Rich
        # Convertir les crochets, accolades, etc.
        escaped = text.replace("[", "\\[").replace("]", "\\]")
        return escaped
    
    @staticmethod
    def sanitize_log_message(message):
        """Nettoyer un message de log pour éviter les problèmes de markup"""
        # S'assurer que le message est une chaîne
        if not isinstance(message, str):
            message = str(message)
        
        # Échapper les caractères spéciaux
        return LoggerUtils.escape_markup(message)
    
    @staticmethod
    async def add_log(app, message: str, level: str = 'info'):
        """Ajout d'un message dans les logs avec formatage amélioré"""
        try:
            # Vérifier si nous sommes dans le thread principal
            if not app._thread_id == threading.get_ident():
                # Dans un thread différent, utiliser call_from_thread
                await app.call_from_thread(LoggerUtils.add_log, app, message, level)
                return

            logs = app.query_one("#logs-text")
            if logs:
                current_text = logs.renderable or ""
                timestamp = time.strftime("%H:%M:%S")
                
                # Normaliser le niveau de log
                level = level.lower()
                
                # Sanitiser le message
                safe_message = LoggerUtils.sanitize_log_message(message)
                
                # Détection améliorée des messages de succès
                message_lower = safe_message.lower()
                if any(term in message_lower for term in [
                    'terminé avec succès',
                    'réussi',
                    'succès',
                    'test bash test',
                    'exécution terminée',
                    'completed successfully'
                ]):
                    level = 'success'
                elif 'Progression :' in message:
                    # Extraire uniquement le pourcentage pour les messages de progression
                    progress = message.split('(')[0].strip()
                    safe_message = LoggerUtils.sanitize_log_message(progress)
                
                # Styles de couleur améliorés pour une meilleure visibilité
                level_styles = {
                    'debug': 'grey',
                    'info': 'cyan',
                    'warning': 'yellow',
                    'error': 'red',
                    'success': 'green'
                }
                style = level_styles.get(level, 'white')
                
                # Format du niveau avec largeur fixe et alignement à droite
                level_str = f"{level.upper():7}"
                
                # Format du message avec espacement cohérent - en utilisant des chaînes sûres
                formatted_message = f"[bright_cyan]{timestamp}[/bright_cyan]  [{style}]{level_str}[/{style}]  {safe_message}"
                
                # Mise à jour des logs
                if current_text:
                    current_text += "\n"
                logs.update(current_text + formatted_message)
                
                # Forcer le défilement immédiat sans animation
                logs_container = app.query_one("#logs-container")
                if logs_container:
                    logs_container.scroll_end(animate=False)
                    
            # Ajout dans le fichier de logs de manière sécurisée
            valid_levels = {'debug', 'info', 'warning', 'error'}
            log_level = level if level in valid_levels else 'info'
            log_func = getattr(logger, log_level)
            log_func(message)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un log: {str(e)}")
    
    @staticmethod
    async def clear_logs(app):
        """Effacement des logs"""
        logs_widget = app.query_one("#logs-text")
        if logs_widget:
            logs_widget.update("")
    
    @staticmethod
    def toggle_logs(app) -> None:
        """Afficher/Masquer les logs"""
        logs_container = app.query_one("#logs-container")
        if logs_container:
            if "hidden" in logs_container.classes:
                logs_container.remove_class("hidden")
                app.show_logs = True
            else:
                logs_container.add_class("hidden")
                app.show_logs = False