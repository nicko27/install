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
        # Vérifier si le plugin est multiple
        settings_path = os.path.join('plugins', self.plugin_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
                multiple = settings.get('multiple', False)
        except Exception:
            multiple = False

        # Si le plugin est multiple et déjà sélectionné, on ajoute une nouvelle instance
        if multiple and self.selected:
            self.app.post_message(self.PluginSelectionChanged(self.plugin_name, True, self))
        else:
            # Sinon, on bascule l'état et on envoie le message approprié
            self.selected = not self.selected
            self.update_styles()
            self.app.post_message(self.PluginSelectionChanged(self.plugin_name, self.selected, self))

    def update_styles(self):
        """Update card styles based on selection state"""
        if self.selected:
            self.add_class('selected')
        else:
            self.remove_class('selected')

    class PluginSelectionChanged(Message):
        """Message sent when plugin selection changes"""
        def __init__(self, plugin_name: str, selected: bool, source: Widget):
            super().__init__()
            self.plugin_name = plugin_name
            self.selected = selected
            self.source = source


class PluginListItem(Horizontal):
    def __init__(self, plugin_data: tuple, index: int):
        super().__init__()
        self.plugin_name, self.instance_id = plugin_data
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
        yield Label(f"{self.index}. {icon} {name} ({self.instance_id})", classes="plugin-list-name")
        yield Button("❌", id=f"remove_{self.plugin_name}_{self.instance_id}", variant="error", classes="remove-button")

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
        self.selected_plugins = plugins
        container = self.query_one("#selected-plugins-list", Container)
        container.remove_children()
        
        if not plugins:
            container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))
            return

        for idx, plugin in enumerate(plugins, 1):
            item = PluginListItem(plugin, idx)
            container.mount(item)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the selected plugins panel"""
        if event.button.id == "configure_selected":
            await self.app.action_configure_selected()
        elif event.button.id and event.button.id.startswith('remove_'):
            # Extraire l'ID d'instance (dernier élément après le dernier _)
            parts = event.button.id.replace('remove_', '').split('_')
            instance_id = int(parts[-1])
            # Le nom du plugin est tout ce qui est entre 'remove_' et le dernier _
            plugin_name = '_'.join(parts[:-1])
            
            # Retirer l'instance spécifique de la liste
            self.app.selected_plugins = [(p, i) for p, i in self.app.selected_plugins if not (p == plugin_name and i == instance_id)]
            
            # Mettre à jour l'affichage
            self.update_plugins(self.app.selected_plugins)
            
            # Si c'était la dernière instance du plugin, on peut mettre à jour la carte
            if not any(p == plugin_name for p, _ in self.app.selected_plugins):
                for card in self.app.query(PluginCard):
                    if card.plugin_name == plugin_name:
                        card.selected = False
                        card.update_styles()
                        self.app.post_message(card.PluginSelectionChanged(plugin_name, False, card))


class Choice(App):
    BINDINGS = [
        ("escape", "quit", "Quitter"),

    ]

    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/choice.css")
    
    def __init__(self):
        super().__init__()
        self.selected_plugins = []  # Cette liste contiendra maintenant des tuples (plugin_name, instance_id)
        self.instance_counter = {}  # Pour suivre le nombre d'instances de chaque plugin

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
        # Charger les settings du plugin pour vérifier s'il peut être sélectionné plusieurs fois
        settings_path = os.path.join('plugins', message.plugin_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
                multiple = settings.get('multiple', False)
        except Exception:
            multiple = False

        # Si le message indique une sélection
        if message.selected:
            # Si c'est un plugin multiple ou pas encore sélectionné
            if multiple or not any(p[0] == message.plugin_name for p in self.selected_plugins):
                # Incrémenter le compteur d'instances pour ce plugin
                if message.plugin_name not in self.instance_counter:
                    self.instance_counter[message.plugin_name] = 0
                self.instance_counter[message.plugin_name] += 1
                
                # Ajouter le plugin avec son ID d'instance
                instance_id = self.instance_counter[message.plugin_name]
                self.selected_plugins.append((message.plugin_name, instance_id))
            else:
                # Si le plugin n'est pas multiple et déjà sélectionné, on annule la sélection
                message.source.selected = False
                message.source.update_styles()
        else:
            # Désélection : on retire toutes les instances du plugin
            self.selected_plugins = [(p, i) for p, i in self.selected_plugins if p != message.plugin_name]

        # Update the panel
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

    async def action_configure_selected(self) -> None:
        """Configure selected plugins"""
        from ui.config import PluginConfig
        
        if not self.selected_plugins:
            self.notify("Aucun plugin sélectionné", severity="error")
            return
            
        # Passer les plugins avec leurs IDs d'instance
        plugin_instances = [(p[0], p[1]) for p in self.selected_plugins]
        
        # Lancer l'interface de configuration
        config_app = PluginConfig(plugin_instances)
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
