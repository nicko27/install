"""IP field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import Input
from .text_field import TextField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class IPField(TextField):
    """IP address input field with validation"""
    

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate IP address on input change"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            # Extract IP address from tuple string if needed
            value = event.input.value
            if value and value.startswith('(') and value.endswith(')'):
                try:
                    # Parse the tuple string and get the second element (the IP)
                    parts = value.strip('()').split(',')
                    if len(parts) >= 2:
                        # Extrait l'adresse IP et nettoie les guillemets/apostrophes
                        value = parts[1].strip().strip('\'"')
                        # Si la valeur est vide après nettoyage, on garde la valeur originale
                        if not value:
                            value = event.input.value
                except Exception as e:
                    logger.warning(f"Erreur lors du parsing du tuple pour {self.field_id}: {e}")
                    # En cas d'erreur, on garde la valeur originale
                    value = event.input.value
            error_input = self.query_one(f"#input_{self.field_id}", Input)
            error_widget = self.query_one(FieldError)
            
            # Get validation rules
            rules = []
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
            rules.append(create_rule('ip'))
            
            # Apply validation rules
            for rule in rules:
                success, message = rule(value)
                if not success:
                    error_input.add_class("error")
                    error_widget.show_error(message)
                    ValidationNotification.error(message, self.field_id)
                    return
            
            # All validations passed
            error_input.remove_class("error")
            error_widget.clear()
            
            # Update dependent fields
            self._update_dependent_fields(value)
