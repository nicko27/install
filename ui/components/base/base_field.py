"""Base field component for plugin configuration"""
import logging
import os
import importlib.util
from typing import Any, Optional, Tuple
from textual.app import ComposeResult
from textual.containers import Container, HorizontalGroup, VerticalGroup
from textual.widgets import Label
from textual.widget import Widget

from ...logging import get_logger
logger = get_logger('components')

class BaseField(Widget):
    """Base class for configuration fields"""
    
    def __init__(self, plugin_path: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(id=field_id)
        self.plugin_path = plugin_path
        self.field_id = field_id
        self.field_config = field_config
        self.fields_by_id = fields_by_id or {}
        self.disabled = False
        self.needs_refresh_when_enabled = False
        logger.info(f"Creating field {field_id} with config: {field_config}")
        
        # Initialize dependencies
        self.enabled_if = field_config.get('enabled_if')
        self.depends_on = field_config.get('depends_on')
        self.variable_name = field_config.get('variable', field_id)
        
        # Get initial value
        self.value = self._get_initial_value()
        
    def _get_initial_value(self) -> Any:
        """Get initial value based on dependencies and configuration"""
        # Check for dynamic default value from script
        if 'dynamic_default' in self.field_config:
            dynamic_value = self._get_dynamic_default()
            if dynamic_value is not None:
                return dynamic_value
                
        # Check for value dependent on another field
        if self.depends_on and 'values' in self.field_config:
            dependent_value = self._get_dependent_value()
            if dependent_value is not None:
                return dependent_value
                
        # Use static default value
        return self.field_config.get('default')
        
    def _get_dependent_value(self) -> Any:
        """Get value based on another field's value"""
        if not self.depends_on or 'values' not in self.field_config:
            return None
            
        # Get the field we depend on
        dep_field = self.fields_by_id.get(self.depends_on)
        if not dep_field:
            logger.warning(f"Dependency field '{self.depends_on}' not found for {self.field_id}")
            return None
            
        # Get its value
        dep_value = dep_field.get_value()
        if dep_value is None:
            return None
            
        # Get corresponding value from mapping
        return self.field_config['values'].get(dep_value)
        
    def _get_dynamic_default(self) -> Any:
        """Get dynamic default value from script"""
        dynamic_config = self.field_config.get('dynamic_default', {})
        if not dynamic_config or 'script' not in dynamic_config:
            return None
            
        script_path = dynamic_config['script']
        is_global = dynamic_config.get('global', False)
        
        # Build full script path
        if not script_path.endswith('.py'):
            script_path += '.py'
            
        if is_global:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', script_path)
        else:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.plugin_path, script_path)
            
        try:
            # Import script module
            spec = importlib.util.spec_from_file_location('dynamic_default', script_full_path)
            if not spec or not spec.loader:
                logger.error(f"Could not load script: {script_full_path}")
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get function to call
            func_name = dynamic_config.get('function', 'get_default_value')
            if not hasattr(module, func_name):
                logger.error(f"Function {func_name} not found in {script_path}")
                return None
                
            # Call function with arguments if specified
            func = getattr(module, func_name)
            if 'args' in dynamic_config:
                args = self._resolve_dynamic_args(dynamic_config['args'])
                result = func(*args)
            else:
                result = func()
                
            # Handle tuple return (success, value)
            if isinstance(result, tuple):
                if len(result) == 2:
                    success, value = result
                    if isinstance(success, bool):
                        if not success:
                            logger.error(f"Dynamic default error: {value}")
                            return None
                        return value
                # Si ce n'est pas un tuple (bool, value), on retourne le tuple tel quel
                return result
                
            return result
            
        except Exception as e:
            logger.error(f"Error getting dynamic default: {e}")
            return None
            
    def _resolve_dynamic_args(self, args_config: list) -> list:
        """Resolve dynamic arguments, replacing field references with their values"""
        resolved_args = []
        for arg in args_config:
            if isinstance(arg, dict) and 'field' in arg:
                # Get value from referenced field
                field_id = arg['field']
                if field_id in self.fields_by_id:
                    field_value = self.fields_by_id[field_id].get_value()
                    resolved_args.append(field_value)
                else:
                    logger.warning(f"Referenced field {field_id} not found")
                    resolved_args.append(None)
            else:
                # Use static value
                resolved_args.append(arg)
        return resolved_args
        
    def update_enabled_state(self) -> None:
        """Update enabled/disabled state based on dependencies"""
        if not self.enabled_if:
            return
            
        # Get the field we depend on
        dep_field_id = self.enabled_if.get('field')
        dep_field = self.fields_by_id.get(dep_field_id) if dep_field_id else None
        
        if not dep_field:
            logger.warning(f"Dependency field '{dep_field_id}' not found for enabled_if on {self.field_id}")
            return
            
        # Get its value and compare
        dep_value = dep_field.get_value()
        should_enable = (dep_value == self.enabled_if.get('value'))
        
        # Update state
        if should_enable != (not self.disabled):
            self.disabled = not should_enable
            if self.disabled:
                self.add_class('disabled')
            else:
                self.remove_class('disabled')
                if self.needs_refresh_when_enabled:
                    self.refresh_field()
                    
    def refresh_field(self) -> None:
        """Refresh field value and options. Override in subclasses if needed."""
        # Update value if it depends on another field
        if self.depends_on:
            new_value = self._get_dependent_value()
            if new_value is not None:
                self.value = new_value
            
    def compose(self) -> ComposeResult:
        """Creates the container for the field and its label"""
        # Create vertical container for the field
        with Container(id=f"field_{self.field_id}", classes="field-container"):
            # Field header with label and required star
            with Container(classes="field-header"):
                yield Label(self.field_config.get('label', self.field_id), classes="field-label")
                if self.field_config.get('required', False):
                    yield Label("*", classes="required-star")
                    
            # Description if present
            if 'description' in self.field_config:
                yield Label(self.field_config['description'], classes="field-description")
                
            # Container for the actual field input
            with Container(classes="field-input-container") as input_container:
                yield input_container
                
            # Check if field should be enabled or not
            if self.enabled_if:
                dep_field = self.fields_by_id.get(self.enabled_if['field'])
                if dep_field:
                    logger.debug(f"Field {self.field_id}: enabled_if={self.enabled_if}, dep_field={dep_field.field_id}, dep_value={dep_field.value}")
                    
                    # Check if field should be enabled
                    should_enable = (dep_field.value == self.enabled_if['value'])
                    self.disabled = not should_enable
                    
                    if self.disabled:
                        logger.debug(f"Field {self.field_id} should be initially disabled")
                        self.add_class('disabled')
                    else:
                        self.remove_class('disabled')
                else:
                    logger.warning(f"Dependency field '{self.enabled_if['field']}' not found for field '{self.field_id}'")
                    
    def get_value(self):
        """Get field value"""
        return self.value
        
    def _get_dynamic_default(self):
        """Get dynamic default value based on another field's value or a script"""
        if 'depends_on' in self.field_config and 'values' in self.field_config:
            # Default value depends on another field
            dep_field = self.fields_by_id.get(self.field_config['depends_on'])
            if dep_field:
                dep_value = dep_field.get_value()
                return self.field_config['values'].get(dep_value, None)
            else:
                logger.warning(f"Dependency field '{self.field_config['depends_on']}' not found for field '{self.field_id}'")
                return None
                
        if 'dynamic_default' in self.field_config and 'script' in self.field_config['dynamic_default']:
            # Default value comes from a script
            dynamic_config = self.field_config['dynamic_default']
            result = self._get_dynamic_options(dynamic_config)
            if result and len(result) > 0:
                return result[0][1]  # Return first value
            return None
            
        return None
        
    def _get_dynamic_options(self, dynamic_config):
        """
        Fonction commune pour obtenir les options dynamiques à partir d'un script.
        
        Args:
            dynamic_config (dict): Configuration des options dynamiques
            
        Returns:
            list: Liste d'options normalisées au format [(label, value), ...]
        """
        if not dynamic_config or 'script' not in dynamic_config:
            logger.error("Configuration des options dynamiques invalide")
            return []
            
        # Le fichier et la fonction à appeler
        script_path = dynamic_config.get('script')
        function_name = dynamic_config.get('function')
        
        if not script_path:
            logger.error("Aucun script spécifié dans dynamic_options")
            return []
            
        # Vérifier si c'est un script global (dans utils)
        is_global_script = dynamic_config.get('global', False)
        
        # Vérifier si le chemin contient une extension .py, sinon l'ajouter
        if not script_path.endswith('.py'):
            script_path += '.py'
            
        # Construire le chemin complet du fichier
        if is_global_script:
            script_full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'utils', script_path))
        else:
            script_full_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'plugins', self.plugin_path, script_path))
            
        logger.info(f"Loading script from: {script_full_path}")
        
        try:
            # Import the script module
            import sys
            import importlib.util
            
            # Assurer que le chemin du script est dans sys.path
            script_dir = os.path.dirname(script_full_path)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
                
            module_name = os.path.splitext(os.path.basename(script_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, script_full_path)
            if not spec:
                logger.error(f"Failed to create module spec for {script_full_path}")
                return []
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Déterminer la fonction à appeler
            # 1. Utiliser la fonction spécifiée dans la configuration si elle existe
            # 2. Sinon, trouver une fonction qui commence par 'get_'
            if not function_name:
                function_name = next((name for name in dir(module) 
                            if name.startswith('get_') and callable(getattr(module, name))), None)
                    
            if not function_name:
                logger.error(f"No suitable function found in {script_path}")
                return []
                
            logger.debug(f"Using function: {function_name}")
            func = getattr(module, function_name)
            
            # Préparer les arguments
            args = []
            kwargs = {}
            
            # Si des arguments sont spécifiés dans la configuration
            if 'args' in dynamic_config:
                for arg_config in dynamic_config['args']:
                    if 'field' in arg_config:
                        # L'argument dépend d'un autre champ
                        field_id = arg_config['field']
                        param_name = arg_config.get('param_name', field_id)
                        
                        if field_id in self.fields_by_id:
                            field_value = self.fields_by_id[field_id].get_value()
                            kwargs[param_name] = field_value
                        else:
                            logger.warning(f"Field {field_id} not found for argument {param_name}")
                    elif 'value' in arg_config:
                        # L'argument est une valeur statique
                        args.append(arg_config['value'])
                        
            # Appeler la fonction
            logger.info(f"Calling {function_name} with args: {args}, kwargs: {kwargs}")
            result = func(*args, **kwargs)
            logger.info(f"Successfully retrieved options from {function_name}")
            
            # Normaliser les options
            return self._normalize_options(result, dynamic_config)
            
        except Exception as e:
            logger.error(f"Error getting dynamic options: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
            
    def _normalize_options(self, options, dynamic_config):
        """
        Normalise les options au format [(label, value), ...] uniforme.
        
        Args:
            options: Données brutes retournées par le script
            dynamic_config: Configuration des options dynamiques
            
        Returns:
            list: Liste d'options normalisées
        """
        normalized = []
        
        # Si les options sont None ou vides
        if not options:
            return normalized
            
        # Log des options brutes pour debug
        logger.debug(f"Normalizing options with label_key='{dynamic_config.get('label_key', 'description')}', value_key='{dynamic_config.get('value_key', 'value')}'")
        logger.debug(f"Options is a {type(options)} with {len(options) if isinstance(options, (list, dict)) else 'N/A'} items")
        if isinstance(options, (list, dict)):
            for i, item in enumerate(options if isinstance(options, list) else options.items()):
                logger.debug(f"  Raw option {i}: {type(item)}: {item}")
                
        # Si les options sont une liste de tuples (label, value)
        if isinstance(options, list) and all(isinstance(x, tuple) and len(x) == 2 for x in options):
            logger.debug("Options already in (label, value) format")
            return options
            
        # Si les options sont un dictionnaire
        if isinstance(options, dict):
            logger.debug("Options is a dict, converting to (label, value) format")
            for key, value in options.items():
                if isinstance(value, (str, int, float, bool)):
                    # Si la valeur est un type simple, utiliser la clé comme label
                    normalized.append((str(key), str(value)))
                elif isinstance(value, dict):
                    # Si la valeur est un dict, chercher label_key/value_key
                    label = value.get(dynamic_config.get('label_key', 'description'), key)
                    val = value.get(dynamic_config.get('value_key', 'value'), value)
                    normalized.append((str(label), str(val)))
                else:
                    # Sinon utiliser la représentation string
                    normalized.append((str(key), str(value)))
            return normalized
            
        # Si les options sont une liste
        if isinstance(options, list):
            logger.debug("Options is a list, converting to (label, value) format")
            for item in options:
                if isinstance(item, (str, int, float, bool)):
                    # Si l'item est un type simple, utiliser la même valeur pour label et value
                    normalized.append((str(item), str(item)))
                elif isinstance(item, dict):
                    # Si l'item est un dict, chercher label_key/value_key
                    label_key = dynamic_config.get('label_key', 'description')
                    value_key = dynamic_config.get('value_key', 'value')
                    
                    raw_label = item.get(label_key, '')
                    raw_value = item.get(value_key, raw_label)
                    
                    logger.debug(f"  From dict: raw_label='{raw_label}', raw_value='{raw_value}'")
                    
                    # Convertir en string
                    label = str(raw_label)
                    value = str(raw_value)
                    
                    logger.debug(f"  Final normalized: '{label}' -> '{value}'")
                    
                    normalized.append((label, value))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    # Si l'item est une liste/tuple avec au moins 2 éléments
                    normalized.append((str(item[0]), str(item[1])))
                else:
                    # Sinon utiliser la représentation string
                    normalized.append((str(item), str(item)))
            return normalized
            
        # Si c'est un autre type, essayer de le convertir en string
        try:
            value = str(options)
            return [(value, value)]
        except:
            return []
