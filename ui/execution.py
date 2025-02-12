"""
Screen d'exécution des plugins.
Gère l'interface et la logique d'exécution des plugins de manière séquentielle.
"""

import os
import logging
import importlib.util
import asyncio
from typing import Dict, Callable

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Label, ProgressBar, Static, Footer
from textual.reactive import reactive
from textual import events

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
            yield Label("En attente", classes="plugin-status")
            yield ProgressBar(classes="plugin-progress")

    def update_progress(self, progress: float, step: str = None):
        """Mise à jour de la progression du plugin"""
        self.query_one(ProgressBar).update(progress=progress)
        if step:
            self.query_one(".plugin-status").update(step)

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


class ExecutionScreen(Screen):
    """Écran d'exécution des plugins"""

    # État d'exécution
    is_running = reactive(False)

    def __init__(self, plugins_config: dict):
        """Initialise l'écran avec la configuration des plugins"""
        super().__init__()
        self.plugins_config = plugins_config
        self.plugins: Dict[str, PluginContainer] = {}

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        with Container(id="execution-container"):
            # En-tête
            yield Container(
                Label("Exécution des plugins", id="title"),
                Label("Plugin en cours : aucun", id="current-plugin"),
                ProgressBar(id="global-progress"),
                id="header"
            )
            
            # Liste des plugins
            with ScrollableContainer(id="plugins-list"):
                # Créer les conteneurs de plugins
                for plugin_id, config in self.plugins_config.items():
                    plugin_name = config.get('name', plugin_id)
                    container = PluginContainer(plugin_id, plugin_name)
                    self.plugins[plugin_id] = container
                    yield container

            # Zone des logs
            with Container(id="logs-container"):
                yield Label("Logs:", id="logs-title")
                yield Static("", id="logs-text")
                yield Button("Effacer", id="clear-logs", variant="default")

            # Bouton de démarrage
            yield Button("Démarrer", id="start-button", variant="primary")

        # Pied de page
        yield Footer()

    def on_mount(self) -> None:
        """Initialisation après le montage de l'écran"""
        # Laisser Textual gérer le cycle de vie
        self.update_global_progress(0)
        self.set_current_plugin("aucun")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gestion des clics sur les boutons"""
        button_id = event.button.id
        logger.debug(f"Clic sur le bouton {button_id}")

        if not button_id:
            logger.warning("Bouton sans identifiant détecté")
            return

        try:
            if button_id == "start-button":
                # Vérifier si le bouton n'est pas déjà désactivé
                if not event.button.disabled:
                    await self.start_execution()
            elif button_id == "clear-logs":
                await self.clear_logs()
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
                    # Extraire le nom du plugin et son ID
                    plugin_name = plugin_widget.plugin_name
                    config = self.plugins_config[plugin_id]
                    logger.debug(f"Démarrage du plugin {plugin_name} ({plugin_id})")

                    # Mise à jour de l'interface
                    self.set_current_plugin(plugin_name)
                    plugin_widget.set_status('running')
                    
                    # Charger et exécuter le plugin
                    try:
                        # Charger le module du plugin
                        base_type = plugin_id.split('_')[0] + '_' + plugin_id.split('_')[1]
                        test_type = base_type + '_test'
                        
                        # Essayer d'abord avec _test
                        plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", test_type)
                        exec_path = os.path.join(plugin_dir, "exec.py")
                        logger.debug(f"Tentative de chargement du plugin depuis {exec_path}")
                        
                        if not os.path.exists(exec_path):
                            # Si pas de _test, utiliser le plugin normal
                            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", base_type)
                            exec_path = os.path.join(plugin_dir, "exec.py")
                            logger.debug(f"Chargement du plugin depuis {exec_path}")
                        
                        # Charger le module
                        spec = importlib.util.spec_from_file_location("plugin_module", exec_path)
                        if not spec or not spec.loader:
                            raise ImportError(f"Impossible de charger le plugin depuis {exec_path}")
                            
                        main_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(main_module)
                        
                        # Préparer les callbacks
                        def wrapped_progress(progress: float, step: str = None):
                            """Wrapper pour le callback de progression"""
                            plugin_widget.update_progress(progress, step)
                            # Mettre à jour la progression globale
                            global_progress = (executed + progress) / total_plugins
                            asyncio.create_task(self.update_global_progress(global_progress))

                        def wrapped_status(status: str, message: str = None):
                            """Wrapper pour le callback de statut"""
                            plugin_widget.set_status(status, message)
                            if message:
                                asyncio.create_task(self.add_log(f"[{plugin_name}] {message}"))

                        # Exécuter le plugin
                        result = main_module.execute_plugin(
                            config,
                            progress_callback=wrapped_progress,
                            status_callback=wrapped_status
                        )
                        
                        # Traiter le résultat
                        if isinstance(result, tuple):
                            success, message = result
                        else:
                            success, message = result, None
                            
                        if success:
                            plugin_widget.set_status('success', message)
                            await self.add_log(f"Plugin {plugin_name} terminé avec succès")
                        else:
                            plugin_widget.set_status('error', message)
                            await self.add_log(f"Erreur dans le plugin {plugin_name}: {message}", 'error')
                            return
                            
                    except Exception as e:
                        logger.error(f"Erreur lors de l'exécution du plugin {plugin_name}: {str(e)}")
                        plugin_widget.set_status('error', str(e))
                        await self.add_log(f"Erreur dans le plugin {plugin_name}: {str(e)}", 'error')
                        return
                        
                    executed += 1
                    
                except Exception as e:
                    logger.error(f"Erreur inattendue dans le plugin {plugin_id}: {str(e)}")
                    await self.add_log(f"Erreur inattendue: {str(e)}", 'error')
                    return

            # Mise à jour finale
            self.update_global_progress(1.0)
            self.set_current_plugin("Terminé")
            await self.add_log("Exécution terminée avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'exécution des plugins : {str(e)}")
            await self.add_log(f"Erreur lors de l'exécution : {str(e)}", 'error')

    async def clear_logs(self):
        """Effacement des logs"""
        logs_widget = self.query_one("#logs-text")
        if logs_widget:
            logs_widget.update("")

    def update_global_progress(self, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = self.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(progress=progress)

    def set_current_plugin(self, plugin_name: str):
        """Mise à jour du plugin en cours"""
        current_plugin = self.query_one("#current-plugin")
        if current_plugin:
            current_plugin.update(f"Plugin en cours : {plugin_name}")

    async def add_log(self, message: str, level: str = 'info'):
        """Ajout d'un message dans les logs"""
        # Ajout dans l'interface
        logs = self.query_one("#logs-text")
        if logs:
            current_text = logs.renderable or ""
            logs.update(current_text + ("\n" if current_text else "") + message)
        
        # Ajout dans le fichier de logs
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)
