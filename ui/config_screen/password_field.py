from textual.app import ComposeResult
from textual.widgets import Input
from typing import Optional

from .text_field import TextField
from ..utils.logging import get_logger

logger = get_logger('password_field')

class PasswordField(TextField):
    """Password input field that masks input"""
    
    def __init__(self, source_id: str, field_id: str, field_config: dict, 
                 fields_by_id: dict = None, is_global: bool = False,
                 instance_id: Optional[int] = None):
        """
        Initialise un champ de mot de passe.
        
        Args:
            source_id: ID du plugin ou de la source
            field_id: ID unique du champ
            field_config: Configuration du champ
            fields_by_id: Dictionnaire des champs par ID (pour les dépendances)
            is_global: Indique si le champ est global
            instance_id: ID d'instance (optionnel)
        """
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global, instance_id)
    
    def compose(self) -> ComposeResult:
        """Create password field components"""
        yield from super().compose()
        
        # Remplacer l'input standard par un input en mode password
        self.input.password = True
        
        # Toujours initialiser à l'état activé
        self.input.disabled = False
        self.input.remove_class('disabled')
        
        if self.disabled:
            logger.debug(f"PasswordField {self.field_id} is initially disabled")
            self.input.disabled = True
            self.input.add_class('disabled')