"""
Écran d'exécution des plugins
"""
import os
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, ProgressBar, Static

class PluginStatus(Static):
    """Widget affichant le statut d'un plugin avec ses valeurs de configuration"""
    
    def __init__(self, plugin_name: str, instance_id: int, config_values: dict):
        super().__init__()
        self.plugin_name = plugin_name
        self.instance_id = instance_id
        self.config_values = config_values
        
    def compose(self) -> ComposeResult:
        """Créer l'interface du widget"""
        with Container(classes="plugin-status-container"):
            # En-tête avec le nom du plugin et son ID d'instance
            with Horizontal(classes="plugin-header"):
                yield Label(f"{self.plugin_name} #{self.instance_id}", classes="plugin-title")
                yield Label("En attente", classes="plugin-state waiting")
            
            # Valeurs de configuration
            with Container(classes="config-values"):
                for key, value in self.config_values.items():
                    with Horizontal():
                        yield Label(f"{key}:", classes="config-key")
                        yield Label(str(value), classes="config-value")

class ExecutionScreen(Screen):
    """Écran d'exécution des plugins"""
    
    BINDINGS = [
        Binding("l", "toggle_logs", "Afficher/Masquer les logs", show=True),
        Binding("escape", "quit", "Retour", show=True),
    ]
    
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/execution.css")
    
    def __init__(self, plugins_config: dict):
        """
        Args:
            plugins_config: Dictionnaire {plugin_id: {config_values}}
        """
        super().__init__()
        self.plugins_config = plugins_config
        self.show_logs = False
    
    def compose(self) -> ComposeResult:
        """Créer l'interface"""
        yield Header()
        
        with Container(id="execution-container"):
            # Zone de contrôle supérieure
            with Horizontal(classes="controls-section"):
                yield Button("Démarrer", id="start", variant="primary")
                yield Label("Progression globale :", classes="progress-label")
                yield ProgressBar(id="global-progress", total=100)
            
            # Label pour la dernière opération
            yield Label("En attente du démarrage...", id="last-operation")
            
            # Liste des plugins avec leur configuration
            with ScrollableContainer(id="plugins-list"):
                for plugin_id, config in self.plugins_config.items():
                    plugin_name, instance_id = plugin_id.rsplit('_', 1)
                    yield PluginStatus(plugin_name, int(instance_id), config)
            
            # Zone de logs (masquée par défaut)
            yield Container(id="logs-container", classes="hidden")
        
        yield Footer()
    
    def action_toggle_logs(self) -> None:
        """Afficher/masquer la zone de logs"""
        self.show_logs = not self.show_logs
        logs = self.query_one("#logs-container")
        if self.show_logs:
            logs.remove_class("hidden")
        else:
            logs.add_class("hidden")
    
    def action_quit(self) -> None:
        """Retourner à l'écran précédent"""
        self.app.pop_screen()
