"""
Screen d'exécution des plugins.
Gère l'interface et la logique d'exécution des plugins de manière séquentielle.
"""

import os
import time
import logging
import importlib.util
import asyncio
from typing import Dict, Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, VerticalGroup, HorizontalGroup
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
        """Initialise le conteneur avec l'ID et le nom du plugin"""
        super().__init__(id=f"plugin-{plugin_id}")
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.classes = "plugin-container waiting"

    def compose(self) -> ComposeResult:
        """Création des widgets du conteneur"""
        with Horizontal():
            yield Label(self.plugin_name, classes="plugin-name")
            yield ProgressBar(classes="plugin-progress",show_eta=False)
            yield Label("En attente", classes="plugin-status")

    def update_progress(self, progress: float, step: str = None):
        """Mise à jour de la progression du plugin"""
        progress_bar = self.query_one(ProgressBar)
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)
        if step:
            status_label = self.query_one(".plugin-status")
            if status_label:
                status_label.update(step)

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

    CSS_PATH = "styles/execution.css"

    # État d'exécution
    is_running = reactive(False)
    continue_on_error = reactive(False)
    show_logs = reactive(False)

    BINDINGS = [
        Binding("l", "toggle_logs", "Afficher/Masquer les logs", show=True)
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
                plugin_name = config.get('name', plugin_id)
                container = PluginContainer(plugin_id, plugin_name)
                self.plugins[plugin_id] = container
                yield container

        # Zone des logs
        with ScrollableContainer(id="logs-container"):
            with Horizontal():
                yield Label("Logs:", id="logs-title")
            with ScrollableContainer(id="logs-content"):
                yield Static("", id="logs-text")
        with HorizontalGroup(id="button-container"):
            with HorizontalGroup(id="progress-zone"):
                yield Button("Démarrer", id="start-button", variant="primary")                
                yield Checkbox("Continuer en cas d'erreur", id="continue-on-error")
                yield Label("Plugin en cours : aucun", id="current-plugin")
                with HorizontalGroup():
                    yield Label("Progression globale")
                    yield ProgressBar(id="global-progress", show_eta=False)
            yield Label("")
            yield Button("Quitter", id="quit-button", variant="error")

        yield Footer()

    def action_quit_button(self) -> None:
        """Quitter l'application"""
        self.app.exit()


    def action_toggle_logs(self) -> None:
        """Action pour afficher/masquer les logs (raccourci 'l')"""
        self.show_logs = not self.show_logs
        logs_container = self.query_one("#logs-container")
        if logs_container:
            if self.show_logs:
                logs_container.remove_class("hidden")
                # Scroll to bottom when showing logs
                logs_content = self.query_one("#logs-content")
                if logs_content:
                    logs_content.scroll_end(animate=False)
            else:
                logs_container.add_class("hidden")
        logger.debug(f"Logs {'affichés' if self.show_logs else 'masqués'} via raccourci")

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

            import threading
            import queue
            
            try:
                for plugin_id, plugin_widget in self.plugins.items():
                    try:
                        config = self.plugins_config[plugin_id]
                        self.set_current_plugin(plugin_widget.plugin_name)
                        plugin_widget.set_status('running')
                        
                        # Créer une nouvelle queue pour ce plugin
                        result_queue = queue.Queue()
                        
                        # Exécuter le plugin dans un thread séparé
                        bound_run_plugin = self.run_plugin.__get__(self, self.__class__)
                        thread = threading.Thread(
                            target=bound_run_plugin,
                            args=(plugin_id, plugin_widget, config, executed, total_plugins, result_queue)
                        )
                        thread.start()
                        # Ne pas attendre la fin du thread ici pour garder l'UI réactive
                        
                        # Récupérer le résultat de manière non bloquante
                        while thread.is_alive():
                            await asyncio.sleep(0.1)
                        success, message = result_queue.get()
                        
                        # Traiter le résultat
                        if success:
                            await self.add_log(f"Plugin {plugin_widget.plugin_name} terminé avec succès")
                            plugin_widget.set_status('success')
                        else:
                            plugin_widget.set_status('error', message)
                            await self.add_log(f"Erreur dans le plugin {plugin_widget.plugin_name}: {message}", 'error')
                            if not self.continue_on_error:
                                logger.error(f"Arrêt de l'exécution suite à l'erreur du plugin {plugin_widget.plugin_name}")
                                return
                            else:
                                logger.warning(f"Continuation après erreur du plugin {plugin_widget.plugin_name} (option activée)")
                                await self.add_log(f"Continuation après erreur (option activée)", 'warning')
                        
                        executed += 1
                        
                    except Exception as e:
                        logger.error(f"Erreur inattendue dans le plugin {plugin_widget.plugin_name}: {str(e)}")
                        plugin_widget.set_status('error', str(e))
                        await self.add_log(f"Erreur inattendue: {str(e)}", 'error')
                        if not self.continue_on_error:
                            return
                        else:
                            logger.info(f"Continuation après erreur du plugin {plugin_widget.plugin_name} (option activée)")
                            await self.add_log(f"Continuation après erreur (option activée)", 'warning')
                            executed += 1
                
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

    def run_plugin(self, plugin_id, plugin_widget, config, executed, total_plugins, result_queue):
        """Exécute un plugin dans un thread séparé"""
        try:
            # Extraire le nom du plugin
            plugin_name = plugin_widget.plugin_name
            logger.debug(f"Démarrage du plugin {plugin_name} ({plugin_id})")

            # Obtenir le nom du dossier du plugin
            folder_name = get_plugin_folder_name(plugin_id)
            
            # Construire le chemin du plugin
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", folder_name)
            
            # Vérifier si c'est un plugin bash
            if os.path.exists(os.path.join(plugin_dir, "main.sh")):
                logger.debug(f"Détecté comme plugin bash: {plugin_id}")
                is_bash_plugin = True
            else:
                # Sinon essayer de charger comme plugin Python
                exec_path = os.path.join(plugin_dir, "exec.py")
                logger.debug(f"Chargement du plugin Python depuis {exec_path}")
                
                # Charger le module Python
                spec = importlib.util.spec_from_file_location("plugin_module", exec_path)
                if not spec or not spec.loader:
                    raise ImportError(f"Impossible de charger le plugin depuis {exec_path}")
                    
                main_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(main_module)
                is_bash_plugin = False
            
            # Créer les callbacks
            def sync_progress(progress: float, step: str = None):
                def _update():
                    # Convertir le pourcentage en valeur décimale (0-1)
                    progress_value = progress / 100.0 if progress > 1 else progress
                    plugin_widget.update_progress(progress_value, step)
                    # Calculer la progression globale en tenant compte de tous les plugins
                    global_progress = (executed + progress_value) / total_plugins
                    self.update_global_progress(global_progress)
                    if step and self.show_logs:
                        logs_container = self.query_one("#logs-container")
                        logs = self.query_one("#logs-text")
                        if logs:
                            current_text = logs.renderable or ""
                            message = f"[{plugin_widget.plugin_name}] Progression {int(progress_value*100)}% - {step}"
                            logs.update(current_text + ("\n" if current_text else "") + message)
                            logs_container.scroll_end(animate=False)
                self.app.call_from_thread(_update)

            def sync_status(status: str, message: str = None):
                def _update():
                    plugin_widget.set_status(status, message)
                    if message:
                        logs_container = self.query_one("#logs-content")
                        logs = self.query_one("#logs-text")
                        if logs:
                            current_text = logs.renderable or ""
                            log_message = f"[{plugin_widget.plugin_name}] {message}"
                            logs.update(current_text + ("\n" if current_text else "") + log_message)
                            logs_container.scroll_end(animate=False)
                self.app.call_from_thread(_update)

            # Créer une fonction pour parser la progression depuis les logs
            def parse_progress_from_output(output):
                if isinstance(output, str) and '[INFO] Progression :' in output:
                    try:
                        # Extraire le pourcentage (format: "Progression : XX% (étape Y/Z)")
                        progress_str = output.split('[INFO] Progression :')[1].split('%')[0].strip()
                        progress = float(progress_str)
                        # Extraire l'étape si présente
                        step = output.split('(')[1].split(')')[0] if '(' in output else None
                        return progress, step
                    except (IndexError, ValueError):
                        pass
                return None, None
            
            # Créer une fonction pour gérer les logs en temps réel
            def handle_log_output(line: str):
                try:
                    # Vérifier si c'est une ligne de log valide
                    if '[INFO]' in line or '[DEBUG]' in line or '[WARNING]' in line or '[ERROR]' in line:
                        # Déterminer le niveau de log
                        if '[INFO]' in line:
                            level = 'info'
                        elif '[DEBUG]' in line:
                            level = 'debug'
                        elif '[WARNING]' in line:
                            level = 'warning'
                        else:
                            level = 'error'
                        
                        # Extraire le message
                        message = line.split(']', 2)[-1].strip()
                        logger.debug(f"Message extrait: {message} (niveau: {level})")
                        
                        # Mettre à jour les logs dans l'interface de manière synchrone
                        def update_logs():
                            try:
                                logs = self.query_one("#logs-text")
                                if logs:
                                    current_text = logs.renderable or ""
                                    timestamp = time.strftime("%H:%M:%S")
                                    
                                    # Formater les messages de progression
                                    if "Progression :" in message:
                                        match = re.match(r'Progression : (\d+)% \(étape (\d+)/(\d+)\)', message)
                                        if match:
                                            percentage = match.group(1)
                                            current_step = match.group(2)
                                            total_steps = match.group(3)
                                            message = f"[→] Étape {current_step}/{total_steps} - {percentage}% terminé"
                                    
                                    # Ignorer les messages de progression simples
                                    if message.strip() == "Progression : 0%" or message.strip() == "Progression : 100%":
                                        return
                                        
                                    # Formater le message avec des espaces appropriés
                                    new_message = f"[{timestamp}]  [{level.upper():7}]  {message}"
                                    
                                    # Ajouter le message aux logs existants
                                    logs.update(current_text + ("\n" if current_text else "") + new_message)
                                    
                                    # Forcer l'affichage des logs et scroller en bas
                                    logs_container = self.query_one("#logs-container")
                                    if logs_container:
                                        logs_container.remove_class("hidden")
                                        logs_container.scroll_end(animate=False)
                            except Exception as e:
                                logger.error(f"Erreur lors de la mise à jour des logs: {str(e)}")
                        
                        self.app.call_from_thread(update_logs)
                        
                        # Vérifier si c'est une ligne de progression
                        if "Progression :" in line:
                            try:
                                progress_str = line.split("Progression :")[1].split("%")[0].strip()
                                progress = float(progress_str)
                                step = f"Étape {progress}%"
                                sync_progress(progress, step)
                            except Exception as e:
                                logger.error(f"Erreur lors du parsing de la progression: {str(e)}")
                except Exception as e:
                    logger.error(f"Erreur dans handle_log_output: {str(e)}")
            
            # Exécuter le script bash si nécessaire
            if is_bash_plugin:
                import subprocess
                import threading
                
                # Construire le chemin du script bash
                script_path = os.path.join(plugin_dir, "main.sh")
                if not os.path.exists(script_path):
                    raise FileNotFoundError(f"Script bash introuvable : {script_path}")
                
                # Ajouter un log de début d'exécution
                def _log_start():
                    # Créer une fonction asynchrone pour ajouter le log
                    async def _add_log():
                        await self.add_log(f"Démarrage du script bash: {script_path}", 'info')
                    
                    # Exécuter la fonction asynchrone dans le thread principal
                    self.app.call_from_thread(lambda: self.app.run_worker(_add_log()))
                
                # Créer le processus
                process = subprocess.Popen(
                    ["bash", script_path, config.get('name', 'test'), config.get('intensity', 'light')],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    cwd=plugin_dir  # Exécuter dans le dossier du plugin
                )
                
                # Ajouter un log de confirmation
                logger.debug(f"Processus bash démarré avec PID: {process.pid}")
                
                # Fonction pour lire la sortie en temps réel
                def read_output(pipe, is_error=False):
                    try:
                        while True:
                            line = pipe.readline()
                            if not line:
                                break
                            line = line.strip()
                            if line:
                                logger.debug(f"Log reçu: {line}")
                                # Ajouter directement le log dans l'interface
                                level = 'error' if is_error else 'info'
                                # Extract the actual message without timestamp and level
                                msg_parts = line.split('] ')
                                if len(msg_parts) >= 3:  # Format is [timestamp] [level] message
                                    actual_message = msg_parts[2]
                                    # Extract the level from the original message
                                    level_part = msg_parts[1].strip('[]').lower()
                                    if level_part in ['debug', 'info', 'warning', 'error', 'success']:
                                        level = level_part
                                else:
                                    actual_message = line
                                    
                                # Détecter les messages de succès
                                if any(success_term in actual_message.lower() for success_term in ['terminé avec succès', 'réussi', 'test bash test']):
                                    level = 'success'
                                
                                # Ajouter le log de manière asynchrone
                                async def _add_log_line():
                                    await self.add_log(actual_message, level)
                                
                                # Exécuter la fonction dans le thread principal
                                self.app.call_from_thread(lambda: self.app.run_worker(_add_log_line()))
                                # Vérifier la progression
                                if "Progression :" in line:
                                    try:
                                        progress_str = line.split("Progression :")[1].split("%")[0].strip()
                                        progress = float(progress_str)
                                        sync_progress(progress, f"Étape {progress}%")
                                    except Exception as e:
                                        logger.error(f"Erreur parsing progression: {str(e)}")
                    except Exception as e:
                        logger.error(f"Erreur lors de la lecture des logs: {str(e)}")
                
                # Créer des threads pour lire stdout et stderr
                stdout_thread = threading.Thread(target=read_output, args=(process.stdout,))
                stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
                
                # Démarrer les threads
                stdout_thread.start()
                stderr_thread.start()
                
                # Attendre la fin du processus
                exit_code = process.wait()
                
                # Attendre la fin des threads de lecture
                stdout_thread.join()
                stderr_thread.join()
                
                # Retourner le résultat
                result = (exit_code == 0, "Exécution terminée" if exit_code == 0 else f"Erreur (code {exit_code})")
                
            else:
                # Exécuter le plugin Python avec les callbacks
                try:
                    result = main_module.execute_plugin(
                        config,
                        progress_callback=sync_progress,
                        status_callback=sync_status
                    )
                except TypeError as e:
                    if 'unexpected keyword argument' in str(e):
                        try:
                            result = main_module.execute_plugin(
                                config,
                                progress_callback=sync_progress
                            )
                        except TypeError:
                            result = main_module.execute_plugin(config)
                    else:
                        raise
            
            # Logger le résultat brut pour debug
            logger.debug(f"Résultat brut du plugin {plugin_id}: {result} (type: {type(result)})")
            
            # Valider et normaliser le résultat
            if result is None:
                logger.error(f"Plugin {plugin_id}: aucun résultat retourné")
                result_queue.put((False, 'Le plugin n\'a retourné aucun résultat'))
            elif isinstance(result, bool):
                logger.debug(f"Plugin {plugin_id}: résultat booléen {result}")
                result_queue.put((result, 'OK' if result else 'Echec'))
            elif isinstance(result, dict):
                success = result.get('success', False)
                message = result.get('message', 'OK' if success else 'Echec')
                logger.debug(f"Plugin {plugin_id}: résultat dict - success: {success}, message: {message}")
                result_queue.put((success, message))
            elif isinstance(result, tuple) and len(result) >= 2:
                success, message = result[0], result[1]
                logger.debug(f"Plugin {plugin_id}: résultat tuple - success: {success}, message: {message}")
                result_queue.put((bool(success), str(message)))
            else:
                logger.warning(f"Plugin {plugin_id}: format de résultat inattendu, conversion en bool/str")
                result_queue.put((bool(result), str(result)))
        except Exception as e:
            logger.error(f"Erreur dans le thread du plugin {plugin_id}: {str(e)}")
            result_queue.put((False, str(e)))

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
        """Mise à jour du plugin en cours"""
        current_plugin = self.query_one("#current-plugin")
        if current_plugin:
            current_plugin.update(f"Plugin en cours : {plugin_name}")

    async def add_log(self, message: str, level: str = 'info'):
        """Ajout d'un message dans les logs avec formatage amélioré"""
        try:
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
                
                # Faire défiler vers le bas
                logs_content = self.query_one("#logs-content")
                logs_content.scroll_end(animate=False)
                
                # Forcer l'affichage des logs et le défilement
                logs_container = self.query_one("#logs-container")
                if logs_container:
                    logs_container.remove_class("hidden")
                    # Forcer le défilement immédiat sans animation
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

    def __init__(self, plugins_config: dict = None):
        """Initialise l'écran"""
        super().__init__()
        self.plugins_config = plugins_config

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        yield ExecutionWidget(self.plugins_config)
