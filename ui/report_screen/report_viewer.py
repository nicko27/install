"""
Widget de visualisation des rapports d'exécution.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import DataTable, Button, Label, Input
from textual.widgets.data_table import RowKey
from textual.reactive import reactive
from textual.message import Message
from pathlib import Path
from typing import Dict, List, Any
from logging import getLogger

from .report_manager import ReportManager

logger = getLogger('report_viewer')

class ReportViewer(Vertical):
    """Interface de visualisation des rapports d'exécution"""

    # Messages personnalisés
    class CloseRequested(Message):
        """Message pour demander la fermeture de l'écran"""
        pass

    def __init__(self, report_path: str):
        super().__init__()
        self.report_path = report_path
        self.report_manager = ReportManager()
        self.reports = []
        self.filtered_reports = []

    def compose(self) -> ComposeResult:
        """Compose l'interface utilisateur"""
        with Horizontal(id="controls"):
            yield Label("Filtre:", classes="section-title")
            yield Input(placeholder="Filtrer...", id="filter-input")
        
        with ScrollableContainer():
            yield DataTable(id="report-table")
        
        with Horizontal(id="button-container"):
            yield Button("Actualiser", id="refresh", variant="primary")
            yield Button("Fermer", id="close", variant="error")

    def on_mount(self) -> None:
        """Configuration initiale"""
        # Configuration de la table
        table = self.query_one("#report-table", DataTable)
        table.add_columns(
            "Horodatage", "Machine", "Séquence", 
            "Plugin", "Instance", "Statut", "Sortie"
        )
        
        # Chargement initial des données
        self.load_reports()

    def load_reports(self) -> None:
        """Charge et affiche les rapports"""
        try:
            # Charger les rapports
            self.reports = self.report_manager.load_reports(self.report_path)
            self.filtered_reports = self.reports.copy()
            
            # Mettre à jour la table
            self.update_table()
            
            # Message d'info
            count = len(self.reports)
            self.notify(f"{count} rapports chargés", severity="information")
            
        except Exception as e:
            logger.error(f"Erreur chargement rapports : {e}")
            self.notify(f"Erreur : {str(e)}", severity="error")

    def update_table(self) -> None:
        """Met à jour l'affichage de la table"""
        table = self.query_one("#report-table", DataTable)
        
        # Effacer les données existantes
        table.clear()
        
        # Ajouter les rapports filtrés
        for i, report in enumerate(self.filtered_reports):
            row_key = RowKey(str(i))
            
            # Déterminer la classe CSS pour le statut
            status_class = "success" if report.get('statut') == 'Succès' else "error"
            
            # Ajouter la ligne avec formatage
            table.add_row(
                report.get('timestamp', ''),
                report.get('machine', ''),
                report.get('sequence', ''),
                report.get('plugin', ''),
                report.get('instance', ''),
                report.get('statut', ''),
                report.get('sortie', ''),
                key=row_key
            )
            
            # Appliquer le style au statut
            table.columns[5].cells[row_key] = (report.get('statut', ''), status_class)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filtre les rapports selon le texte saisi"""
        if event.input.id == "filter-input":
            search_text = event.value.lower()
            
            if search_text:
                # Filtrer les rapports contenant le texte recherché
                self.filtered_reports = [
                    r for r in self.reports
                    if any(search_text in str(v).lower() for v in r.values())
                ]
            else:
                # Pas de filtre, afficher tous les rapports
                self.filtered_reports = self.reports.copy()
            
            self.update_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gère les clics sur les boutons"""
        if event.button.id == "refresh":
            self.load_reports()
            self.notify("Rapports actualisés", severity="information")
        elif event.button.id == "close":
            # Envoyer un message pour fermer l'écran
            self.post_message(self.CloseRequested())
