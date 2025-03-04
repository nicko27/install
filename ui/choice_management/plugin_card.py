from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.reactive import reactive
from textual.message import Message
from textual.widget import Widget

from .plugin_utils import load_plugin_info
from ..logging import get_logger

logger = get_logger('plugin_card')

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