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

# Création d'une instance YAML unique pour tout le programme
yaml = YAML()

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

# Fonction pour charger les informations d'un plugin
def load_plugin_info(plugin_name: str, default_info=None) -> dict:
    """Charge les informations d'un plugin depuis son fichier settings.yml
    
    Args:
        plugin_name: Le nom du plugin
        default_info: Informations par défaut en cas d'erreur
        
    Returns:
        dict: Les informations du plugin
    """
    if default_info is None:
        default_info = {"name": plugin_name, "description": "No description available", "icon": "📦"}
        
    folder_name = get_plugin_folder_name(plugin_name)
    settings_path = os.path.join('plugins', folder_name, 'settings.yml')
    
    try:
        with open(settings_path, 'r') as f:
            return yaml.load(f)
    except Exception as e:
        logger.error(f"Error loading plugin {plugin_name}: {e}")
        return default_info

# Classe représentant une carte de plugin
class PluginCard(Static):
    """A widget to represent a single plugin"""
    selected = reactive(False)  # État réactif pour savoir si le plugin est sélectionné

    def __init__(self, plugin_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugin_name = plugin_name  # Nom du plugin
        self.plugin_info = load_plugin_info(plugin_name)  # Charger les informations du plugin

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
        plugin_info = load_plugin_info(self.plugin_name)
        multiple = plugin_info.get('multiple', False)  # Vérifier si le plugin peut être sélectionné plusieurs fois

        # Si le plugin est multiple et déjà sélectionné, on ajoute une nouvelle instance
        if multiple and self.selected:
            # Envoyer un message spécial pour ajouter une instance
            self.app.post_message(self.AddPluginInstance(self.plugin_name, self))
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
            
    class AddPluginInstance(Message):
        """Message spécifique pour ajouter une instance d'un plugin multiple"""
        def __init__(self, plugin_name: str, source: Widget):
            super().__init__()
            self.plugin_name = plugin_name
            self.source = source

# Classe représentant un élément de la liste des plugins sélectionnés
class PluginListItem(Horizontal):
    def __init__(self, plugin_data: tuple, index: int):
        super().__init__()
        self.plugin_name, self.instance_id = plugin_data  # Nom du plugin et ID d'instance
        self.index = index  # Index de l'élément dans la liste
        self.plugin_info = load_plugin_info(self.plugin_name, {"name": self.plugin_name, "icon": "📦"})

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
            # Extraire les informations du bouton
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
        """Handle button presses in the main application"""
        if event.button.id == "configure_selected":
            await self.action_configure_selected()  # Action pour configurer les plugins sélectionnés
        elif event.button.id == "quit":
            self.exit()  # Quitter l'application

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
            logger.error(f"Error discovering plugins: {e}")
            return []

    def on_plugin_card_plugin_selection_changed(self, message: PluginCard.PluginSelectionChanged) -> None:
        """Handle regular plugin selection changes (first selection or deselection)"""
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
        else:
            # Désélection : on retire toutes les instances du plugin
            self.selected_plugins = [(p, i) for p, i in self.selected_plugins if p != message.plugin_name]
            # Réinitialiser le compteur d'instances
            if message.plugin_name in self.instance_counter:
                del self.instance_counter[message.plugin_name]

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
        
        # Mettre à jour le panneau
        panel = self.query_one("#selected-plugins", SelectedPluginsPanel)
        panel.update_plugins(self.selected_plugins)
        
        # Effet visuel pour indiquer que l'instance a été ajoutée
        # Nous utilisons simplement l'ajout de classe sans essayer de la retirer automatiquement
        # Cette solution est la plus compatible avec toutes les versions de Textual
        message.source.add_class("instance-added")
        
        # Note: Si vous souhaitez ajouter un effet temporaire, vous devrez définir
        # une règle CSS qui fait disparaître l'effet après un court délai, par exemple:
        # .instance-added {
        #    animation: flash 0.3s forwards;
        # }
        # @keyframes flash {
        #    0% { background-color: highlight; }
        #    100% { background-color: transparent; }
        # }

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