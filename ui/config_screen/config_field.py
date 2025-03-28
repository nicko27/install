from textual.app import ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup
from textual.widgets import Label, Select
import os

from ..utils.logging import get_logger

logger = get_logger('config_field')

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
            # Store the original default value for later use
            self._original_default = field_config.get('default')
        else:
            self.enabled_if = None
            self._original_default = None
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

                    # Determine script path (custom path, global, or plugin)
                    if 'path' in self.field_config['dynamic_default']:
                        # Utiliser le chemin personnalisé
                        path = self.field_config['dynamic_default']['path']

                        # Gérer la syntaxe @[directory]
                        if path.startswith('@[') and path.endswith(']'):
                            dir_name = path[2:-1]  # Extraire le nom du répertoire entre @[ et ]
                            if dir_name == 'scripts':
                                script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
                            else:
                                # Chemin absolu pour d'autres répertoires
                                script_path = os.path.join(os.path.dirname(__file__), '..', '..', dir_name, script_name)
                        else:
                            # Chemin absolu ou relatif spécifié directement
                            script_path = os.path.join(path, script_name) if not os.path.isabs(path) else os.path.join(path, script_name)
                    elif self.field_config['dynamic_default'].get('global', False):
                        # Script in utils folder
                        script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
                    else:
                        # Script in plugin folder
                        script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.source_id, script_name)

                    logger.info(f"Loading script from: {script_path}")
                    spec = importlib.util.spec_from_file_location("dynamic_default_module", script_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    # Préparer les arguments à passer à la fonction
                    function_args = {}
                    if 'args' in self.field_config['dynamic_default']:
                        for arg in self.field_config['dynamic_default']['args']:
                            # Si l'argument fait référence à un autre champ
                            if 'field' in arg:
                                field_id = arg['field']
                                if field_id in self.fields_by_id:
                                    field_value = self.fields_by_id[field_id].get_value()
                                    param_name = arg.get('param_name', field_id)
                                    function_args[param_name] = field_value
                            # Si l'argument est une valeur directe
                            elif 'value' in arg:
                                param_name = arg.get('param_name')
                                if param_name:
                                    function_args[param_name] = arg['value']
                    function_name = self.field_config['dynamic_default'].get('function', 'get_default_value')
                    if hasattr(module, function_name):
                        result = getattr(module, function_name)()
                        logger.info(f"Dynamic default value obtained: {result}")

                        # 1. Handle tuple returns (status, value)
                        if isinstance(result, tuple) and len(result) == 2:
                            success, value = result

                            # 1.1 If success, check if value is a dict with value_key
                            if success and isinstance(value, dict):
                                value_key = self.field_config['dynamic_default'].get('value')
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
                            value_key = self.field_config['dynamic_default'].get('value')
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

        with HorizontalGroup(classes="field-header", id=f"header_{self.field_id}"):
            if self.field_config.get('required', False):
                yield Label(f"{label} *", classes="field-label required-field")
            else:
                yield Label(label, classes="field-label")

        # Check if field should be enabled or not
        if self.enabled_if:
            dep_field = self.fields_by_id.get(self.enabled_if['field'])
            logger.debug(f"Field {self.field_id}: enabled_if={self.enabled_if}, dep_field={dep_field and dep_field.field_id}, dep_value={dep_field and dep_field.value}")

            # Check if the dependency field exists
            if dep_field:
                # Récupérer les valeurs pour la comparaison
                field_value = dep_field.value
                required_value = self.enabled_if.get('value')

                # Convertir les valeurs en booléens si nécessaire pour la comparaison
                if isinstance(required_value, bool) and not isinstance(field_value, bool):
                    if isinstance(field_value, str):
                        field_value = field_value.lower() in ('true', 't', 'yes', 'y', '1')
                    else:
                        field_value = bool(field_value)

                logger.debug(f"Comparaison pour {self.field_id}: {field_value} == {required_value}")

                # Check if the dependency field's value matches the required value
                if field_value != required_value:
                    logger.debug(f"Field {self.field_id} should be initially disabled")
                    self.disabled = True
                    self.add_class('disabled')
                else:
                    # If the field should be enabled, make sure it's not disabled
                    logger.debug(f"Field {self.field_id} should be initially enabled")
                    self.disabled = False
                    self.remove_class('disabled')
            else:
                # If the dependency field doesn't exist yet (e.g., remote execution checkbox not yet created)
                # Use the default value from the field configuration
                logger.debug(f"Dependency field {self.enabled_if['field']} not found for {self.field_id}, using default state")

                # Default to disabled if the enabled_if condition exists but the dependency field doesn't
                # This is safer as the field will be enabled when the dependency is satisfied
                self.disabled = True
                self.add_class('disabled')

    def get_value(self):
        """Get the current value of the field"""
        return self.value
        
    def update_dynamic_options(self):
        """Met à jour les options dynamiques du champ"""
        # Cette méthode est destinée à être surchargée par les classes filles
        # qui ont des options dynamiques (SelectField, CheckboxGroupField, etc.)
        pass

    def set_value(self, value):
        """Set the value of the field"""
        self.value = value
        return True

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