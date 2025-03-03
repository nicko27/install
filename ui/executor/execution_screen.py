"""
Écran d'exécution des plugins.
"""

import os
from textual.app import ComposeResult
from textual.screen import Screen

from .execution_widget import ExecutionWidget

class ExecutionScreen(Screen):
    """Écran contenant le widget d'exécution des plugins"""

    CSS_PATH = os.path.join(os.path.dirname(__file__), "../styles/execution.css")

    def __init__(self, plugins_config: dict = None):
        """Initialise l'écran avec la configuration des plugins
        
        Args:
            plugins_config: Dictionnaire de configuration des plugins
        """
        super().__init__()
        self.plugins_config = plugins_config

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        yield ExecutionWidget(self.plugins_config)