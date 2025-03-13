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
from ..utils.messaging import Message, MessageType
from ..choice_screen.plugin_utils import get_plugin_folder_name
from ..utils.logging import get_logger

logger = get_logger('execution_widget')

class ExecutionWidget(Container):
    """Widget principal d'exécution des plugins"""

    # État d'exécution
    is_running = reactive(False)
    continue_on_error = reactive(False)
    show_logs = reactive(True)  # Logs visibles par défaut
    
    # Raccourcis clavier
    BINDINGS = [
        Binding("l", "toggle_logs", "Afficher/Masquer logs"),
    ]
    
    class ExecutionCompleted(Message):
        """Message indiquant que l'exécution est terminée"""
        pass
    
    def __init__(self, plugins_config: dict = None):
        """Initialise le widget avec la configuration des plugins"""
        super().__init__()
        self.plugins: Dict[str, PluginContainer] = {}
        self.plugins_config = plugins_config or {}
        self._current_plugin = None
        self._total_plugins = 0
        self._executed_plugins = 0
        self.report_manager = None  # Gestionnaire de rapports
        self.sequence_name = None   # Nom de la séquence en cours
        logger.debug(f"ExecutionWidget initialized with {len(self.plugins_config)} plugins: {list(self.plugins_config.keys())}")

    async def execute_plugin(self, plugin_id: str, config: dict) -> dict:
        """Exécute un plugin spécifique"""
        try:
            # Récupérer le nom du plugin depuis son dossier
            folder_name = get_plugin_folder_name(plugin_id)
            
            # Exécuter le plugin localement ou via SSH selon la configuration
            if config.get('ssh'):
                executor = SSHExecutor(config['ssh'])
            else:
                executor = LocalExecutor()
                
            # Exécuter le plugin
            success, output = await executor.execute_plugin(folder_name, config)
            
            return {
                'success': success,
                'output': output
            }
            
        except Exception as e:
            logger.error(f"Erreur exécution plugin {plugin_id}: {e}")
            return {
                'success': False,
                'output': str(e)
            }

    async def run_plugins(self):
        """Exécute les plugins de façon séquentielle"""
        try:
            total_plugins = len(self.plugins)
            logger.debug(f"Démarrage de l'exécution de {total_plugins} plugins")
            logger.debug(f"Plugins disponibles: {list(self.plugins.keys())}")
            logger.debug(f"Plugins config: {list(self.plugins_config.keys())}")
            executed = 0

            for plugin_id, plugin_widget in self.plugins.items():
                try:
                    logger.debug(f"Préparation de l'exécution de {plugin_id}")
                    config = self.plugins_config[plugin_id]
                    plugin_name = plugin_widget.plugin_name
                    self.set_current_plugin(plugin_name)
                    
                    # Initialiser la progression et le statut
                    plugin_widget.update_progress(0.0, "Démarrage...")
                    
                    # Exécuter le plugin
                    result = await self.execute_plugin(plugin_id, config)
                    success = result.get('success', False)
                    output = result.get('output', '')
                    
                    # Mettre à jour le statut du plugin
                    plugin_widget.set_status("succès" if success else "erreur")
                    plugin_widget.set_output(output)
                    plugin_widget.update_progress(100.0, "Terminé")
                    
                    # Ajouter au rapport si activé
                    if self.report_manager:
                        # Extraire l'ID d'instance du plugin_id (dernier nombre)
                        instance_id = int(plugin_id.split('_')[-1])
                        
                        self.report_manager.add_result(
                            plugin_name=plugin_name,
                            instance_id=instance_id,
                            success=success,
                            output=output,
                            sequence_name=self.sequence_name
                        )
                    
                    executed += 1
                    self.update_global_progress(executed / total_plugins * 100)
                    
                    # En cas d'erreur, vérifier si on continue
                    if not success and not self.continue_on_error:
                        logger.warning(f"Arrêt de l'exécution après erreur sur {plugin_name}")
                        break
                        
                except Exception as e:
                    error_msg = f"Erreur lors de l'exécution de {plugin_id}: {str(e)}"
                    logger.error(error_msg)
                    plugin_widget.set_status("erreur")
                    plugin_widget.set_output(error_msg)
                    plugin_widget.update_progress(100.0, "Erreur")
                    
                    # Ajouter l'erreur au rapport
                    if self.report_manager:
                        instance_id = int(plugin_id.split('_')[-1])
                        self.report_manager.add_result(
                            plugin_name=plugin_name,
                            instance_id=instance_id,
                            success=False,
                            output=error_msg,
                            sequence_name=self.sequence_name
                        )
                    
                    if not self.continue_on_error:
                        break
            
            # Notifier la fin de l'exécution
            self.post_message(self.ExecutionCompleted())
            
        except Exception as e:
            logger.error(f"Erreur globale lors de l'exécution : {str(e)}")
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
            error_msg = Message(MessageType.ERROR, f"Erreur lors du démarrage : {str(e)}")
            await LoggerUtils.display_message(self, error_msg)
            
            # Réactiver le bouton en cas d'erreur
            start_button.disabled = False
            logger.debug("Bouton réactivé après erreur")
        finally:
            self.is_running = False
            # Réactiver le bouton
            start_button.disabled = False

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
        """Afficher/Masquer les logs (appelé par le raccourci clavier ou le bouton)"""
        LoggerUtils.toggle_logs(self)
        
    # Méthode pour compatibilité avec loggers existants
    async def display_log(self, message, level="info"):
        """Méthode pour compatibilité avec anciens systèmes de logs"""
        await LoggerUtils.add_log(self, message, level)

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        # En-tête
        yield Header(name="Exécution des plugins")

        # Liste des plugins
        with ScrollableContainer(id="plugins-list"):
            # Créer les conteneurs de plugins
            logger.debug(f"Création des conteneurs pour {len(self.plugins_config)} plugins")
            for plugin_id, config in self.plugins_config.items():
                # Récupérer le nom du plugin depuis son dossier
                folder_name = get_plugin_folder_name(plugin_id)
                plugin_name = config.get('plugin_name', folder_name)
                plugin_icon = config.get('icon', '📦')
                plugin_show_name = config.get('name', plugin_name)
                logger.debug(f"Création du conteneur pour {plugin_id}: nom={plugin_name}, affichage={plugin_show_name}")
                container = PluginContainer(plugin_id, plugin_name, plugin_show_name, plugin_icon)
                self.plugins[plugin_id] = container
                logger.debug(f"Conteneur ajouté pour {plugin_id}: {plugin_name}")
                yield container

        # Zone des logs (visible par défaut)
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

        # Initialiser l'état de la checkbox
        self.continue_on_error = True  # True par défaut

        # Initialiser l'affichage des logs
        await LoggerUtils.clear_logs(self)


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
                from ..config_screen.config_screen import PluginConfig

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
            elif button_id == "toggle-logs-button":
                # Afficher/Masquer les logs
                self.action_toggle_logs()
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