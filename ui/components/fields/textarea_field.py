"""Textarea field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import TextArea
from ..base import BaseField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class TextAreaField(BaseField):
    """Multi-line text area field"""
    
    def compose(self) -> ComposeResult:
        """Create the text area field"""
        yield from super().compose()
        
        # Create text area
        text_area = TextArea(
            id=f"textarea_{self.field_id}",
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', '')
        )
        
        if self.disabled:
            text_area.disabled = True
            
        yield text_area
        
    def get_value(self):
        """Get text area value"""
        text_area = self.query_one(f"#textarea_{self.field_id}", TextArea)
        return text_area.text if text_area else None
        
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Validate text on change"""
        if event.text_area.id == f"textarea_{self.field_id}" and not self.disabled:
            value = event.text_area.text
            error_input = self.query_one(f"#textarea_{self.field_id}", TextArea)
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
