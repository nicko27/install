from textual.app import ComposeResult
from textual.widgets import Button
from textual.containers import VerticalGroup, Horizontal
from subprocess import Popen, PIPE
from typing import Any, Optional, Tuple, cast

from .text_field import TextField
from ..utils.logging import get_logger

logger = get_logger('directory_field')

class DirectoryField(TextField):
    """Champ de sélection de répertoire avec un bouton de navigation"""
    
    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        """Initialisation du champ avec les options spécifiques aux répertoires"""
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        logger.debug(f"Initialisation du champ répertoire {self.field_id}")
        self._browse_button: Optional[Button] = None
    
    def compose(self) -> ComposeResult:
        """Composition des éléments visuels du champ"""
        # 1. Récupérer les widgets de base du TextField
        parent_widgets = list(super().compose())
        
        # 2. Rendre les widgets de base
        for widget in parent_widgets:
            yield widget

        # 3. Ajouter le bouton Browse en dehors du conteneur d'input
        self._browse_button = Button(
            "Parcourir...", 
            id=f"browse_{self.field_id}", 
            classes="browse-button"
        )
        yield self._browse_button
    
    def on_mount(self) -> None:
        """Exécuté après création des widgets"""
        logger.debug(f"🚨 MONTAGE du champ répertoire {self.field_id}")
        # Appeler la méthode du parent (TextField) pour la gestion des valeurs en attente
        # et l'application des valeurs stockées dans _internal_value ou _pending_value
        super().on_mount()
        
        # Si le champ est désactivé, désactiver aussi le bouton de navigation
        if self.disabled and hasattr(self, '_browse_button') and self._browse_button:
            self._browse_button.disabled = True
    
    def set_disabled(self, disabled: bool) -> None:
        """Désactive ou active à la fois le champ texte et le bouton browse"""
        # Appeler la méthode parent pour désactiver le champ texte
        super().set_disabled(disabled)
        
        # Désactiver aussi le bouton browse si nécessaire
        if hasattr(self, '_browse_button') and self._browse_button:
            self._browse_button.disabled = disabled
    
    def validate_input(self, value: str) -> Tuple[bool, str]:
        """Validation spécifique pour les chemins de répertoire"""
        # Utiliser d'abord la validation de base (vide, longueur, etc.)
        is_valid, error_msg = super().validate_input(value)
        if not is_valid:
            return is_valid, error_msg
        
        # Validation spécifique aux répertoires
        # Par exemple, vérifier si c'est un chemin existant si 'exists' est spécifié
        if value and self.field_config.get('exists', False):
            import os
            if not os.path.exists(value):
                return False, "Ce répertoire n'existe pas"
            if not os.path.isdir(value):
                return False, "Ce chemin n'est pas un répertoire"
        
        # Si on arrive ici, tout est valide
        return True, ""
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gestion du clic sur le bouton Browse"""
        # Vérifier que c'est bien notre bouton
        if event.button.id != f"browse_{self.field_id}":
            return
            
        logger.debug(f"🔍 Bouton Browse pressé pour {self.field_id}")
        
        # Lancer la boîte de dialogue de sélection de répertoire via zenity
        try:
            from subprocess import Popen, PIPE
            # Utiliser le répertoire actuel comme point de départ si déjà défini
            current_dir = self._internal_value if self._internal_value else ""
            
            # Args pour zenity - démarrer dans le répertoire actuel si possible
            zenity_args = ['zenity', '--file-selection', '--directory']
            if current_dir and os.path.isdir(current_dir):
                zenity_args.extend(['--filename', current_dir])
                
            process = Popen(zenity_args, stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()
            
            if stderr:
                logger.debug(f"Zenity stderr: {stderr.decode()}")
                
            # Si réussi, appliquer le répertoire sélectionné
            if process.returncode == 0:
                selected_dir = stdout.decode().strip()
                logger.debug(f"Répertoire sélectionné: '{selected_dir}'")
                
                # Mise à jour de la valeur via notre méthode standard
                if selected_dir and selected_dir != self._internal_value:
                    logger.debug(f"Application du répertoire sélectionné pour {self.field_id}")
                    self.set_value(selected_dir)
                    
        except Exception as e:
            logger.error(f"Erreur lors de la sélection du répertoire: {e}")
            import traceback
            logger.error(traceback.format_exc())