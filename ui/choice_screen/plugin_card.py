from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual.reactive import reactive
from textual.message import Message
from textual.widget import Widget
from pathlib import Path
from ruamel.yaml import YAML

from .plugin_utils import load_plugin_info
from ..utils.logging import get_logger

logger = get_logger('plugin_card')
yaml = YAML()

class PluginCard(Static):
    """A widget to represent a single plugin"""
    selected = reactive(False)  # État réactif pour savoir si le plugin est sélectionné

    def __init__(self, plugin_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plugin_name = plugin_name  # Nom du plugin

        # Vérifier si c'est une séquence
        if plugin_name.startswith('__sequence__'):
            self.is_sequence = True
            self.sequence_file = plugin_name.replace('__sequence__', '')
            self.plugin_info = self._load_sequence_info(self.sequence_file)
        else:
            self.is_sequence = False
            self.plugin_info = load_plugin_info(plugin_name)  # Charger les informations du plugin

    def compose(self) -> ComposeResult:
        """Compose the plugin card"""
        name = self.plugin_info.get('name', 'Unnamed Plugin')  # Nom du plugin
        description = self.plugin_info.get('description', '')  # Description du plugin

        if self.is_sequence:
            icon = '⚙️'  # Icône d'engrenage pour les séquences
            yield Label(f"{icon}  {name}", classes="plugin-name sequence-name")  # Afficher le nom et l'icône de la séquence
            plugins_count = self.plugin_info.get('plugins_count', 0)
            if len(description)>0:
                yield Label(f"{description} ({plugins_count} plugins)", classes="plugin-description")  # Afficher la description et le nombre de plugins
        else:
            icon = self.plugin_info.get('icon', '📦')  # Icône du plugin

            # Vérifier si le plugin est utilisable plusieurs fois
            multiple = self.plugin_info.get('multiple', False)
            remote = self.plugin_info.get('remote_execution', False)


            # Ajouter une icône spécifique pour les plugins utilisables plusieurs fois
            if multiple:
                icon = f"{icon}  🔁"  # Ajouter l'icône de recyclage pour indiquer que le plugin est réutilisable
            if remote:
                icon = f"{icon} 🌐"

            yield Label(f"{icon}  {name}", classes="plugin-name")  # Afficher le nom et l'icône du plugin

            yield Label(description, classes="plugin-description")  # Afficher la description du plugin

    def on_click(self) -> None:
        """Handle click to select/deselect plugin"""
        # Si c'est une séquence, on la traite différemment
        if self.is_sequence:
            self.selected = not self.selected
            self.update_styles()
            self.app.post_message(self.PluginSelectionChanged(self.plugin_name, self.selected, self))
            return

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

    def _load_sequence_info(self, sequence_file: str) -> dict:
        """Charge les informations d'une séquence"""
        try:
            sequence_path = Path('sequences') / sequence_file
            if not sequence_path.exists():
                logger.error(f"Fichier de séquence non trouvé : {sequence_path}")
                return {'name': 'Séquence inconnue', 'description': 'Fichier non trouvé'}

            with open(sequence_path, 'r', encoding='utf-8') as f:
                sequence = yaml.load(f)

            if not isinstance(sequence, dict):
                return {'name': 'Séquence invalide', 'description': 'Format incorrect'}

            return {
                'name': sequence.get('name', sequence_file),
                'description': sequence.get('description', 'Aucune description'),
                'plugins_count': len(sequence.get('plugins', []))
            }
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la séquence {sequence_file}: {e}")
            return {'name': 'Erreur', 'description': f'Erreur: {str(e)}'}


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