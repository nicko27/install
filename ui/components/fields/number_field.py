"""Number field component for plugin configuration"""
import logging
from typing import Optional, Union
from textual.app import ComposeResult
from textual.widgets import Input
from ..base import BaseField
from ..validation import ValidationRule, create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class NumberField(BaseField):
    """Number input field with validation"""
    
    def compose(self) -> ComposeResult:
        """Create the number input field"""
        yield from super().compose()
        
        # Create the number input
        number_input = Input(
            id=f"input_{self.field_id}",
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', '')
        )
        
        if self.disabled:
            number_input.disabled = True
            number_input.add_class('disabled')
            
        yield number_input
        yield FieldError(self.field_id)
        
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes and validation"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            value = event.input.value
            
            # Get validation rules from config
            rules = [create_rule('number')]
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
                
            if 'min' in self.field_config or 'max' in self.field_config:
                message = self.field_config.get('messages', {}).get('range')
                rules.append(create_rule('range',
                    min_value=self.field_config.get('min'),
                    max_value=self.field_config.get('max'),
                    message=message
                ))
                
            # Custom validation
            if 'validation' in self.field_config:
                rules.extend(self._get_custom_validation_rules())
                
            # Apply all validation rules
            error_input = self.query_one(f"#input_{self.field_id}", Input)
            error_widget = self.query_one(FieldError)
            
            for rule in rules:
                success, message = rule(value)
                if not success:
                    error_input.add_class("error")
                    error_widget.show_error(message)
                    # Show notification for first error
                    ValidationNotification.error(message, self.field_id)
                    return
                    
            # All validations passed
            error_input.remove_class("error")
            error_widget.clear()
            
            # Update dependent fields
            self._update_dependent_fields(self.get_value())
            
    def get_value(self) -> Optional[Union[int, float]]:
        """Get the current value of the number input"""
        number_input = self.query_one(f"#input_{self.field_id}", Input)
        if number_input and number_input.value:
            try:
                # Try integer first
                return int(number_input.value)
            except ValueError:
                try:
                    # Then try float
                    return float(number_input.value)
                except ValueError:
                    return None
        return None
        
    def _get_custom_validation_rules(self) -> list[ValidationRule]:
        """Get custom validation rules from config"""
        rules = []
        for validation in self.field_config['validation']:
            if isinstance(validation, dict):
                rule_type = validation.get('type')
                rules.append(create_rule(
                    rule_type,
                    min_value=validation.get('min'),
                    max_value=validation.get('max'),
                    message=validation.get('message')
                    ))
                # Add more custom validation types as needed
        return rules
