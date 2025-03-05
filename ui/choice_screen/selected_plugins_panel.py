from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Label, Button, Static

from .plugin_list_item import PluginListItem
from .plugin_card import PluginCard
from ..utils.logging import get_logger

logger = get_logger('selected_plugins_panel')

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