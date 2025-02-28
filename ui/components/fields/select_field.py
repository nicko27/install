"""Select field component for plugin configuration"""
import logging
from textual.app import ComposeResult
from textual.widgets import Select
from ..base import BaseField
from ..validation import create_rule
from ..utils import ValidationNotification, FieldError

logger = logging.getLogger('install_ui')

class SelectField(BaseField):
    """Select field for dropdown selection"""
    
    def compose(self) -> ComposeResult:
        """Create the select field"""
        yield from super().compose()
        
        # Get options
        options = self._get_options()
        logger.info(f"Got {len(options)} options for select field {self.field_id}")
        
        # Create select widget
        # Get default value
        default_value = str(self.value) if self.value is not None else None
        if default_value is None and options:
            default_value = str(options[0][1])  # Use first option as default
            
        select = Select(
            options=[(str(label), str(value)) for label, value in options],
            id=f"select_{self.field_id}",
            value=default_value,
            allow_blank=not self.field_config.get('required', False)
        )
        
        if self.disabled:
            select.disabled = True
            
        yield select
        yield FieldError(self.field_id)
        
    def get_value(self):
        """Get the current value of the select"""
        select = self.query_one(f"#select_{self.field_id}", Select)
        return select.value if select else None
        
    def _get_options(self):
        """Get options from dynamic source if configured, or use static options"""
        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']
            try:
                # Import the module
                import importlib.util
                import os
                
                # Get plugin path from base field
                if not self.plugin_path:
                    logger.error(f"No plugin_path found for field {self.field_id}")
                    return [('Error loading options', 'none')]
                    
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                                          'plugins', self.plugin_path, dynamic_config['script'])
                
                if not os.path.exists(script_path):
                    logger.error(f"Dynamic options script not found: {script_path}")
                    return [('No options available', '')]
                    
                spec = importlib.util.spec_from_file_location(dynamic_config['script'], script_path)
                if not spec or not spec.loader:
                    logger.error(f"Could not load dynamic options module: {script_path}")
                    return [('Error loading options', '')]
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get the function
                func = getattr(module, dynamic_config['function'])
                if not func:
                    logger.error(f"Function {dynamic_config['function']} not found in {script_path}")
                    return [('Error loading options', '')]
                    
                # Call the function with args if specified
                if 'args' in dynamic_config:
                    args = self._resolve_dynamic_args(dynamic_config['args'])
                    result = func(*args)
                else:
                    result = func()

                # Handle tuple return (success, value)
                if isinstance(result, tuple):
                    if len(result) == 2 and isinstance(result[0], bool):
                        success, value = result
                        if not success:
                            logger.error(f"Error from dynamic function: {value}")
                            return [('Error loading options', 'none')]
                        result = value
                    else:
                        # Si ce n'est pas un tuple (bool, value), on utilise le résultat tel quel
                        result = [result]
                
                # Extract values using the specified keys
                value_key = dynamic_config.get('value_key', 'value')
                label_key = dynamic_config.get('label_key', 'label')
                
                # Normalize the result into a list of items
                if not isinstance(result, (list, tuple)):
                    result = [result]
                
                options = []
                for item in result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        # Si c'est déjà un tuple (label, value)
                        options.append((str(item[0]), str(item[1])))
                    elif isinstance(item, dict):
                        # Si c'est un dictionnaire, utiliser les clés spécifiées
                        label = item.get(label_key, str(item))
                        value = item.get(value_key, str(item))
                        options.append((str(label), str(value)))
                    else:
                        # Pour les autres cas, utiliser la valeur comme label et value
                        str_item = str(item)
                        options.append((str_item, str_item))
                
                if not options:
                    logger.warning(f"No options returned from {script_path}")
                    return [('No options available', 'none')]
                    
                return options
                
            except Exception as e:
                logger.error(f"Error getting dynamic options: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return [('Error loading options', '')]
                
        return [(str(v), str(v)) for v in self.field_config.get('options', [])]
        
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes"""
        if not self.disabled:
            value = event.value
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
