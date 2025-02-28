"""Date field component for plugin configuration"""
import logging
from datetime import datetime
from textual.app import ComposeResult
from textual.widgets import Input
from .text_field import TextField
from ..validation import create_rule

logger = logging.getLogger('install_ui')

class DateField(TextField):
    """Date input field with validation"""
    
    def compose(self) -> ComposeResult:
        """Create the date input field"""
        yield from super().compose()
        
        # Create date input
        date_input = Input(
            id=f"input_{self.field_id}",
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', 'YYYY-MM-DD')
        )
        
        if self.disabled:
            date_input.disabled = True
            
        yield date_input
        
    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate date on input change"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            value = event.input.value
            error_input = self.query_one(f"#input_{self.field_id}", Input)
            error_widget = self.query_one("FieldError")
            
            # Get validation rules
            rules = [create_rule('date')]
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
            
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
                    return
            
            # All validations passed
            error_input.remove_class("error")
            error_widget.clear()
