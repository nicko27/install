"""
Module définissant le conteneur pour un plugin à exécuter.
"""

from ..utils.logging import get_logger
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Label, ProgressBar

from ..choice_management.plugin_utils import get_plugin_folder_name

logger = get_logger('plugin_container')

class PluginContainer(Container):
    """Conteneur pour afficher l'état et la progression d'un plugin"""

    def __init__(self, plugin_id: str, plugin_name: str, plugin_show_name: str, plugin_icon: str):
        """Initialise le conteneur avec l'ID et le nom du plugin

        Args:
            plugin_id: L'ID complet du plugin (ex: bash_interactive_1)
            plugin_name: Le nom interne du plugin
            plugin_show_name: Le nom à afficher dans l'interface
            plugin_icon: L'icône associée au plugin
        """
        super().__init__(id=f"plugin-{plugin_id}")
        self.plugin_id = plugin_id
        # Récupérer le nom du dossier pour les logs
        self.folder_name = get_plugin_folder_name(plugin_id)
        # Nom affiché dans l'interface
        self.plugin_name = plugin_name
        self.plugin_show_name = plugin_show_name
        self.plugin_icon = plugin_icon
        self.classes = "plugin-container waiting"

    def compose(self) -> ComposeResult:
        """Création des widgets du conteneur"""
        with Horizontal(classes="plugin-content"):
            yield Label(self.plugin_icon+"  "+self.plugin_show_name, classes="plugin-name")
            yield ProgressBar(classes="plugin-progress", show_eta=False, total=100.0)
            yield Label("En attente", classes="plugin-status")

    def update_progress(self, progress: float, step: str = None):
        """Mise à jour de la progression du plugin"""
        try:
            # Récupérer la barre de progression
            progress_bar = self.query_one(ProgressBar)
            if progress_bar:
                # Convertir la progression en pourcentage et s'assurer qu'elle est entre 0 et 100
                progress_value = max(0, min(100, progress * 100))
                progress_bar.update(progress=progress_value)

            # Mettre à jour le texte de statut si fourni
            if step:
                status_label = self.query_one(".plugin-status")
                if status_label:
                    status_label.update(step)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de la progression: {str(e)}")

    def set_status(self, status: str, message: str = None):
        """Mise à jour du statut du plugin"""
        # Mettre à jour les classes CSS
        self.classes = f"plugin-container {status}"

        # Définir le texte du statut
        status_map = {
            'waiting': 'En attente',
            'running': 'En cours',
            'success': 'Terminé',
            'error': 'Erreur'
        }
        status_text = status_map.get(status, status)
        if message:
            status_text = f"{status_text} - {message}"

        # Mettre à jour le widget de statut
        self.query_one(".plugin-status").update(status_text)