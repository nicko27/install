"""File field component for plugin configuration"""
import logging
import os
from textual.app import ComposeResult
from textual.widgets import Button, Input
from .text_field import TextField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class FileField(TextField):
    """File selection field with browse button"""
    
    def compose(self) -> ComposeResult:
        """Create the file field with browse button"""
        yield from super().compose()
        
        # Create file input
        file_input = Input(
            id=f"input_{self.field_id}",
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', '')
        )
        
        if self.disabled:
            file_input.disabled = True
            
        yield file_input
        yield Button("Browse...", id=f"browse_{self.field_id}")
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle browse button press"""
        if event.button.id == f"browse_{self.field_id}":
            # TODO: Implement file browser
            # For now, just log that it was pressed
            logger.info(f"Browse button pressed for {self.field_id}")
            
    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate file path on input change"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            value = event.input.value
            error_input = self.query_one(f"#input_{self.field_id}", Input)
            error_widget = self.query_one(FieldError)
            
            # Get validation rules
            rules = [create_rule('file_exists')]
            
            # Required validation
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
            
            # Extension validation
            if 'extensions' in self.field_config:
                message = self.field_config.get('messages', {}).get('extension')
                rules.append(create_rule('file_extension',
                    extensions=self.field_config['extensions'],
                    message=message
                ))
            
            # Custom validation
            if 'validation' in self.field_config:
                for validation in self.field_config['validation']:
                    if isinstance(validation, dict):
                        rule_type = validation.get('type')
                        rules.append(create_rule(
                            rule_type,
                            message=validation.get('message')
                        ))
            
            # Apply all validation rules
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
