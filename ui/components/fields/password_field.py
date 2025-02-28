"""Password field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import Input
from .text_field import TextField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class PasswordField(TextField):
    """Password input field with masked text"""
    
    def compose(self) -> ComposeResult:
        """Create the password input field"""
        yield from super().compose()
        
        # Create password input
        password_input = Input(
            id=f"input_{self.field_id}",
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', ''),
            password=True  # This masks the input
        )
        
        if self.disabled:
            password_input.disabled = True
            
        yield password_input
        
    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate password on input change"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            value = event.input.value
            error_input = self.query_one(f"#input_{self.field_id}", Input)
            error_widget = self.query_one(FieldError)
            
            # Get validation rules
            rules = []
            
            # Required validation
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
                
            # Length validation
            if 'min_length' in self.field_config or 'max_length' in self.field_config:
                message = self.field_config.get('messages', {}).get('length')
                rules.append(create_rule('length',
                    min_length=self.field_config.get('min_length'),
                    max_length=self.field_config.get('max_length'),
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
