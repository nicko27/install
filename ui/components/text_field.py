from textual.app import ComposeResult
from textual.widgets import Input

from .config_field import ConfigField
from ..utils import setup_logging

logger = setup_logging()

class TextField(ConfigField):
    """Text input field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        self.input = Input(
            placeholder=self.field_config.get('placeholder', ''),
            value=self.value or '',
            id=f"input_{self.field_id}"
        )
        # Always initialize to enabled state first
        self.input.disabled = False
        self.input.remove_class('disabled')
        
        if self.disabled:
            logger.debug(f"TextField {self.field_id} is initially disabled")
            self.input.disabled = True
            self.input.add_class('disabled')
        yield self.input

    def validate_input(self, value: str) -> tuple[bool, str]:
        """Validate input value according to configured rules"""
        # Vérifier si le champ est désactivé par enabled_if
        if self.enabled_if and self.disabled:
            return True, ""

        # Vérifier not_empty
        if self.field_config.get('not_empty', False) and not value:
            return False, "Ce champ ne peut pas être vide"
            
        # Vérifier min_length
        min_length = self.field_config.get('min_length')
        if min_length and len(value) < min_length:
            return False, f"La longueur minimale est de {min_length} caractères"
            
        # Vérifier max_length
        max_length = self.field_config.get('max_length')
        if max_length and len(value) > max_length:
            return False, f"La longueur maximale est de {max_length} caractères"
            
        # Vérifier no_spaces
        if self.field_config.get('validate') == 'no_spaces' and ' ' in value:
            return False, "Les espaces ne sont pas autorisés"
            
        return True, ""

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            # Ensure value is a string
            value = str(event.value) if event.value is not None else ""
            
            # Validation
            is_valid, error_msg = self.validate_input(value)
            if not is_valid:
                self.input.add_class('error')
                # Update tooltip with error message
                self.input.tooltip = error_msg
                return
            else:
                self.input.remove_class('error')
                self.input.tooltip = None
                
            self.value = value