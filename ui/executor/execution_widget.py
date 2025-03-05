"""
Widget principal d'exécution de plugins.
"""

import asyncio
import threading
from typing import Dict

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Label, ProgressBar, Static, Footer, Header
from textual.reactive import reactive
from textual.binding import Binding

from .plugin_container import PluginContainer
from .local_executor import LocalExecutor
from .ssh_executor import SSHExecutor
from .logger_utils import LoggerUtils
from ..choice_management.plugin_utils import get_plugin_folder_name
from ..logging import get_logger

logger = get_logger('execution_widget')

class ExecutionWidget(Container):
    """Widget principal d'exécution des plugins"""

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
                plugin_name = config.get('plugin_name', folder_name)
                plugin_icon = config.get('icon', '📦')
                plugin_show_name = config.get('name', plugin_name)
                container = PluginContainer(plugin_id, plugin_name, plugin_show_name, plugin_icon)
                self.plugins[plugin_id] = container
                yield container

        # Zone des logs
        with Horizontal(id="logs"):
            with ScrollableContainer(id="logs-container"):
                yield Static("", id="logs-text")
        with Horizontal(id="button-container"):
            yield Button("Retour", id="back-button", variant="error")
            yield Checkbox("Continuer en cas d'erreur", id="continue-on-error", value=True)
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
                from ..config import PluginConfig

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
            await LoggerUtils.clear_logs(self)

            # Exécuter les plugins
            await self.run_plugins()

        except Exception as e:
            logger.error(f"Erreur lors du démarrage de l'exécution : {str(e)}")
            await LoggerUtils.add_log(self, f"Erreur lors du démarrage : {str(e)}", 'error')
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

                    # Exécuter le plugin selon le mode (local ou SSH)
                    plugin_config = config.get("config", {})
                    if plugin_config.get("remote_execution", False):
                        # Exécution SSH
                        await SSHExecutor.run_ssh_plugin(
                            self, plugin_id, plugin_widget, config['name'],
                            plugin_config, executed, total_plugins, result_queue
                        )
                    else:
                        # Exécution locale
                        await LocalExecutor.run_local_plugin(
                            self, plugin_id, plugin_widget, config['name'],
                            plugin_config, executed, total_plugins, result_queue
                        )

                    # Récupérer le résultat
                    success, message = await result_queue.get()

                    # Récupérer le nom du dossier du plugin pour les logs
                    plugin_folder = get_plugin_folder_name(plugin_id)

                    if success:
                        plugin_widget.set_status('success')
                    else:
                        plugin_widget.set_status('error', message)
                        if not self.continue_on_error:
                            logger.error(f"Arrêt de l'exécution suite à l'erreur du plugin {plugin_folder}")
                            return
                        else:
                            logger.warning(f"Continuation après erreur du plugin {plugin_folder} (option activée)")
                            await LoggerUtils.add_log(self, f"Continuation après erreur (option activée)", 'warning')

                    executed += 1
                    # Mise à jour de la progression globale
                    self.update_global_progress(executed / total_plugins)

                except Exception as e:
                    # Récupérer le nom du dossier du plugin pour les logs
                    plugin_folder = get_plugin_folder_name(plugin_id)

                    logger.error(f"Erreur inattendue dans le plugin {plugin_folder}: {str(e)}")
                    plugin_widget.set_status('error', str(e))
                    await LoggerUtils.add_log(self, f"Erreur inattendue: {str(e)}", 'error')
                    if not self.continue_on_error:
                        return
                    else:
                        logger.info(f"Continuation après erreur du plugin {plugin_folder} (option activée)")
                        await LoggerUtils.add_log(self, f"Continuation après erreur (option activée)", 'warning')
                        executed += 1
                        self.update_global_progress(executed / total_plugins)

            # Mise à jour finale
            self.update_global_progress(1.0)
            self.set_current_plugin("Terminé")
            await LoggerUtils.add_log(self, "Exécution terminée avec succès")

        except Exception as e:
            logger.error(f"Erreur lors de l'exécution des plugins : {str(e)}")
            await LoggerUtils.add_log(self, f"Erreur lors de l'exécution : {str(e)}", 'error')

    def update_global_progress(self, progress: float):
        """Mise à jour de la progression globale"""
        progress_bar = self.query_one("#global-progress")
        if progress_bar:
            progress_bar.update(total=100.0, progress=progress * 100)

    def set_current_plugin(self, plugin_name: str):
        """Met à jour l'affichage du plugin courant et scrolle vers lui"""
        # Trouver le plugin en cours et scroller vers lui
        plugins_list = self.query_one("#plugins-list")
        if plugins_list:
            for plugin_id, plugin in self.plugins.items():
                if plugin.plugin_name == plugin_name:
                    # Scroller vers le plugin
                    plugin.scroll_visible()
                    break

    def action_toggle_logs(self) -> None:
        """Afficher/Masquer les logs"""
        LoggerUtils.toggle_logs(self)