import os
import csv
from datetime import datetime
import socket
from pathlib import Path
from typing import Dict, List, Any, Optional
from logging import getLogger

logger = getLogger('report_manager')

class ReportManager:
    """Gestionnaire de rapports d'exécution"""

    def __init__(self, output_dir: str = 'rapports'):
        self.output_dir = output_dir
        self.machine_name = self._get_machine_name()
        self.reports = []
        self._setup_output_dir()

    def _get_machine_name(self) -> str:
        """Récupère le nom de la machine locale"""
        try:
            return socket.gethostname()
        except:
            return "machine_inconnue"

    def _setup_output_dir(self) -> None:
        """Crée le dossier de sortie pour les rapports"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            logger.info(f"Dossier de rapports créé : {self.output_dir}")
        except Exception as e:
            logger.error(f"Erreur création dossier rapports : {e}")

    def add_result(self, plugin_name: str, instance_id: int, 
                  success: bool, output: str, 
                  sequence_name: Optional[str] = None) -> None:
        """Ajoute un résultat d'exécution"""
        self.reports.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'machine': self.machine_name,
            'sequence': sequence_name or 'exécution_directe',
            'plugin': plugin_name,
            'instance': instance_id,
            'statut': 'Succès' if success else 'Erreur',
            'sortie': output.replace('\n', ' ') if output else ''
        })

    def save_csv_report(self) -> str:
        """Sauvegarde le rapport au format CSV"""
        if not self.reports:
            logger.warning("Aucun résultat à sauvegarder")
            return ""

        try:
            # Nom du fichier basé sur la machine et la date
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"rapport_{self.machine_name}_{timestamp}.csv"
            filepath = os.path.join(self.output_dir, filename)

            # En-têtes du CSV
            fieldnames = ['timestamp', 'machine', 'sequence', 'plugin', 
                         'instance', 'statut', 'sortie']

            # Écriture du fichier CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.reports)

            logger.info(f"Rapport CSV sauvegardé : {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Erreur sauvegarde rapport CSV : {e}")
            return ""

    def load_reports(self, path: str) -> List[Dict[str, Any]]:
        """Charge les rapports depuis un fichier ou dossier"""
        reports = []
        try:
            path_obj = Path(path)
            
            # Si c'est un dossier, charger tous les CSV
            if path_obj.is_dir():
                for csv_file in path_obj.glob('*.csv'):
                    reports.extend(self._load_csv_file(csv_file))
            # Si c'est un fichier CSV
            elif path_obj.suffix.lower() == '.csv':
                reports.extend(self._load_csv_file(path_obj))
            else:
                logger.error(f"Chemin invalide : {path}")

            return reports

        except Exception as e:
            logger.error(f"Erreur chargement rapports : {e}")
            return []

    def _load_csv_file(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Charge un fichier CSV de rapport"""
        reports = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                reports.extend(list(reader))
            logger.debug(f"Rapport chargé : {csv_path}")
            return reports
        except Exception as e:
            logger.error(f"Erreur lecture CSV {csv_path}: {e}")
            return []
