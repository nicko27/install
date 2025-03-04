from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, Select
import os
import importlib.util

from ..utils import setup_logging

logger = setup_logging()

class ConfigField(VerticalGroup):
    """Base class for configuration fields"""
    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        super().__init__()
        self.source_id = source_id         # ID de la source (plugin ou config globale)
        self.field_id = field_id           # ID du champ
        self.field_config = field_config   # Configuration du champ
        self.fields_by_id = fields_by_id or {}  # Champs indexés par ID pour les dépendances
        self.is_global = is_global         # Indique si c'est un champ global ou plugin

        # Check if the field has an enabled_if dependency
        if 'enabled_if' in field_config:
            self.enabled_if = field_config['enabled_if']
        else:
            self.enabled_if = None
        self.variable_name = field_config.get('variable', field_id)

        # Handle default value (static, dynamic or dependent)
        if ('depends_on' in field_config and 'values' in field_config) or \
           ('dynamic_default' in field_config and 'script' in field_config['dynamic_default']):
            self.value = self._get_dynamic_default()
        else:
            self.value = field_config.get('default', None)

    def _get_dynamic_default(self) -> str:
            """Get dynamic default value based on another field's value or a script"""
            logger.info(f"Attempting to get dynamic default for field: {self.field_id}")
            logger.info(f"Field config: {self.field_config}")

            # If the field depends on another field
            if 'depends_on' in self.field_config and 'values' in self.field_config:
                depends_on = self.field_config['depends_on']
                if depends_on in self.fields_by_id:
                    dependent_field = self.fields_by_id[depends_on]
                    dependent_value = dependent_field.get_value()
                    values = self.field_config['values']
                    if dependent_value in values:
                        return values[dependent_value]

            # Handle dynamic values via script
            if 'dynamic_default' in self.field_config and 'script' in self.field_config['dynamic_default']:
                script_name = self.field_config['dynamic_default']['script']
                try:
                    import importlib.util

                    # Determine script path (global or plugin)
                    if self.field_config['dynamic_default'].get('global', False):
                        # Script in utils folder
                        script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', script_name)
                    else:
                        # Script in plugin folder
                        script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.source_id, script_name)

                    logger.info(f"Loading script from: {script_path}")
                    spec = importlib.util.spec_from_file_location("dynamic_default_module", script_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    function_name = self.field_config['dynamic_default'].get('function', 'get_default_value')
                    if hasattr(module, function_name):
                        result = getattr(module, function_name)()
                        logger.info(f"Dynamic default value obtained: {result}")

                        # 1. Handle tuple returns (status, value)
                        if isinstance(result, tuple) and len(result) == 2:
                            success, value = result

                            # 1.1 If success, check if value is a dict with value_key
                            if success and isinstance(value, dict):
                                value_key = self.field_config['dynamic_default'].get('value_key')
                                if value_key and value_key in value:
                                    return str(value[value_key])

                                # 1.2 If no value_key specified, use the first value in dict
                                if value:
                                    return str(list(value.values())[0])

                            # 1.3 If success but value is not a dict, return the value as string
                            elif success:
                                return str(value)

                            # 1.4 If not success, log warning and return empty string
                            else:
                                logger.warning(f"Dynamic script returned error: {value}")
                                return ''

                        # 2. Handle direct dictionary returns
                        elif isinstance(result, dict):
                            value_key = self.field_config['dynamic_default'].get('value_key')
                            if value_key and value_key in result:
                                return str(result[value_key])

                            # If no value_key specified, use the first value
                            if result:
                                return str(list(result.values())[0])

                        # 3. Handle any other return type by converting to string
                        return str(result) if result is not None else ''
                    else:
                        logger.error(f"Function {function_name} not found in {script_name}")
                        return ''
                except FileNotFoundError:
                    logger.error(f"Script not found: {script_path}")
                    return ''
                except ImportError as e:
                    logger.error(f"Import error: {e}")
                    return ''
                except Exception as e:
                    logger.error(f"Error executing dynamic script {script_path}: {e}")
                    return ''

            # Default value if no dependency or value not found
            default = self.field_config.get('default', '')
            logger.info(f"Returning default value: {default}")
            return str(default) if default is not None else ''

    def compose(self) -> ComposeResult:
        label = self.field_config.get('label', self.field_id)

        with HorizontalGroup():
            yield Label(label, classes="field-label")
            if self.field_config.get('required', False):
                yield Label("*", classes="required-star")

        # Check if field should be enabled or not
        if self.enabled_if:
            dep_field = self.fields_by_id.get(self.enabled_if['field'])
            logger.debug(f"Field {self.field_id}: enabled_if={self.enabled_if}, dep_field={dep_field and dep_field.field_id}, dep_value={dep_field and dep_field.value}")
            if dep_field and dep_field.value != self.enabled_if['value']:
                logger.debug(f"Field {self.field_id} should be initially disabled")
                self.disabled = True
                self.add_class('disabled')

    def get_value(self):
        return self.value

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select change"""
        if event.select.id == f"select_{self.source_id}_{self.field_id}":
            # Ensure value is a string
            self.value = str(event.value) if event.value is not None else ""

            # Update fields that depend on this one
            for field_id, field in self.fields_by_id.items():
                if field.field_config.get('depends_on') == self.field_id:
                    field.value = field._get_dynamic_default()
                    if hasattr(field, 'input'):
                        # Ensure value is a string before assigning to input
                        field.input.value = str(field.value) if field.value is not None else ""
                    elif hasattr(field, 'select'):
                        field.select.value = field.value