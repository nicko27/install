from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Button

from .plugin_utils import load_plugin_info
from ..logging import get_logger

logger = get_logger('plugin_list_item')

class PluginListItem(Horizontal):
    """Représente un élément dans la liste des plugins sélectionnés"""

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