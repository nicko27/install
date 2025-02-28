"""Text field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Input
from ..base import BaseField
from ..validation import ValidationRule, create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class TextField(BaseField):
    """Text input field with validation"""
    
    def compose(self) -> ComposeResult:
        """Create the text input field"""
        # Get the base field layout (label, description, etc)
        with Container(classes="field-container"):
            with Container(classes="field-input-container"):
                # Create the text input
                # Convertir la valeur en string de manière sécurisée
                value = self.value
                if isinstance(value, (list, tuple)) and len(value) >= 2:
                    # Si c'est un tuple (success, value), prendre la valeur
                    if isinstance(value[0], bool):
                        value = value[1] if value[0] else ""
                    else:
                        value = str(value)
                elif value is not None:
                    value = str(value)
                else:
                    value = ""

                text_input = Input(
                    id=f"input_{self.field_id}",
                    value=value,
                    placeholder=self.field_config.get('placeholder', '')
                )
                
                if self.disabled:
                    text_input.disabled = True
                    text_input.add_class('disabled')
                    
                yield text_input
                yield FieldError(self.field_id)
        
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes and validation"""
        if event.input.id == f"input_{self.field_id}" and not self.disabled:
            value = event.input.value
            
            # Get validation rules from config
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
                
            # Pattern validation
            if 'pattern' in self.field_config:
                message = self.field_config.get('messages', {}).get('pattern')
                rules.append(create_rule('pattern',
                    pattern=self.field_config['pattern'],
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
            self._update_dependent_fields(value)
            
    def get_value(self) -> str:
        """Get the current value of the text input"""
        text_input = self.query_one(f"#input_{self.field_id}", Input)
        if not text_input:
            return ""
            
        value = text_input.value
        if not value:
            return ""
            
        # Si la valeur est un tuple string, extraire la partie pertinente
        if value.startswith('(') and value.endswith(')'):
            try:
                parts = value.strip('()').split(',')
                if len(parts) >= 2:
                    # Si c'est un tuple (success, value), prendre la valeur
                    success_str = parts[0].strip().lower()
                    if success_str in ['true', 'false']:
                        value = parts[1].strip().strip('\'"')
            except Exception as e:
                logger.warning(f"Erreur lors du parsing du tuple pour {self.field_id}: {e}")
                
        return value
        
    def _get_custom_validation_rules(self) -> list[ValidationRule]:
        """Get custom validation rules from config"""
        rules = []
        for validation in self.field_config['validation']:
            if isinstance(validation, dict):
                rule_type = validation.get('type')
                if rule_type:
                    # Create validation rule from plugin
                    kwargs = {k: v for k, v in validation.items() if k != 'type'}
                    rule = create_rule(rule_type, **kwargs)
                    if rule:
                        rules.append(rule)
                # Add more custom validation types as needed
        return rules
        
    def _update_dependent_fields(self, value: str) -> None:
        """Update fields that depend on this field's value"""
        # Get dependent fields from config
        dependent_fields = self.field_config.get('dependent_fields', [])
        if not dependent_fields:
            return
            
        # Find all fields in the form
        form = self.query(BaseField)
        for field in form:
            if field.field_id in dependent_fields:
                # Update field state based on current value
                field.disabled = not bool(value)
                if field.disabled:
                    field.value = None
