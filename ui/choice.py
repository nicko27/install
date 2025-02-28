from textwrap import wrap
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Static
from textual.widget import Widget
from textual.reactive import reactive
from textual.message import Message
import os
from ruamel.yaml import YAML

from .logging import get_logger
logger = get_logger('choice')

# Classe représentant une carte de plugin
class PluginCard(Static):
    """A widget to represent a single plugin"""
    selected = reactive(False)  # État réactif pour savoir si le plugin est sélectionné

    def __init__(self, plugin_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugin_name = plugin_name  # Nom du plugin
        self.plugin_info = self._load_plugin_info()  # Charger les informations du plugin

    def _load_plugin_info(self) -> dict:
        """Load plugin information from settings.yml"""
        folder_name = get_plugin_folder_name(self.plugin_name)  # Obtenir le nom du dossier du plugin
        settings_path = os.path.join('plugins', folder_name, 'settings.yml')  # Chemin vers le fichier settings.yml
        yaml = YAML()
        try:
            with open(settings_path, 'r') as f:
                return yaml.load(f)  # Charger les informations du plugin depuis le fichier YAML
        except Exception as e:
            print(f"Error loading plugin {self.plugin_name}: {e}")
            return {"name": self.plugin_name, "description": "No description available"}  # Retourner une description par défaut en cas d'erreur

    def compose(self) -> ComposeResult:
        """Compose the plugin card"""
        name = self.plugin_info.get('name', 'Unnamed Plugin')  # Nom du plugin
        description = self.plugin_info.get('description', 'No description')  # Description du plugin
        icon = self.plugin_info.get('icon', '📦')  # Icône du plugin
        
        yield Label(f"{icon}  {name}", classes="plugin-name")  # Afficher le nom et l'icône du plugin
        yield Label(description, classes="plugin-description")  # Afficher la description du plugin

    def on_click(self) -> None:
        """Handle click to select/deselect plugin"""
        # Vérifier si le plugin est multiple
        folder_name = get_plugin_folder_name(self.plugin_name)
        settings_path = os.path.join('plugins', folder_name, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.load(f)
                multiple = settings.get('multiple', False)  # Vérifier si le plugin peut être sélectionné plusieurs fois
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
            self.add_class('selected')  # Ajouter la classe CSS 'selected' si le plugin est sélectionné
        else:
            self.remove_class('selected')  # Retirer la classe CSS 'selected' si le plugin n'est pas sélectionné

    class PluginSelectionChanged(Message):
        """Message sent when plugin selection changes"""
        def __init__(self, plugin_name: str, selected: bool, source: Widget):
            super().__init__()
            self.plugin_name = plugin_name  # Nom du plugin
            self.selected = selected  # État de sélection
            self.source = source  # Source du message (la carte du plugin)

# Classe représentant un élément de la liste des plugins sélectionnés
class PluginListItem(Horizontal):
    def __init__(self, plugin_data: tuple, index: int):
        super().__init__()
        self.plugin_name, self.instance_id = plugin_data  # Nom du plugin et ID d'instance
        self.index = index  # Index de l'élément dans la liste
        self.plugin_info = self._load_plugin_info()  # Charger les informations du plugin

    def _load_plugin_info(self) -> dict:
        settings_path = os.path.join('plugins', self.plugin_name, 'settings.yml')  # Chemin vers le fichier settings.yml
        yaml = YAML()
        try:
            with open(settings_path, 'r') as f:
                return yaml.load(f)  # Charger les informations du plugin depuis le fichier YAML
        except Exception:
            return {"name": self.plugin_name, "icon": "📦"}  # Retourner des informations par défaut en cas d'erreur

    def compose(self) -> ComposeResult:
        name = self.plugin_info.get('name', self.plugin_name)  # Nom du plugin
        icon = self.plugin_info.get('icon', '📦')  # Icône du plugin
        yield Label(f"{self.index}. {icon}  {name}", classes="plugin-list-name")  # Afficher le nom et l'icône du plugin avec l'index
        yield Button("X", id=f"remove_{self.plugin_name}_{self.instance_id}", variant="error", classes="remove-button")  # Bouton pour retirer le plugin

    def on_mount(self) -> None:
        self.styles.align_horizontal = "left"  # Aligner horizontalement à gauche
        self.styles.align_vertical = "middle"  # Aligner verticalement au milieu
        self.styles.height = 3  # Hauteur de l'élément
        self.styles.margin = (0, 0, 1, 0)  # Marges de l'élément

# Classe représentant le panneau des plugins sélectionnés
class SelectedPluginsPanel(Static):
    """Panel to display selected plugins and their order"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_plugins = []  # Liste des plugins sélectionnés

    def compose(self) -> ComposeResult:
        yield Label("Plugins sélectionnés", classes="panel-title")  # Titre du panneau
        yield Container(id="selected-plugins-list")  # Conteneur pour la liste des plugins sélectionnés

    def update_plugins(self, plugins: list) -> None:
        """Update the display when selected plugins change"""
        self.selected_plugins = plugins  # Mettre à jour la liste des plugins sélectionnés
        container = self.query_one("#selected-plugins-list", Container)  # Rechercher le conteneur de la liste
        container.remove_children()  # Retirer tous les enfants du conteneur
        
        if not plugins:
            container.mount(Label("Aucun plugin sélectionné", classes="no-plugins"))  # Afficher un message si aucun plugin n'est sélectionné
            return

        for idx, plugin in enumerate(plugins, 1):
            item = PluginListItem(plugin, idx)  # Créer un élément de la liste pour chaque plugin
            container.mount(item)  # Ajouter l'élément au conteneur

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the selected plugins panel"""
        if event.button.id and event.button.id.startswith('remove_'):
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

# Fonction pour obtenir le nom du dossier d'un plugin
def get_plugin_folder_name(plugin_name: str) -> str:
    """Retourne le nom du dossier d'un plugin à partir de son nom.
    
    Args:
        plugin_name: Le nom du plugin (peut inclure l'ID d'instance)
        
    Returns:
        str: Le nom du dossier du plugin
    """
    # Extraire le nom de base du plugin (sans l'ID d'instance)
    base_name = plugin_name.split('_')[0] + '_' + plugin_name.split('_')[1]
    test_type = base_name + '_test'
    
    # Vérifier si la version test existe
    test_path = os.path.join('plugins', test_type)
    if os.path.exists(test_path):
        return test_type
    
    # Sinon retourner le nom de base
    return base_name

# Classe principale de l'application
class Choice(App):
    BINDINGS = [
        ("escape", "quit", "Quitter"),  # Raccourci pour quitter l'application
    ]

    CSS_PATH = "styles/choice.css"  # Chemin vers le fichier CSS
    
    def __init__(self):
        super().__init__()
        logger.debug("Initializing Choice application")
        self.selected_plugins = []  # Cette liste contiendra maintenant des tuples (plugin_name, instance_id)
        self.instance_counter = {}  # Pour suivre le nombre d'instances de chaque plugin

    def compose(self) -> ComposeResult:
        yield Header()  # En-tête de l'application
        with Horizontal(id="main-content"):
            with Vertical(id="plugins-column"):
                yield Label("Sélectionnez vos plugins", classes="section-title")  # Titre de la section des plugins
                with ScrollableContainer(id="plugin-cards"):
                    yield from self.create_plugin_cards()  # Créer dynamiquement les cartes de plugins
            yield SelectedPluginsPanel(id="selected-plugins")  # Panneau des plugins sélectionnés
        with Horizontal(id="button-container"):
            yield Button("Quitter", id="quit", variant="error")  # Bouton pour quitter l'application
            yield Button("Configurer", id="configure_selected", variant="primary")  # Bouton pour configurer les plugins sélectionnés

        yield Footer()  # Pied de page de l'application

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses in the selected plugins panel"""
        if event.button.id == "configure_selected":
            await self.app.action_configure_selected()  # Action pour configurer les plugins sélectionnés
        elif event.button.id == "quit":
            self.app.exit()  # Quitter l'application

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
        yaml = YAML()
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.load(f)
                multiple = settings.get('multiple', False)  # Vérifier si le plugin peut être sélectionné plusieurs fois
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

        # Mettre à jour le panneau
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)

    async def action_configure_selected(self) -> None:
        """Configure selected plugins"""
        from ui.config import PluginConfig
        from ui.execution import ExecutionScreen
        
        if not self.selected_plugins:
            self.notify("Aucun plugin sélectionné", severity="error")  # Notification si aucun plugin n'est sélectionné
            return
            
        # Créer l'écran de configuration pour tous les plugins sélectionnés
        config_screen = PluginConfig(self.selected_plugins)
        
        # Afficher l'écran de configuration et attendre qu'il se termine
        await self.push_screen(config_screen)
        
        # Récupérer la configuration depuis l'écran de configuration
        config = config_screen.current_config
        
        # Si une configuration a été définie, passer à l'écran d'exécution
        if config:
            execution_screen = ExecutionScreen(self.selected_plugins, config)
            await self.push_screen(execution_screen)

    def action_quit(self) -> None:
        """Quit the application"""
        self.exit()  # Quitter l'application
