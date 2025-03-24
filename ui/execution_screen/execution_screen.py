"""
Écran d'exécution des plugins.
"""

import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button
from textual.message import Message

from .execution_widget import ExecutionWidget
from ..report_screen import ReportScreen

class ExecutionScreen(Screen):
    """Écran contenant le widget d'exécution des plugins"""

    CSS_PATH = os.path.join(os.path.dirname(__file__), "../styles/execution.tcss")
    
    class ShowReportRequested(Message):
        """Message pour demander l'affichage du rapport"""
        def __init__(self, report_path: str):
            self.report_path = report_path
            super().__init__()

    def __init__(self, plugins_config: dict = None, auto_execute: bool = False, report_manager=None):
        """Initialise l'écran avec la configuration des plugins
        
        Args:
            plugins_config: Dictionnaire de configuration des plugins
            auto_execute: Si True, lance l'exécution automatiquement
            report_manager: Gestionnaire de rapports optionnel
        """
        super().__init__()
        self.plugins_config = plugins_config
        self.auto_execute = auto_execute
        self.report_manager = report_manager
        
    async def on_mount(self) -> None:
        """Appelé quand l'écran est monté"""
        try:
            # Appeler initialize_screen après le rafraîchissement du DOM
            # call_after_refresh ne retourne pas un awaitable, donc pas de await
            self.call_after_refresh(self.initialize_screen)
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors du montage de l'écran d'exécution: {str(e)}")
            self.notify(f"Erreur lors de l'initialisation: {str(e)}", severity="error")
    
    async def initialize_screen(self):
        """Initialise l'écran après le montage complet"""
        try:
            # Configurer le gestionnaire de rapports si présent
            widget = self.query_one(ExecutionWidget)
            if widget and self.report_manager:
                widget.report_manager = self.report_manager
                
            if self.auto_execute:
                # Lancer l'exécution automatiquement
                if widget:
                    await widget.start_execution()
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors de l'initialisation de l'écran: {str(e)}")
            self.notify(f"Erreur lors de l'initialisation: {str(e)}", severity="error")
    
    async def on_execution_completed(self) -> None:
        """Appelé quand l'exécution des plugins est terminée"""
        # Si un rapport a été généré, proposer de l'afficher
        widget = self.query_one(ExecutionWidget)
        if widget and widget.report_manager:
            report_path = widget.report_manager.save_csv_report()
            if report_path:
                self.notify(f"Rapport sauvegardé : {report_path}", severity="information")
                # Émettre un message pour afficher le rapport
                self.post_message(self.ShowReportRequested(report_path))
    
    def show_report(self, report_path: str) -> None:
        """Affiche l'écran de rapport"""
        self.app.push_screen(ReportScreen(report_path))

    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        try:
            yield ExecutionWidget(self.plugins_config)
        except Exception as e:
            from ..utils.logging import get_logger
            logger = get_logger('execution_screen')
            logger.error(f"Erreur lors de la composition de l'écran d'exécution: {str(e)}")
            # Fallback to a basic message if widget creation fails
            from textual.widgets import Static
            yield Static(f"Erreur lors de la création de l'interface: {str(e)}\n\nVeuillez vérifier les logs pour plus de détails.")