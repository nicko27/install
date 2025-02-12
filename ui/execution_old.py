import os
import logging
import importlib.util
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Callable

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

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Label, ProgressBar, Static, Footer
from textual.reactive import reactive
from textual import events

class PluginContainer(Container):
    """Conteneur pour afficher l'état et la progression d'un plugin"""
    
    def __init__(self, plugin_id: str, plugin_name: str):
        super().__init__(id=f"plugin-{plugin_id}")
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.classes = "plugin-container waiting"

    def compose(self) -> ComposeResult:
        """Création des widgets du conteneur"""
        with Horizontal(classes="plugin-header"):
            yield Label(self.plugin_name, classes="plugin-name")
            yield Label("En attente", classes="plugin-status")
        
        with Container(classes="plugin-progress-container"):
            yield ProgressBar(classes="plugin-progress")
            yield Label("", classes="plugin-step")

    def update_progress(self, progress: float, step: str = None):
        """Mise à jour de la progression du plugin"""
        self.query_one(ProgressBar).update(progress=progress)
        if step:
            self.query_one(".plugin-step").update(f"Étape en cours : {step}")

    def set_status(self, status: str, message: str = None):
        """Mise à jour du statut du plugin"""
        status_map = {
            'waiting': 'En attente',
            'running': 'En cours',
            'success': 'Terminé',
            'error': 'Erreur'
        }
        
        # Mise à jour des classes CSS
        self.remove_class("waiting", "running", "success", "error")
        self.add_class(status)
        
        # Mise à jour du texte de statut
        status_text = status_map.get(status, status)
        if message:
            status_text = f"{status_text} - {message}"
        self.query_one(".plugin-status").update(status_text)

class ExecutionScreen(Screen):
    """Écran d'exécution des plugins"""

    # Déclaration des variables d'instance avec reactive
    is_running = reactive(False)

    def __init__(self, plugins_config: dict):
        super().__init__()
        self.plugins_config = plugins_config
        self.plugins = {}

    def _maybe_clear_tooltip(self) -> None:
        """Nettoie les tooltips si nécessaire"""
        # Cette méthode est appelée par Textual pour gérer les tooltips
        # On laisse la gestion par défaut de Textual
        return super()._maybe_clear_tooltip()

    async def _on_mount(self, event: events.Mount) -> None:
        """Gère le montage de l'écran"""
        # Initialiser l'interface
        await self.update_global_progress(0)
        await self.set_current_plugin("aucun")

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        with Container(id="execution-container"):
            # Section supérieure
            with Container(id="header-section"):
                with Horizontal():
                    yield Button("Démarrer", id="start-button", variant="primary")
                    yield Label("Progression globale :", classes="progress-label")
                    yield ProgressBar(id="global-progress", total=100)
                    yield Label("0", id="progress-text")
                    yield Label("%", classes="progress-unit")
                yield Label("Plugin en cours : aucun", id="current-plugin")
            
            # Section des plugins
            with ScrollableContainer(id="plugins-section"):
                for plugin_id, config in self.plugins_config.items():
                    plugin_name = f"{config.get('test_name', 'Plugin')} #{plugin_id.split('_')[-1]}"
                    plugin = PluginContainer(plugin_id, plugin_name)
                    self.plugins[plugin_id] = plugin
                    yield plugin
            
            # Section des logs
            with Container(id="footer-section"):
                with Container(id="logs-header"):
                    yield Label("Logs", id="logs-title")
                with ScrollableContainer(id="logs-content"):
                    yield Label("", id="logs-text", expand=True)

        yield Footer()

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
            await self.update_global_progress(0)
            await self.set_current_plugin("aucun")
            await self.clear_logs()
            
            await self.run_plugins()

        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution : {str(e)}")
            await self.add_log(f"Erreur lors du démarrage : {str(e)}", 'error')
            # Réactiver le bouton en cas d'erreur
            start_button.disabled = False
            logger.debug("Bouton réactivé après erreur")
        finally:
            self.is_running = False

    async def clear_logs(self):
        """Effacement des logs"""
        logs_widget = self.query_one("#logs-text")
        if logs_widget:
            logs_widget.update("")

    async def update_global_progress(self, progress: float):
        """Mise à jour de la progression globale"""
        self.query_one("#global-progress").update(progress=progress)

    async def set_current_plugin(self, plugin_name: str):
        """Mise à jour du plugin en cours"""
        self.query_one("#current-plugin").update(f"Plugin en cours : {plugin_name}")

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
        
    def update_ui(self, func, *args):
        """Mise à jour de l'interface depuis un thread ou le thread principal"""
        try:
            import threading
            if threading.current_thread() is threading.main_thread():
                # Si nous sommes dans le thread principal, appeler directement
                func(*args)
            else:
                # Si nous sommes dans un thread secondaire, utiliser call_from_thread
                self.app.call_from_thread(func, *args)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'interface : {str(e)}")

    async def run_plugins(self):
        """Exécuter les plugins de façon séquentielle"""
        try:
            total_plugins = len(self.plugins)
            logger.debug(f"Démarrage de l'exécution de {total_plugins} plugins")
            executed = 0
            # Plus besoin de ThreadPoolExecutor car on utilise run_worker

            for plugin_id, plugin_widget in self.plugins.items():
                try:
                    # Extraire le nom du plugin et son ID
                    plugin_name = plugin_widget.plugin_name
                    config = self.plugins_config[plugin_id]
                    logger.debug(f"Démarrage du plugin {plugin_name} ({plugin_id}) avec config : {config}")

                    # Mise à jour de l'interface
                    await self.set_current_plugin(plugin_name)
                    plugin_widget.set_status('running')
                    
                    # Charger et exécuter le plugin
                    try:
                        # Charger le module du plugin
                        base_type = plugin_id.split('_')[0] + '_' + plugin_id.split('_')[1]
                        test_type = base_type + '_test'
                        
                        # Essayer d'abord avec _test
                        plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", test_type)
                        exec_path = os.path.join(plugin_dir, "exec.py")
                        logger.debug(f"Tentative de chargement du plugin {plugin_name} depuis {exec_path}")
                        
                        if not os.path.exists(exec_path):
                            logger.debug(f"Fichier {exec_path} non trouvé, essai sans _test")
                            # Si pas trouvé, essayer sans _test
                            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins", base_type)
                            exec_path = os.path.join(plugin_dir, "exec.py")
                            logger.debug(f"Tentative de chargement du plugin {plugin_name} depuis {exec_path}")
                            
                            if not os.path.exists(exec_path):
                                error_msg = f"Le fichier exec.py n'existe pas pour le plugin {plugin_name} (essayé dans {test_type} et {base_type})"
                                logger.debug(f"Fichier {exec_path} non trouvé, abandon du chargement")
                                raise ImportError(error_msg)

                        spec = importlib.util.spec_from_file_location("exec", exec_path)
                        if not spec or not spec.loader:
                            error_msg = f"Impossible de charger le plugin {plugin_name}"
                            raise ImportError(error_msg)

                        plugin_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(plugin_module)
                        logger.debug(f"Module {plugin_name} chargé avec succès")

                        # Exécuter le plugin dans un worker
                        logger.debug(f"Soumission du plugin {plugin_name} au worker")
                        try:
                            # Définir les callbacks dans une closure pour garder le contexte
                            def execute_with_callbacks():
                                def wrapped_progress(progress: float, step: str = None):
                                    self.app.call_from_thread(plugin_widget.update_progress, progress, step)
                                    total_progress = (executed * 100 + progress) / total_plugins
                                    self.app.call_from_thread(self.update_global_progress, total_progress)

                                def wrapped_status(status: str, message: str = None):
                                    if message:
                                        self.app.call_from_thread(self.add_log, f"{plugin_name}: {message}")
                                    self.app.call_from_thread(plugin_widget.set_status, status, message)

                                return plugin_module.execute_plugin(config, wrapped_progress, wrapped_status)

                            # Exécuter le plugin et attendre son résultat
                            result = await self.app.run_worker(
                                execute_with_callbacks,
                                thread=True,
                                group="plugin_execution",
                                name=f"plugin_{plugin_name}"
                            )
                            logger.debug(f"Résultat reçu pour le plugin {plugin_name}")

                            # Vérifier le résultat
                            if isinstance(result, tuple) and len(result) == 2:
                                success, message = result
                                status = 'success' if success else 'error'
                                plugin_widget.set_status(status, message)
                                log_level = 'info' if success else 'error'
                                self.add_log(f"Plugin {plugin_name} terminé avec {status} : {message}", log_level)
                            else:
                                plugin_widget.set_status('success', "Plugin terminé")
                                self.add_log(f"Plugin {plugin_name} terminé", 'info')
                        except Exception as e:
                            error_msg = f"Erreur lors de l'exécution de {plugin_name} : {str(e)}"
                            logger.error(error_msg)
                            plugin_widget.set_status('error', str(e))
                            self.add_log(error_msg, 'error')

                    except ImportError as e:
                        error_msg = f"Erreur de chargement du plugin {plugin_name} : {str(e)}"
                        logger.error(error_msg)
                        plugin_widget.set_status('error', str(e))
                        self.add_log(error_msg, 'error')
                    except Exception as e:
                        error_msg = f"Erreur d'exécution du plugin {plugin_name} : {str(e)}"
                        logger.error(error_msg)
                        plugin_widget.set_status('error', str(e))
                        self.add_log(error_msg, 'error')

                    executed += 1
                    logger.debug(f"Plugin {plugin_name} terminé. {executed}/{total_plugins} plugins exécutés")

                except Exception as e:
                    error_msg = f"Erreur inattendue avec le plugin {plugin_name} : {str(e)}"
                    logger.error(error_msg)
                    self.add_log(error_msg, 'error')
                    # S'assurer que le widget est marqué comme en erreur
                    plugin_widget.set_status('error', "Erreur inattendue")

            # Mise à jour finale
            self.update_global_progress(100)
            self.set_current_plugin("Terminé")

        except Exception as e:
            error_msg = f"Erreur générale lors de l'exécution des plugins : {str(e)}"
            logger.error(error_msg)
            self.add_log(error_msg, 'error')

        finally:
            # Réactiver le bouton uniquement si tous les plugins ont réussi
            start_button = self.query_one("#start-button")
            if start_button is not None:
                if all(plugin.classes.endswith('success') for plugin in self.plugins.values()):
                    logger.debug("Réactivation du bouton car tous les plugins ont réussi")
                    start_button.disabled = False
                else:
                    logger.debug("Le bouton reste désactivé car certains plugins ont échoué")
            else:
                logger.error("Bouton introuvable pour la réactivation")
