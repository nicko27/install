"""Radio group field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import RadioButton, Label
from ..base import BaseField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class RadioGroupField(BaseField):
    """Radio button group field"""
    
    def compose(self) -> ComposeResult:
        """Create the radio button group"""
        yield from super().compose()
        
        # Get options
        self.options = self._get_options()
        logger.info(f"Got {len(self.options)} options for radio group {self.field_id}")
        
        # Create radio buttons
        for option in self.options:
            option_label = option[0]  # label is in first position
            option_value = option[1]  # value is in second position
            
            with HorizontalGroup(classes="radio-option"):
                radio = RadioButton(
                    id=f"radio_{self.field_id}_{option_value}",
                    value=str(self.value) == str(option_value)
                )
                
                if self.disabled:
                    radio.disabled = True
                    radio.add_class('disabled')
                    
                yield radio
                yield Label(option_label)
                
        # Add error widget
        yield FieldError(self.field_id)
                
    def get_value(self):
        """Get selected radio button value"""
        for option in self.options:
            option_value = option[1]
            radio = self.query_one(f"#radio_{self.field_id}_{option_value}", RadioButton)
            if radio and radio.value:
                return option_value
        return None
        
    def _get_options(self):
        """Get options from dynamic source if configured, or use static options"""
        if 'dynamic_options' in self.field_config:
            return self._get_dynamic_options(self.field_config['dynamic_options'])
        return [(str(v), str(v)) for v in self.field_config.get('options', [])]
        
    def on_radio_button_changed(self, event: RadioButton.Changed) -> None:
        """Handle radio button changes"""
        if not self.disabled:
            # Get all radio buttons in the group
            radio_buttons = self.query("RadioButton")
            selected_value = None
            
            # Find which button is selected
            for button in radio_buttons:
                if button.value:
                    selected_value = button.id.split('_')[-1]
                    break
            
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
                success, message = rule(selected_value)
                if not success:
                    self.add_class("error")
                    error_widget.show_error(message)
                    ValidationNotification.error(message, self.field_id)
                    return
            
            # All validations passed
            self.remove_class("error")
            error_widget.clear()
