"""Checkbox group field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.widgets import Checkbox, Label
from ..base import BaseField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class CheckboxGroupField(BaseField):
    """Checkbox group field for multiple selection"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_values = set()
        if self.value:
            self.selected_values = set(str(v).strip() for v in self.value.split(',') if v.strip())
            
    def compose(self) -> ComposeResult:
        """Create the checkbox group container"""
        logger.info(f"Creating checkbox group container for {self.field_id}")
        
        # Get initial options
        self.options = self._get_options()
        logger.info(f"Got {len(self.options)} initial options for {self.field_id}")
        
        # First yield parent containers
        yield from super().compose()
        
        # Create checkboxes
        for option in self.options:
            option_label = option[0]  # label is in first position
            option_value = option[1]  # value is in second position
            
            logger.debug(f"Creating checkbox for option: '{option_label}' (value: '{option_value}')")
            
            with HorizontalGroup(classes="checkbox-option"):
                checkbox = Checkbox(
                    id=f"checkbox_{self.field_id}_{option_value}",
                    value=option_value in self.selected_values
                )
                
                if self.disabled:
                    checkbox.disabled = True
                    checkbox.add_class('disabled')
                    
                yield checkbox
                yield Label(option_label)
                
        # Add error widget
        yield FieldError(self.field_id)
                
    def get_value(self):
        """Get selected values as comma-separated string"""
        selected = []
        for option in self.options:
            option_value = option[1]
            checkbox = self.query_one(f"#checkbox_{self.field_id}_{option_value}", Checkbox)
            if checkbox and checkbox.value:
                selected.append(str(option_value))
        return ','.join(selected)
        
    def _get_options(self):
        """Get options from dynamic source if configured, or use static options"""
        if 'dynamic_options' in self.field_config:
            return self._get_dynamic_options(self.field_config['dynamic_options'])
        return [(str(v), str(v)) for v in self.field_config.get('options', [])]
        
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes"""
        if not self.disabled:
            # Get current selection
            selected_values = []
            for option in self.options:
                option_value = option[1]
                checkbox = self.query_one(f"#checkbox_{self.field_id}_{option_value}", Checkbox)
                if checkbox and checkbox.value:
                    selected_values.append(option_value)
            
            error_widget = self.query_one(FieldError)
            
            # Get validation rules
            rules = []
            
            # Required validation
            if self.field_config.get('required', False):
                message = self.field_config.get('messages', {}).get('required')
                rules.append(create_rule('required', message=message))
            
            # Min/max selection validation
            if 'min_selected' in self.field_config or 'max_selected' in self.field_config:
                message = self.field_config.get('messages', {}).get('selection')
                rules.append(create_rule('multiple_selection',
                    min_selected=self.field_config.get('min_selected'),
                    max_selected=self.field_config.get('max_selected'),
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
                success, message = rule(','.join(selected_values))
                if not success:
                    self.add_class("error")
                    error_widget.show_error(message)
                    ValidationNotification.error(message, self.field_id)
                    return
            
            # All validations passed
            self.remove_class("error")
            error_widget.clear()
