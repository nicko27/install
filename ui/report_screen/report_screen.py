"""
Écran de visualisation des rapports d'exécution.
"""

import os
from textual.app import ComposeResult
from textual.screen import Screen

from .report_viewer import ReportViewer

class ReportScreen(Screen):
    """Écran contenant le widget de visualisation des rapports"""

    CSS_PATH = os.path.join(os.path.dirname(__file__), "../styles/report.tcss")

    def __init__(self, report_path: str):
        """Initialise l'écran avec le chemin du rapport
        
        Args:
            report_path: Chemin vers le fichier ou dossier de rapports
        """
        super().__init__()
        self.report_path = report_path
        
    def compose(self) -> ComposeResult:
        """Création de l'interface"""
        yield ReportViewer(self.report_path)
        
    def on_report_viewer_close_requested(self, message: ReportViewer.CloseRequested) -> None:
        """Gère la demande de fermeture du rapport"""
        self.app.pop_screen()
