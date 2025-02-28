"""Checkbox field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import Checkbox
from ..base import BaseField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class CheckboxField(BaseField):
    """Single checkbox field"""
    
    def compose(self) -> ComposeResult:
        """Create the checkbox field"""
        yield from super().compose()
        
        # Create checkbox
        checkbox = Checkbox(
            id=f"checkbox_{self.field_id}",
            value=bool(self.value)
        )
        
        if self.disabled:
            checkbox.disabled = True
            checkbox.add_class('disabled')
            
        yield checkbox
        yield FieldError(self.field_id)
        
    def get_value(self):
        """Get checkbox value"""
        checkbox = self.query_one(f"#checkbox_{self.field_id}", Checkbox)
        return checkbox.value if checkbox else False
        
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes"""
        if not self.disabled:
            value = event.checkbox.value
            error_widget = self.query_one(FieldError)
            
            # Get validation rules
            rules = []
            
            # Required validation
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
                    self.add_class("error")
                    error_widget.show_error(message)
                    ValidationNotification.error(message, self.field_id)
                    return
            
            # All validations passed
            self.remove_class("error")
            error_widget.clear()
