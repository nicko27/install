from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Checkbox, Label
import os
import importlib.util
import sys
import traceback

from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('checkbox_group_field')

class CheckboxGroupField(ConfigField):
    """Field for multiple checkbox selection"""

    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        self.add_class("field-type-checkbox-group")
        self.checkboxes = {}
        self.options = []
        self.selected_values = []
        
        # Initialiser la dépendance si elle est définie dans la configuration
        if 'depends_on' in field_config:
            self.depends_on = field_config['depends_on']
            logger.debug(f"Champ {self.field_id} dépend de {self.depends_on}")

    def compose(self) -> ComposeResult:
        # Créer le conteneur pour les checkboxes
        with VerticalGroup(classes="field-input-container checkbox-group-container"):
            # Get options for checkboxes
            self.options = self._get_options()
            logger.debug(f"Checkbox group options for {self.field_id}: {self.options}")

            if not self.options:
                logger.warning(f"No options available for checkbox group {self.field_id}")
            else:
                label = self.field_config.get('label', self.field_id)
                with HorizontalGroup(classes="field-header", id=f"header_{self.field_id}"):
                    if self.field_config.get('required', False):
                        yield Label(f"{label} *", classes="field-label required-field")
                    else:
                        yield Label(label, classes="field-label")

                # Create a checkbox for each option
                for option_label, option_value in self.options:
                    checkbox_id = f"checkbox_group_{self.source_id}_{self.field_id}_{option_value}".replace(".","_")
                    with HorizontalGroup(classes="checkbox-group-item"):
                        checkbox = Checkbox(
                            id=checkbox_id,
                            classes="field-checkbox-group-item",
                            value=option_value in self.selected_values
                        )
                        self.checkboxes[option_value] = checkbox

                        yield checkbox

    def _get_options(self) -> list:
        """Get options for the checkbox group, either static or dynamic"""
        if 'options' in self.field_config:
            logger.debug(f"Using static options from config: {self.field_config['options']}")
            return self._normalize_options(self.field_config['options'])

        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']
            logger.debug(f"Loading dynamic options with config: {dynamic_config}")

            # Determine script path (global or plugin)
            if dynamic_config.get('global', False):
                # Script in utils folder
                script_name = dynamic_config['script']
                script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
            else:
                # Script in plugin folder
                script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.source_id, dynamic_config['script'])

            logger.debug(f"Loading script from: {script_path}")
            logger.debug(f"Script exists: {os.path.exists(script_path)}")

            try:
                # Import the script module
                sys.path.append(os.path.dirname(script_path))
                logger.debug(f"Python path: {sys.path}")

                spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
                if not spec:
                    logger.error("Failed to create module spec")
                    return [("Error loading module", "error_loading")]

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Get the function name
                func_name = dynamic_config.get('function')
                if not func_name or not hasattr(module, func_name):
                    logger.error(f"Function {func_name} not found in script")
                    return [("Function not found", "function_not_found")]

                logger.debug(f"Using function: {func_name}")

                # Prepare arguments if any
                args = []
                kwargs = {}

                if 'args' in dynamic_config:
                    for arg_config in dynamic_config['args']:
                        if 'field' in arg_config:
                            # Get value from another field
                            field_id = arg_config['field']
                            if field_id in self.fields_by_id:
                                field_value = self.fields_by_id[field_id].get_value()
                                param_name = arg_config.get('param_name')
                                if param_name:
                                    kwargs[param_name] = field_value
                                else:
                                    args.append(field_value)
                        elif 'value' in arg_config:
                            # Static value
                            param_name = arg_config.get('param_name')
                            if param_name:
                                kwargs[param_name] = arg_config['value']
                            else:
                                args.append(arg_config['value'])

                logger.debug(f"Calling {func_name} with args={args}, kwargs={kwargs}")

                # Call the function with arguments
                if args and kwargs:
                    result = getattr(module, func_name)(*args, **kwargs)
                elif args:
                    result = getattr(module, func_name)(*args)
                elif kwargs:
                    result = getattr(module, func_name)(**kwargs)
                else:
                    result = getattr(module, func_name)()

                logger.debug(f"Result from {func_name}: {result}")

                # Process the result
                if isinstance(result, tuple) and len(result) == 2:
                    success, data = result

                    if not success:
                        logger.error(f"Dynamic options script failed: {data}")
                        return [("Script error", "script_error")]

                    # If data is a list, process it
                    if isinstance(data, list):
                        # Extract value_key and label_key if specified
                        value_key = dynamic_config.get('value')
                        label_key = dynamic_config.get('description')

                        options = []
                        for item in data:
                            if isinstance(item, dict):
                                if value_key and label_key and value_key in item and label_key in item:
                                    options.append((str(item[label_key]), str(item[value_key])))
                                elif value_key and value_key in item:
                                    # Use value as label if no label_key specified
                                    value = str(item[value_key])
                                    options.append((value, value))
                            else:
                                # For simple values, use as both label and value
                                value = str(item)
                                options.append((value, value))

                        if options:
                            return options
                        else:
                            # Si la liste est vide, retourner None pour que le champ soit supprimé
                            return None

                    # If it's not a list, return an error
                    logger.error(f"Expected list result, got {type(data)}")
                    return None

                # If result is not a tuple, return an error
                logger.error(f"Expected tuple result (success, data), got {type(result)}")
                return [("Invalid result format", "invalid_format")]

            except Exception as e:
                logger.error(f"Error loading dynamic options: {e}")
                logger.error(traceback.format_exc())
                return [(f"Error: {str(e)}", "script_exception")]

        # Fallback if no options defined
        return [("No options defined", "no_options_defined")]

    def _normalize_options(self, options: list) -> list:
        """
        Normalize options to format expected by checkbox group: (label, value)
        The value must be a string and must be unique.
        """
        normalized = []
        for opt in options:
            if isinstance(opt, (list, tuple)):
                # If it's already a tuple/list, make sure it has 2 elements
                if len(opt) >= 2:
                    normalized.append((str(opt[0]), str(opt[1])))
                else:
                    normalized.append((str(opt[0]), str(opt[0])))
            elif isinstance(opt, dict):
                # For dictionaries with description and value
                if 'description' in opt and 'value' in opt:
                    normalized.append((str(opt['description']), str(opt['value'])))
                else:
                    label = str(opt.get('description', opt.get('label', opt.get('name', ''))))
                    value = str(opt.get('value', opt.get('id', label)))
                    normalized.append((label, value))
            else:
                # For simple values, use same value for label and value
                normalized.append((str(opt), str(opt)))

        return normalized

    def on_mount(self) -> None:
        """Called when the widget is mounted"""
        # Les événements de checkbox seront gérés automatiquement par la méthode on_checkbox_changed

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes"""
        # Check if this is one of our checkboxes
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changed: {checkbox_id} -> {event.value}")

        for option_value, checkbox in self.checkboxes.items():
            if checkbox.id == checkbox_id:
                logger.debug(f"Found matching checkbox for option: {option_value}")

                # Update selected values
                if event.value and option_value not in self.selected_values:
                    self.selected_values.append(option_value)
                elif not event.value and option_value in self.selected_values:
                    self.selected_values.remove(option_value)

                logger.debug(f"Updated selected values: {self.selected_values}")
                break

    def get_value(self):
        """Return the list of selected values"""
        return self.selected_values
        
    def update_dynamic_options(self):
        """Met à jour les options dynamiques du champ"""
        new_options = self._get_options()
        
        # Si les options sont None ou vides, le champ doit être supprimé
        if new_options is None:
            logger.debug(f"Aucune option disponible pour {self.field_id}, le champ sera supprimé")
            self.options = []
            # Trouver le conteneur parent
            from .config_container import ConfigContainer
            parent = next((ancestor for ancestor in self.ancestors_with_self if isinstance(ancestor, ConfigContainer)), None)
            if parent:
                # Supprimer le champ du dictionnaire
                if self.field_id in parent.fields_by_id:
                    del parent.fields_by_id[self.field_id]
                # Supprimer le widget de l'interface
                self.remove()
            return
            
        # Mettre à jour les options
        self.options = new_options
        
        # Sauvegarder les valeurs sélectionnées qui sont toujours valides
        self.selected_values = [val for val in self.selected_values if any(opt[1] == val for opt in self.options)]
        
        # Supprimer les anciens checkboxes
        for checkbox in self.checkboxes.values():
            checkbox.remove()
        self.checkboxes.clear()
        
        # Créer les nouveaux checkboxes
        container = self.query_one('.checkbox-group-container')
        if container:
            # Supprimer le label "Aucune option disponible" s'il existe
            for label in container.query('.no-options-label'):
                label.remove()
                
            # Créer les nouveaux checkboxes
            for option_label, option_value in self.options:
                checkbox_id = f"checkbox_group_{self.source_id}_{self.field_id}_{option_value}".replace(".", "_")
                # Créer le groupe horizontal
                group = HorizontalGroup(classes="checkbox-group-item")
                # Monter d'abord le groupe dans le conteneur
                container.mount(group)
                # Créer la checkbox
                checkbox = Checkbox(
                    id=checkbox_id,
                    classes="field-checkbox-group-item",
                    value=option_value in self.selected_values
                )
                self.checkboxes[option_value] = checkbox
                # Créer le label
                label = Label(option_label, classes="checkbox-group-label")
                # Monter la checkbox et le label dans le groupe déjà monté
                group.mount(checkbox)
                group.mount(label)
