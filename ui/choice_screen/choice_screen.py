from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button

import os
from ..utils.logging import get_logger
from .plugin_card import PluginCard
from .selected_plugins_panel import SelectedPluginsPanel
from .plugin_utils import load_plugin_info

logger = get_logger('choice')

class Choice(App):
    """Application principale pour la sélection des plugins"""
    BINDINGS = [
        ("escape", "quit", "Quitter"),  # Raccourci pour quitter l'application
    ]

    CSS_PATH = "../styles/choice.tcss"  # Chemin vers le fichier CSS

    def __init__(self):
        super().__init__()
        logger.debug("Initializing Choice application")
        self.selected_plugins = []  # Cette liste contiendra des tuples (plugin_name, instance_id)
        self.instance_counter = {}  # Pour suivre le nombre d'instances de chaque plugin

    def compose(self) -> ComposeResult:
        yield Header()  # En-tête de l'application
        with Horizontal(id="main-content"):
            with Vertical(id="plugins-column"):
                yield Label("Sélectionnez vos plugins", classes="section-title")
                with ScrollableContainer(id="plugin-cards"):
                    yield from self.create_plugin_cards()
            yield SelectedPluginsPanel(id="selected-plugins")
        with Horizontal(id="button-container"):
            yield Button("Quitter", id="quit", variant="error")
            yield Button("Configurer", id="configure_selected", variant="primary")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the main application"""
        logger.debug(f"Button pressed: {event.button.id}")
        if event.button.id == "configure_selected":
            await self.action_configure_selected()
        elif event.button.id == "quit":
            self.exit()

    def create_plugin_cards(self) -> list:
        """Create plugin cards dynamically and sort by the 'name' field in settings.yml"""
        plugins_dir = 'plugins'
        plugin_cards = []
        try:
            logger.debug(f"Scanning plugins directory: {plugins_dir}")
            # Récupérer tous les plugins valides
            valid_plugins = []
            for plugin_name in os.listdir(plugins_dir):
                plugin_path = os.path.join(plugins_dir, plugin_name)
                settings_path = os.path.join(plugin_path, 'settings.yml')
                exec_py_path = os.path.join(plugin_path, 'exec.py')
                exec_bash_path = os.path.join(plugin_path, 'exec.bash')

                # Ajouter ces logs détaillés
                logger.debug(f"Checking plugin: {plugin_name}")
                logger.debug(f"  Path: {plugin_path} (exists: {os.path.isdir(plugin_path)})")
                logger.debug(f"  Settings: {settings_path} (exists: {os.path.exists(settings_path)})")
                logger.debug(f"  Exec Python: {exec_py_path} (exists: {os.path.exists(exec_py_path)})")
                logger.debug(f"  Exec Bash: {exec_bash_path} (exists: {os.path.exists(exec_bash_path)})")

                # Vérifier si le plugin est valide
                if (os.path.isdir(plugin_path) and
                    os.path.exists(settings_path) and
                    (os.path.exists(exec_py_path) or os.path.exists(exec_bash_path))):

                    # Ajouter ce log
                    logger.debug(f"  Plugin {plugin_name} is valid")

                    # Charger les informations du plugin
                    try:
                        plugin_info = load_plugin_info(plugin_name)
                        display_name = plugin_info.get('name', plugin_name)
                        valid_plugins.append((display_name, plugin_name))
                        logger.debug(f"  Added to valid plugins: {plugin_name} as {display_name}")
                    except Exception as e:
                        logger.error(f"  Error loading plugin info for {plugin_name}: {e}")
                else:
                    logger.debug(f"  Plugin {plugin_name} is NOT valid")

            # Trier par le nom affiché (qui est le champ 'name' de settings.yml)
            valid_plugins.sort(key=lambda x: x[0].lower())  # Tri insensible à la casse
            logger.debug(f"Valid plugins after sorting: {valid_plugins}")

            # Créer les cartes dans l'ordre trié
            for _, plugin_name in valid_plugins:
                logger.debug(f"Creating card for plugin: {plugin_name}")
                plugin_cards.append(PluginCard(plugin_name))

            return plugin_cards
        except Exception as e:
            logger.error(f"Error discovering plugins: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def on_plugin_card_plugin_selection_changed(self, message: PluginCard.PluginSelectionChanged) -> None:
        """Handle regular plugin selection changes (first selection or deselection)"""
        logger.debug(f"Selection changed for plugin: {message.plugin_name} to {message.selected}")
        if message.selected:
            # Vérifier si le plugin est multiple
            plugin_info = load_plugin_info(message.plugin_name)
            multiple = plugin_info.get('multiple', False)

            # Si le plugin n'est pas multiple et est déjà sélectionné, annuler la sélection
            if not multiple and any(p[0] == message.plugin_name for p in self.selected_plugins):
                message.source.selected = False
                message.source.update_styles()
                return

            # Sinon, ajouter une nouvelle instance
            if message.plugin_name not in self.instance_counter:
                self.instance_counter[message.plugin_name] = 0
            self.instance_counter[message.plugin_name] += 1

            instance_id = self.instance_counter[message.plugin_name]
            self.selected_plugins.append((message.plugin_name, instance_id))
            logger.debug(f"Added plugin instance: {message.plugin_name} (id: {instance_id})")
        else:
            # Désélection : on retire toutes les instances du plugin
            self.selected_plugins = [(p, i) for p, i in self.selected_plugins if p != message.plugin_name]
            # Réinitialiser le compteur d'instances
            if message.plugin_name in self.instance_counter:
                del self.instance_counter[message.plugin_name]
            logger.debug(f"Removed all instances of plugin: {message.plugin_name}")

        # Mettre à jour le panneau
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

    def on_plugin_card_add_plugin_instance(self, message: PluginCard.AddPluginInstance) -> None:
        """Gérer l'ajout d'une instance pour les plugins multiples"""
        # Incrémenter le compteur d'instances
        if message.plugin_name not in self.instance_counter:
            self.instance_counter[message.plugin_name] = 0
        self.instance_counter[message.plugin_name] += 1

        # Ajouter la nouvelle instance à la liste
        instance_id = self.instance_counter[message.plugin_name]
        self.selected_plugins.append((message.plugin_name, instance_id))
        logger.debug(f"Added additional instance of plugin: {message.plugin_name} (id: {instance_id})")

        # Mettre à jour le panneau
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

        # Effet visuel pour indiquer que l'instance a été ajoutée
        message.source.add_class("instance-added")

    async def action_configure_selected(self) -> None:
        """Configure selected plugins"""
        logger.debug("Starting action_configure_selected")

        try:
            from ui.config_screen.config_screen import PluginConfig

            if not self.selected_plugins:
                logger.debug("No plugins selected")
                self.notify("Aucun plugin sélectionné", severity="error")
                return

            logger.debug(f"Selected plugins: {self.selected_plugins}")

            # Créer l'écran de configuration pour tous les plugins sélectionnés
            logger.debug("Creating PluginConfig instance")
            config_screen = PluginConfig(self.selected_plugins)

            # S'assurer que current_config existe
            if not hasattr(config_screen, 'current_config'):
                logger.debug("Adding default current_config attribute")
                config_screen.current_config = {}

            # Afficher l'écran de configuration et attendre qu'il se termine
            logger.debug("Pushing config screen")
            await self.push_screen(config_screen)
            logger.debug("Config screen pushed successfully")

            # Récupérer la configuration avec sécurité
            config = getattr(config_screen, 'current_config', None)
            logger.debug(f"Config returned: {config is not None}")

            # Si une configuration a été définie, passer à l'écran d'exécution
            if config:
                logger.debug("Creating and pushing execution screen")
                execution_screen = ExecutionScreen(config)
                await self.push_screen(execution_screen)
                logger.debug("Execution screen pushed successfully")
            else:
                logger.debug("No configuration returned from config screen")

        except Exception as e:
            logger.error(f"Error in action_configure_selected: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.notify(f"Erreur: {str(e)}", severity="error")

    def action_quit(self) -> None:
        """Quit the application"""
        logger.debug("Quitting application")
        self.exit()