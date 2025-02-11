from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Static
from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
import os
import yaml


class PluginCard(Static):
    """A widget to represent a single plugin"""
    selected = reactive(False)

    def __init__(self, plugin_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugin_name = plugin_name
        self.plugin_info = self._load_plugin_info()

    def _load_plugin_info(self) -> dict:
        """Load plugin information from settings.yml"""
        settings_path = os.path.join('plugins', self.plugin_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading plugin {self.plugin_name}: {e}")
            return {"name": self.plugin_name, "description": "No description available"}

    def compose(self) -> ComposeResult:
        """Compose the plugin card"""
        name = self.plugin_info.get('name', 'Unnamed Plugin')
        description = self.plugin_info.get('description', 'No description')
        icon = self.plugin_info.get('icon', '📦')
        
        yield Label(f"{icon} {name}", classes="plugin-name")
        yield Label(description, classes="plugin-description")

    def on_click(self) -> None:
        """Handle click to select/deselect plugin"""
        self.selected = not self.selected
        self.update_styles()
        self.app.post_message(self.PluginSelectionChanged(self.plugin_name, self.selected))

    def update_styles(self):
        """Update card styles based on selection state"""
        if self.selected:
            self.add_class('selected')
        else:
            self.remove_class('selected')

    class PluginSelectionChanged(Message):
        """Message sent when plugin selection changes"""
        def __init__(self, plugin_name: str, selected: bool):
            super().__init__()
            self.plugin_name = plugin_name
            self.selected = selected


class PluginListItem(Horizontal):
    def __init__(self, plugin_name: str, index: int):
        super().__init__()
        self.plugin_name = plugin_name
        self.index = index
        self.plugin_info = self._load_plugin_info()

    def _load_plugin_info(self) -> dict:
        settings_path = os.path.join('plugins', self.plugin_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception:
            return {"name": self.plugin_name, "icon": "📦"}

    def compose(self) -> ComposeResult:
        name = self.plugin_info.get('name', self.plugin_name)
        icon = self.plugin_info.get('icon', '📦')
        yield Label(f"{self.index}. {icon} {name}", classes="plugin-list-name")
        yield Button("❌", id=f"remove_{self.index}", variant="error", classes="remove-button")

    def on_mount(self) -> None:
        self.styles.align_horizontal = "left"
        self.styles.align_vertical = "middle"
        self.styles.height = 3
        self.styles.margin = (0, 0, 1, 0)


class SelectedPluginsPanel(Static):
    """Panel to display selected plugins and their order"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_plugins = []

    def compose(self) -> ComposeResult:
        yield Label("Plugins sélectionnés", classes="panel-title")
        yield Container(id="selected-plugins-list")
        yield Button("Configurer", id="configure_selected", variant="primary")

    def update_plugins(self, plugins: list) -> None:
        """Update the display when selected plugins change"""
        # Mettre à jour l'affichage
        container = self.query_one("#selected-plugins-list", Container)
        container.remove_children()
        
        if not plugins:
            container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))
            return

        # Créer une nouvelle liste d'éléments avec les index mis à jour
        for idx, plugin in enumerate(plugins, 1):
            item = PluginListItem(plugin, idx)
            container.mount(item)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the selected plugins panel"""
        if event.button.id == "configure_selected":
            await self.app.action_configure_selected()
        elif event.button.id and event.button.id.startswith('remove_'):
            # Extraire l'index du plugin à supprimer
            remove_index = int(event.button.id.replace('remove_', '')) - 1
            
            # Vérifier si l'index est valide
            if 0 <= remove_index < len(self.app.selected_plugins):
                # Récupérer le nom du plugin à supprimer
                plugin_to_remove = self.app.selected_plugins[remove_index]
                
                # Supprimer le plugin à l'index spécifique
                del self.app.selected_plugins[remove_index]
                
                # Mettre à jour l'affichage
                self.update_plugins(self.app.selected_plugins)
                
                # Mettre à jour la carte du plugin supprimé si nécessaire
                for card in self.app.query(PluginCard):
                    if card.plugin_name == plugin_to_remove:
                        # Désélectionner uniquement si le plugin n'est plus dans la liste
                        if plugin_to_remove not in self.app.selected_plugins:
                            card.selected = False
                            card.update_styles()
                            self.app.post_message(card.PluginSelectionChanged(plugin_to_remove, False))
                        break


class Choice(App):
    BINDINGS = [
        ("escape", "quit", "Quitter"),

    ]

    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/choice.css")
    
    def __init__(self):
        super().__init__()
        self.selected_plugins = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-content"):
            with Vertical(id="plugins-column"):
                yield Label("Sélectionnez vos plugins", classes="section-title")
                with Horizontal(id="plugin-cards"):
                    yield from self.create_plugin_cards()
            yield SelectedPluginsPanel(id="selected-plugins")
        yield Footer()

    def create_plugin_cards(self) -> list:
        """Create plugin cards dynamically"""
        plugins_dir = 'plugins'
        try:
            return [
                PluginCard(plugin_name) 
                for plugin_name in os.listdir(plugins_dir) 
                if os.path.isdir(os.path.join(plugins_dir, plugin_name)) and 
                   os.path.exists(os.path.join(plugins_dir, plugin_name, 'settings.yml')) and
                   (os.path.exists(os.path.join(plugins_dir, plugin_name, 'exec.py')) or 
                    os.path.exists(os.path.join(plugins_dir, plugin_name, 'exec.bash')))
            ]
        except Exception as e:
            print(f"Error discovering plugins: {e}")
            return []

    def on_plugin_card_plugin_selection_changed(self, message: PluginCard.PluginSelectionChanged) -> None:
        """Handle plugin selection changes"""
        # Charger les infos du plugin
        settings_path = os.path.join('plugins', message.plugin_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                plugin_info = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading plugin info: {e}")
            plugin_info = {}
        
        # Vérifier si le plugin permet la sélection multiple
        allows_multiple = plugin_info.get('multiple', False)
        print(f"Plugin {message.plugin_name} allows multiple: {allows_multiple}")
        
        # Compter combien de fois ce plugin est déjà dans la liste
        plugin_count = self.selected_plugins.count(message.plugin_name)
        
        if message.selected or allows_multiple:
            # Pour les plugins multiples ou non encore présents
            if allows_multiple or plugin_count == 0:
                self.selected_plugins.append(message.plugin_name)
                print(f"Added plugin: {message.plugin_name}")
            else:
                # Pour les plugins non multiples déjà présents
                self.selected_plugins.remove(message.plugin_name)
                print(f"Removed plugin: {message.plugin_name}")
        else:
            # Retirer le plugin quand on clique pour désélectionner
            if message.plugin_name in self.selected_plugins:
                self.selected_plugins.remove(message.plugin_name)
                print(f"Removed plugin: {message.plugin_name}")

        print(f"Current selected plugins: {self.selected_plugins}")

        # Update the panel
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)
        
        # Mise à jour visuelle des cartes de plugins
        for card in self.query(PluginCard):
            # Mettre à jour l'état des cartes
            card.selected = card.plugin_name in self.selected_plugins
            card.update_styles()

    async def action_configure_selected(self) -> None:
        """Configure selected plugins"""
        from ui.config import PluginConfig
        
        if not self.selected_plugins:
            self.notify("Aucun plugin sélectionné", severity="error")
            return
            
        # Lancer l'interface de configuration
        config_app = PluginConfig(self.selected_plugins)
        result = await self.push_screen(config_app)
        
        if result:
            # Sauvegarder la configuration pour chaque plugin
            for plugin, config in result.items():
                config_dir = os.path.join('plugins', plugin, 'config')
                os.makedirs(config_dir, exist_ok=True)
                
                config_file = os.path.join(config_dir, 'config.yml')
                with open(config_file, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)

    def action_quit(self) -> None:
        """Quit the application"""
        self.exit()