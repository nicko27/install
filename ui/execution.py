"""
Screen d'exécution des plugins.
Gère l'interface et la logique d'exécution des plugins de manière séquentielle.
"""

import os
import sys
import json
import time
import logging
import importlib.util
import asyncio
import subprocess
import threading
import re
from datetime import datetime
from typing import Dict, Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical, HorizontalGroup
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Label, ProgressBar, Static, Footer, Header
from textual.reactive import reactive
from textual import events
from textual.binding import Binding

from .choice import get_plugin_folder_name

# Configuration du logger
logger = logging.getLogger('install_ui')
logger.setLevel(logging.DEBUG)

# Handler pour le fichier
file_handler = logging.FileHandler('logs/debug.log')
file_handler.setLevel(logging.DEBUG)

# Format des logs
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Ajout du handler au logger
logger.addHandler(file_handler)

class PluginContainer(Container):
    """Conteneur pour afficher l'état et la progression d'un plugin"""

    def __init__(self, plugin_id: str, plugin_name: str):
        """Initialise le conteneur avec l'ID et le nom du plugin
        
        Args:
            plugin_id: L'ID complet du plugin (ex: bash_interactive_1)
            plugin_name: Le nom à afficher dans l'interface
        """
        super().__init__(id=f"plugin-{plugin_id}")
        self.plugin_id = plugin_id
        # Récupérer le nom du dossier pour les logs
        self.folder_name = get_plugin_folder_name(plugin_id)
        # Nom affiché dans l'interface
        self.plugin_name = plugin_name
        self.classes = "plugin-container waiting"

    def compose(self) -> ComposeResult:
        """Création des widgets du conteneur"""
        with Horizontal():
            yield Label(self.plugin_name, classes="plugin-name")
            yield ProgressBar(classes="plugin-progress", show_eta=False, total=100.0)
            yield Label("En attente", classes="plugin-status")

    def update_progress(self, progress: float, step: str = None):
        """Mise à jour de la progression du plugin"""
        try:
            # Récupérer la barre de progression
            progress_bar = self.query_one(ProgressBar)
            if progress_bar:
                # Convertir la progression en pourcentage et s'assurer qu'elle est entre 0 et 100
                progress_value = max(0, min(100, progress * 100))
                progress_bar.update(progress=progress_value)
            
            # Mettre à jour le texte de statut si fourni
            if step:
                status_label = self.query_one(".plugin-status")
                if status_label:
                    status_label.update(step)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la progression: {str(e)}")

    def set_status(self, status: str, message: str = None):
        """Mise à jour du statut du plugin"""
        # Mettre à jour les classes CSS
        self.classes = f"plugin-container {status}"
        
        # Définir le texte du statut
        status_map = {
            'waiting': 'En attente',
            'running': 'En cours',
            'success': 'Terminé',
            'error': 'Erreur'
        }
        status_text = status_map.get(status, status)
        if message:
            status_text = f"{status_text} - {message}"
        
        # Mettre à jour le widget de statut
        self.query_one(".plugin-status").update(status_text)

class ExecutionWidget(Container):
    """Écran d'exécution des plugins"""

    # État d'exécution
    is_running = reactive(False)
    continue_on_error = reactive(False)
    show_logs = reactive(False)

    BINDINGS = [
        Binding("l", "toggle_logs", "Afficher/Masquer les logs", show=False)
    ]

    def __init__(self, plugins_config: dict = None):
        """Initialise le widget avec la configuration des plugins"""
        super().__init__()
        self.plugins: Dict[str, PluginContainer] = {}
        self.plugins_config = plugins_config or {}
        self._current_plugin = None
        self._total_plugins = 0
        self._executed_plugins = 0

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        # En-tête
        yield Header(name="Exécution des plugins")

        
        # Liste des plugins
        with ScrollableContainer(id="plugins-list"):
            # Créer les conteneurs de plugins
            for plugin_id, config in self.plugins_config.items():
                # Récupérer le nom du plugin depuis son dossier
                folder_name = get_plugin_folder_name(plugin_id)
                plugin_name = config.get('name', folder_name)
                container = PluginContainer(plugin_id, plugin_name)
                self.plugins[plugin_id] = container
                yield container

        # Zone des logs
        with Horizontal(id="logs"):
            with ScrollableContainer(id="logs-container"):
                yield Static("", id="logs-text")
        with Horizontal(id="button-container"):             
            yield Button("Retour", id="back-button", variant="error")
            yield Button("Quitter", id="quit-button", variant="error")
            yield Checkbox("Continuer en cas d'erreur", id="continue-on-error")
            yield Label("Progression globale", id="global-progress-label")
            yield ProgressBar(id="global-progress", show_eta=False)
            yield Button("Démarrer", id="start-button", variant="primary")   

        yield Footer()

    async def on_mount(self) -> None:
        """Appelé au montage initial du widget"""
        
        # Initialisation basique
        self.update_global_progress(0)
        self.set_current_plugin("aucun")
        
        # Initialiser l'état de la checkbox et des logs
        self.continue_on_error = False
        self.show_logs = False
        
        # S'assurer que les logs sont masqués au démarrage
        logs_container = self.query_one("#logs-container")
        if logs_container:
            logs_container.add_class("hidden")

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gestion du changement d'état de la checkbox"""
        if event.checkbox.id == "continue-on-error":
            self.continue_on_error = event.value
            logger.debug(f"Option 'continuer en cas d'erreur' changée à: {self.continue_on_error}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gestion des clics sur les boutons"""
        button_id = event.button.id
        logger.debug(f"Clic sur le bouton {button_id}")

        if not button_id:
            logger.warning("Bouton sans identifiant détecté")
            return

        try:
            if button_id == "start-button" and not event.button.disabled:
                # Vérifier si le bouton n'est pas déjà désactivé
                await self.start_execution()
            elif button_id == "back-button":
                # Import ici pour éviter les imports circulaires
                from .config import PluginConfig
                
                # Import la fonction de récupération du dossier plugin
                from .choice import get_plugin_folder_name
                
                # Extraire les infos de plugin_id
                plugin_instances = []
                for plugin_id in self.plugins_config.keys():
                    # Récupérer le dossier du plugin
                    folder_name = get_plugin_folder_name(plugin_id)
                    # Extraire l'instance ID (dernier nombre)
                    instance_id = int(plugin_id.split('_')[-1])
                    # Ajouter le tuple (nom_plugin, instance_id)
                    plugin_instances.append((folder_name, instance_id))
                
                # Créer l'écran de configuration
                config_screen = PluginConfig(plugin_instances)
                
                # Revenir à l'écran de configuration
                self.app.switch_screen(config_screen)
            elif button_id == "quit-button":
                self.app.exit()

        except Exception as e:
            logger.error(f"Erreur lors du traitement du clic sur {button_id} : {str(e)}")
            # En cas d'erreur sur le bouton start, on le réactive
            if button_id == "start-button":
                event.button.disabled = False
                logger.debug("Bouton réactivé après erreur")
            # Propager l'erreur pour le traitement global
            raise

    async def start_execution(self):
        """Démarrage de l'exécution des plugins"""
        # Vérifier si une exécution est déjà en cours
        if self.is_running:
            logger.debug("Exécution déjà en cours, ignoré")
            return

        start_button = self.query_one("#start-button")
        if not start_button:
            logger.error("Bouton de démarrage introuvable")
            return

        try:
            # Démarrer l'exécution
            self.is_running = True
            logger.info("Démarrage de l'exécution")
            start_button.disabled = True
            logger.debug("Bouton désactivé")
            
            # Réinitialiser l'interface
            self.update_global_progress(0)
            self.set_current_plugin("aucun")
            await self.clear_logs()
            
            # Exécuter les plugins
            await self.run_plugins()

        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution : {str(e)}")
            await self.add_log(f"Erreur lors du démarrage : {str(e)}", 'error')
            # Réactiver le bouton en cas d'erreur
            start_button.disabled = False
            logger.debug("Bouton réactivé après erreur")
        finally:
            self.is_running = False

    async def run_plugins(self):
        """Exécuter les plugins de façon séquentielle"""
        try:
            total_plugins = len(self.plugins)
            logger.debug(f"Démarrage de l'exécution de {total_plugins} plugins")
            executed = 0

            for plugin_id, plugin_widget in self.plugins.items():
                try:
                    config = self.plugins_config[plugin_id]
                    self.set_current_plugin(plugin_widget.plugin_name)
                    
                    # Initialiser la progression et le statut
                    plugin_widget.update_progress(0.0, "Démarrage...")
                    plugin_widget.set_status('running')
                    
                    # Créer une queue pour ce plugin
                    result_queue = asyncio.Queue()
                    
                    # Exécuter le plugin et attendre sa fin
                    # Exécuter le plugin et attendre sa fin
                    await self.run_plugin(plugin_id, plugin_widget, config, executed, total_plugins, result_queue)
                    
                    # Récupérer le résultat
                    success, message = await result_queue.get()
                    
                    # Récupérer le nom du dossier du plugin pour les logs
                    plugin_folder = get_plugin_folder_name(plugin_id)
                    
                    if success:
                        await self.add_log(f"Plugin {plugin_folder} terminé avec succès")
                        plugin_widget.set_status('success')
                    else:
                        plugin_widget.set_status('error', message)
                        await self.add_log(f"Erreur dans le plugin {plugin_folder}: {message}", 'error')
                        if not self.continue_on_error:
                            logger.error(f"Arrêt de l'exécution suite à l'erreur du plugin {plugin_folder}")
                            return
                        else:
                            logger.warning(f"Continuation après erreur du plugin {plugin_folder} (option activée)")
                            await self.add_log(f"Continuation après erreur (option activée)", 'warning')
                    
                    executed += 1
                    # Mise à jour de la progression globale
                    self.update_global_progress(executed / total_plugins)
                        
                except Exception as e:
                    # Récupérer le nom du dossier du plugin pour les logs
                    plugin_folder = get_plugin_folder_name(plugin_id)
                    
                    logger.error(f"Erreur inattendue dans le plugin {plugin_folder}: {str(e)}")
                    plugin_widget.set_status('error', str(e))
                    await self.add_log(f"Erreur inattendue: {str(e)}", 'error')
                    if not self.continue_on_error:
                        return
                    else:
                        logger.info(f"Continuation après erreur du plugin {plugin_folder} (option activée)")
                        await self.add_log(f"Continuation après erreur (option activée)", 'warning')
                        executed += 1
                        self.update_global_progress(executed / total_plugins)
            
            # Mise à jour finale
            self.update_global_progress(1.0)
            self.set_current_plugin("Terminé")
            await self.add_log("Exécution terminée avec succès")
        
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution des plugins : {str(e)}")
            await self.add_log(f"Erreur lors de l'exécution : {str(e)}", 'error')
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'exécution des plugins : {str(e)}")
            await self.add_log(f"Erreur inattendue : {str(e)}", 'error')

    async def run_plugin(self, plugin_id, plugin_widget, config, executed, total_plugins, result_queue):
        """Exécute un plugin"""
        try:
            # Extraire le nom du plugin pour les logs
            folder_name = plugin_widget.folder_name
            logger.debug(f"Démarrage du plugin {folder_name} ({plugin_id})")
            
            # Initialiser la barre de progression
            plugin_widget.set_status('running')
            plugin_widget.update_progress(0.0, "Démarrage...")

            # Obtenir le nom du dossier du plugin
            folder_name = get_plugin_folder_name(plugin_id)
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", folder_name)
            
            # Vérifier si c'est un plugin bash
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.debug(f"Détecté comme plugin bash: {plugin_id}")
                is_bash_plugin = True
                exec_path = os.path.join(plugin_dir, "main.sh")
            else:
                # Sinon c'est un plugin Python
                exec_path = os.path.join(plugin_dir, "exec.py")
                logger.debug(f"Chargement du plugin Python depuis {exec_path}")
                is_bash_plugin = False
            
            # Préparer la commande en fonction du type de plugin
            if is_bash_plugin:
                cmd = ["bash", exec_path, config.get('name', 'test'), config.get('intensity', 'light')]
            else:
                cmd = [sys.executable, exec_path, json.dumps(config)]
            
            # Créer le processus de manière asynchrone
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=plugin_dir
            )
            
            # Lire la sortie de manière asynchrone
            async def read_stream(stream, is_error=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line = line.decode().strip()
                    if line:
                        await self.handle_output(line, plugin_widget, executed, total_plugins)
            
            # Lancer la lecture des flux stdout et stderr
            await asyncio.gather(
                read_stream(process.stdout),
                read_stream(process.stderr, True)
            )
            
            # Attendre la fin du processus
            exit_code = await process.wait()
            
            # Traiter le résultat
            if exit_code == 0:
                await self.add_log(f"Plugin {folder_name} terminé avec succès")
                plugin_widget.set_status('success')
                await result_queue.put((True, "Exécution terminée avec succès"))
            else:
                error_msg = f"Erreur lors de l'exécution (code {exit_code})"
                plugin_widget.set_status('error', error_msg)
                await self.add_log(f"Erreur dans le plugin {folder_name}: {error_msg}", 'error')
                await result_queue.put((False, error_msg))
                
        except Exception as e:
            error_msg = f"Erreur lors de l'exécution: {str(e)}"
            logger.error(error_msg)
            await result_queue.put((False, error_msg))


    def read_pipe(self, pipe, output_handler, is_error=False):
        """Lit la sortie d'un pipe de façon asynchrone"""
        try:
            # Utiliser un buffer pour accumuler les lignes partielles
            buffer = ""
            while True:
                # Lire un caractère à la fois pour éviter les blocages
                char = pipe.read(1)
                if not char:
                    # Fin du flux, traiter le buffer restant
                    if buffer:
                        line = buffer.strip()
                        if line:
                            output_handler(line)
                    break
                
                # Ajouter le caractère au buffer
                buffer += char.decode('utf-8')
                
                # Si on trouve une fin de ligne, traiter la ligne
                if '\n' in buffer:
                    lines = buffer.split('\n')
                    # Garder la dernière ligne partielle dans le buffer
                    buffer = lines[-1]
                    # Traiter toutes les lignes complètes
                    for line in lines[:-1]:
                        line = line.strip()
                        if line:
                            output_handler(line)
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du pipe: {str(e)}")

    async def handle_output(self, line: str, plugin_widget, executed, total_plugins):
        """Gère les logs et la progression d'un plugin"""
        try:
            # Ignorer les lignes vides
            line = line.strip()
            if not line:
                return

            # Parser le format standard [timestamp] [level] message
            match = re.match(r'\[(.*?)\] \[(\w+)\] (.*)', line)
            if match:
                timestamp, level, message = match.groups()
                level = level.lower()
                
                # Gérer la progression si présente
                if "Progression :" in message:
                    progress_match = re.search(r'Progression : (\d+)% \(étape (\d+)/(\d+)\)', message)
                    if progress_match:
                        # Récupérer et valider les valeurs
                        progress = float(progress_match.group(1)) / 100.0  # Convertir en fraction
                        current_step = int(progress_match.group(2))
                        total_steps = int(progress_match.group(3))
                        
                        # Vérifier que les valeurs sont valides
                        if 0 <= progress <= 1 and current_step <= total_steps:
                            step_text = f"Étape {current_step}/{total_steps}"
                            
                            # Mettre à jour la barre de progression du plugin
                            plugin_widget.update_progress(progress, step_text)
                            
                            # Mettre à jour la progression globale
                            global_progress = (executed + progress) / total_plugins
                            self.update_global_progress(global_progress)
                            
                            logger.debug(f"Progression mise à jour: {progress * 100}% ({step_text})")
                        
                        # Ajouter le log
                        await self.sync_ui(
                            plugin_widget,
                            executed,
                            total_plugins,
                            log_entry=line
                        )
                        return
                
                # Traiter les autres types de messages
                if level in ['error', 'warning', 'info', 'debug', 'success']:
                    # Pour les erreurs et warnings, mettre à jour le statut
                    if level in ['error', 'warning']:
                        await self.sync_ui(
                            plugin_widget,
                            executed,
                            total_plugins,
                            status='error' if level == 'error' else 'warning',
                            message=message,
                            log_entry=line
                        )
                    else:
                        await self.sync_ui(plugin_widget, executed, total_plugins, log_entry=line)
            else:
                # Ligne sans format standard, l'afficher telle quelle
                await self.sync_ui(plugin_widget, executed, total_plugins, log_entry=line)
                
        except Exception as e:
            logger.error(f"Erreur dans handle_output: {str(e)}")

    async def sync_ui(self, plugin_widget, executed, total_plugins, progress=None, step=None, status=None, message=None, log_entry=None):
        """Synchronise l'interface utilisateur avec les mises à jour du plugin"""
        try:
            # Mettre à jour la progression si spécifiée
            if progress is not None:
                # Vérifier si nous sommes dans le thread principal
                if self.app._thread_id == threading.get_ident():
                    # Dans le thread principal, appeler directement
                    plugin_widget.update_progress(progress, step)
                else:
                    # Dans un thread différent, utiliser call_from_thread
                    await self.app.call_from_thread(plugin_widget.update_progress, progress, step)
                # Mettre à jour la progression globale
                global_progress = (executed + progress) / total_plugins
                await self.app.call_from_thread(self.update_global_progress, global_progress)
            
            # Mettre à jour le statut si spécifié
            if status is not None:
                if self.app._thread_id == threading.get_ident():
                    plugin_widget.set_status(status, message)
                else:
                    await self.app.call_from_thread(plugin_widget.set_status, status, message)
            
            # Mettre à jour les logs si spécifié
            if log_entry is not None:
                if self.app._thread_id == threading.get_ident():
                    # Dans le thread principal
                    await self.add_log(log_entry)
                else:
                    # Dans un thread différent
                    await self.app.call_from_thread(self.add_log, log_entry)
                
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'UI: {str(e)}")

    async def clear_logs(self):
        """Effacement des logs"""
        logs_widget = self.query_one("#logs-text")
        if logs_widget:
            logs_widget.update("")

    def update_global_progress(self, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = self.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)

    def set_current_plugin(self, plugin_name: str):
            
        # Trouver le plugin en cours et scroller vers lui
        plugins_list = self.query_one("#plugins-list")
        if plugins_list:
            for plugin_id, plugin in self.plugins.items():
                if plugin.plugin_name == plugin_name:
                    # Scroller vers le plugin
                    plugin.scroll_visible()
                    break

    async def add_log(self, message: str, level: str = 'info'):
        """Ajout d'un message dans les logs avec formatage amélioré"""
        try:
            # Vérifier si nous sommes dans le thread principal
            if not self.app._thread_id == threading.get_ident():
                # Dans un thread différent, utiliser call_from_thread
                await self.app.call_from_thread(self.add_log, message, level)
                return

            logs = self.query_one("#logs-text")
            if logs:
                current_text = logs.renderable or ""
                timestamp = time.strftime("%H:%M:%S")
                
                # Normaliser le niveau de log
                level = level.lower()
                
                # Détection améliorée des messages de succès
                message_lower = message.lower()
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
                    message = progress
                
                # Styles de couleur améliorés pour une meilleure visibilité
                level_styles = {
                    'debug': 'dim grey',      # Plus subtil pour le debug
                    'info': 'bright_cyan',    # Plus visible pour l'info
                    'warning': 'bright_yellow', # Plus visible pour les avertissements
                    'error': 'bright_red',    # Plus visible pour les erreurs
                    'success': 'bright_green' # Plus visible pour les succès
                }
                style = level_styles.get(level, 'white')
                
                # Format du niveau avec largeur fixe et alignement à droite
                level_str = f"{level.upper():7}"
                
                # Format du message avec espacement cohérent
                formatted_message = f"[bright_cyan]{timestamp}[/bright_cyan]  [{style}]{level_str}[/{style}]  {message}"
                
                # Mise à jour des logs
                if current_text:
                    current_text += "\n"
                logs.update(current_text + formatted_message)
                
                # Forcer le défilement immédiat sans animation
                logs_container = self.query_one("#logs-container")
                if logs_container:
                    logs_container.scroll_end(animate=False)
                    
            # Ajout dans le fichier de logs de manière sécurisée
            valid_levels = {'debug', 'info', 'warning', 'error'}
            log_level = level if level in valid_levels else 'info'
            log_func = getattr(logger, log_level)
            log_func(message)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un log: {str(e)}")

class ExecutionScreen(Screen):
    """Écran simple contenant le widget d'exécution"""

    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/execution.css")

    def __init__(self, plugins_config: dict = None):
        """Initialise l'écran"""
        super().__init__()
        self.plugins_config = plugins_config

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        yield ExecutionWidget(self.plugins_config)
