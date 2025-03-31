from textual.app import ComposeResult
from textual.widgets import Select
from textual.containers import VerticalGroup, HorizontalGroup
import os
import importlib.util
import sys
import traceback

from .config_field import ConfigField
from ..utils.logging import get_logger

logger = get_logger('select_field')

class SelectField(ConfigField):
    """Select field with options"""

    def __init__(self, source_id: str, field_id: str, field_config: dict, fields_by_id: dict = None, is_global: bool = False):
        super().__init__(source_id, field_id, field_config, fields_by_id, is_global)
        self.add_class("field-type-select")  # Ajouter une classe spécifique pour le type de champ
        # Initialize _value attribute for the property
        self._value = self.field_config.get('default', None)

    def compose(self) -> ComposeResult:
        # Render label and any other common elements
        yield from super().compose()

        # Get options in format accepted by Textual Select
        self.options = self._get_options()
        if not self.options:
            logger.warning(f"No options available for select {self.field_id}")
            self.options = [("No options available", "no_options")]

        # Debug info
        logger.info(f"Field {self.field_id} options: {self.options}")

        # Extract the actual values from options (second element in each tuple)
        available_values = [opt[1] for opt in self.options]

        # Check if current value is valid, otherwise set default
        if not self.value:
            # No value set, use default
            if available_values:
                self.value = available_values[0]
                logger.info(f"Setting default value for {self.field_id}: {self.value}")
            else:
                logger.error(f"No valid values available for {self.field_id}")
                # Add a fallback option
                placeholder_option = ("Placeholder", "placeholder")
                self.options.append(placeholder_option)
                self.value = "placeholder"
        elif str(self.value) not in available_values:
            # Try partial matching
            match_found = False
            for option_value in available_values:
                if option_value.startswith(str(self.value)) or str(self.value).startswith(option_value.split('.')[0]):
                    logger.info(f"Found partial match for {self.field_id}: {option_value} (from {self.value})")
                    self._value = option_value  # Update stored value to match what's actually available
                    match_found = True
                    break

            # If no match found, set default
            if not match_found:
                if available_values:
                    logger.warning(f"No match found for {self.value} in {self.field_id}, using first available: {available_values[0]}")
                    self.value = available_values[0]
                else:
                    logger.error(f"No valid values available for {self.field_id}")
                    # Add a fallback option
                    placeholder_option = ("Placeholder", "placeholder")
                    self.options.append(placeholder_option)
                    self.value = "placeholder"

        # Create a container for the select widget
        with VerticalGroup(classes="field-input-container select-container"):
            try:
                self.select = Select(
                    options=self.options,
                    value=self.value,
                    id=f"select_{self.field_id}",
                    classes="field-select",
                    allow_blank=self.field_config.get('allow_blank', False)
                )
            except Exception as e:
                logger.exception(f"Error creating Select widget: {e}")
                # Fallback in case of error
                basic_options = [("No valid options", "fallback")]
                self.select = Select(
                    options=basic_options,
                    value="fallback",
                    id=f"select_{self.field_id}",
                    classes="field-select error-select"
                )

            # Always initialize to enabled state first
            self.select.disabled = False
            self.select.remove_class('disabled')

            if self.disabled:
                logger.debug(f"SelectField {self.field_id} is initially disabled")
                self.select.disabled = True
                self.select.add_class('disabled')

            yield self.select

    def _normalize_options(self, options: list) -> list:
        """
        Normalize options to format expected by Textual Select widget: (label, value)
        The value must be a string and must be unique.
        """
        normalized = []
        for opt in options:
            if isinstance(opt, (list, tuple)):
                # If it's already a tuple/list, make sure it has 2 elements
                if len(opt) >= 2:
                    # Format for Textual: (label, value)
                    normalized.append((str(opt[0]), str(opt[1])))
                else:
                    # Use the element as both label and value
                    normalized.append((str(opt[0]), str(opt[0])))
            elif isinstance(opt, dict):
                # For dictionaries with description and value
                if 'description' in opt and 'value' in opt:
                    normalized.append((str(opt['description']), str(opt['value'])))
                # For other dictionary formats
                else:
                    label = str(opt.get('description', opt.get('label', opt.get('title', opt.get('name', '')))))
                    value = str(opt.get('value', opt.get('id', label)))
                    normalized.append((label, value))
            else:
                # For simple values, use same value for label and value
                normalized.append((str(opt), str(opt)))

        # Ensure no duplicate values
        seen_values = set()
        unique_options = []
        for label, value in normalized:
            if value not in seen_values:
                seen_values.add(value)
                unique_options.append((label, value))
            else:
                # If duplicate value, make it unique by appending a suffix
                i = 1
                while f"{value}_{i}" in seen_values:
                    i += 1
                unique_value = f"{value}_{i}"
                seen_values.add(unique_value)
                unique_options.append((label, unique_value))

        return unique_options

    def _get_options(self) -> list:
        """Get options for the select field, either static or dynamic"""
        if 'options' in self.field_config:
            logger.debug(f"Using static options from config: {self.field_config['options']}")
            return self._normalize_options(self.field_config['options'])

        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']

            # Déterminer le chemin du script (plugin ou scripts)
            if dynamic_config.get('global', False):
                # Script dans le dossier scripts
                script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', dynamic_config['script'])
            else:
                # Script dans le dossier du plugin
                script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', self.source_id, dynamic_config['script'])

            logger.info(f"Loading script from: {script_path}")
            logger.debug(f"Script exists: {os.path.exists(script_path)}")

            try:
                # Import the script module
                import sys
                import importlib.util
                sys.path.append(os.path.dirname(script_path))
                logger.debug(f"Python path: {sys.path}")

                spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
                if not spec:
                    logger.error("Failed to create module spec")
                    # Return a safe option
                    return [("Error loading module", "error_loading")]

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Get the function name
                func_name = dynamic_config.get('function')
                if not func_name:
                    # Try to find a function that starts with get_
                    func_name = next((name for name in dir(module)
                                if name.startswith('get_') and callable(getattr(module, name))), None)

                if not func_name or not hasattr(module, func_name):
                    logger.error(f"Function {func_name} not found in script")
                    # Return a safe option
                    return [("Function not found", "function_not_found")]

                logger.debug(f"Using function: {func_name}")

                # Préparer les arguments à passer à la fonction
                function_args = {}
                if 'args' in dynamic_config:
                    for arg in dynamic_config['args']:
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

                # Call the function with arguments
                logger.debug(f"Calling {func_name} with kwargs: {function_args}")
                result = getattr(module, func_name)(**function_args)
                logger.info(f"Got result from {func_name}: {result}")

                # Initialiser data comme None
                data = None

                # Process the result based on its format
                if isinstance(result, tuple) and len(result) == 2:
                    success, value = result

                    if not success:
                        logger.error(f"Dynamic options script failed: {value}")
                        # Return a safe option
                        return [("Script error", "script_error")]

                    # Si c'est un succès, la valeur devient notre data
                    data = value

                    # If data is a dict with a value_key, use that
                    if isinstance(data, dict) and dynamic_config.get('dict') in data:
                        data = data[dynamic_config.get('dict')]
                        logger.info(f"Extracted data using dict_key '{dynamic_config.get('dict')}': {data}")
                        dict_options = []
                        for elt  in data:
                            # Si la valeur est un dictionnaire avec description/value, l'utiliser
                            if isinstance(elt, dict) and dynamic_config.get('description') in elt and dynamic_config.get('value') in elt:
                                dict_options.append((elt.get(dynamic_config.get('description')),elt.get(dynamic_config.get('value'))))
                            elif isinstance(elt, dict) and "description" in elt and "value" in elt:
                                dict_options.append((elt.get('description'),elt.get('value')))
                            else:
                                # Sinon créer un tuple (clé, valeur)
                                dict_options.append((str(key), str(value)))
                        options = self._normalize_options(dict_options)
                else:
                    # Si le résultat n'est pas un tuple, on le considère directement comme data
                    data = result

                logger.info(f"Processed data type: {type(data)} for options")

                # Traiter les différents formats de données possibles
                options = []

                # Si data est une liste, on la normalise directement
                if isinstance(data, list):
                    logger.info(f"Processing list data: {data}")
                    options = self._normalize_options(data)

                # Si data est un dictionnaire sans value_key spécifié, on convertit en liste d'options
                elif isinstance(data, dict) and not dynamic_config.get('value'):
                    if 'dict' in dynamic_config.keys():
                        data = data[dynamic_config.get('dict')]
                    logger.info(f"Processing dictionary data without value_key: {data}")
                    # Transformer le dictionnaire en liste pour normalisation
                    dict_options = []
                    for key, value in data.items():
                        # Si la valeur est un dictionnaire avec description/value, l'utiliser
                        if isinstance(value, dict) and 'description' in value and 'value' in value:
                            dict_options.append(value)
                        else:
                            # Sinon créer un tuple (clé, valeur)
                            dict_options.append((str(key), str(value)))
                    options = self._normalize_options(dict_options)

                # Si ce n'est ni une liste ni un dictionnaire exploitable, on log une erreur
                else:
                    logger.error(f"Cannot process data of type: {type(data)}, data: {data}")
                    # Return a safe option
                    return [("Invalid data format", "invalid_format")]

                # Ensure we have at least one option
                if not options:
                    logger.warning("No options generated from data")
                    return [("No data available", "no_data")]

                logger.info(f"Final normalized options: {options}")
                return options

            except Exception as e:
                logger.error(f"Error loading dynamic options: {e}")
                logger.exception("Traceback:"+traceback.format_exc())
                # Return a safe option
                return [(f"Error: {str(e)}", "script_exception")]

        # Fallback if no options defined
        return [("No options defined", "no_options_defined")]

    # Ajouter un flag spécifique pour surveiller les mises à jour du widget Select
    _updating_widget = False
    
    def set_value(self, value: str, update_input: bool = True, update_dependencies: bool = True) -> bool:
        """Méthode standard pour tous les champs qui définit la valeur"""
        logger.debug(f"🔎 set_value({value}) pour {self.field_id}, update_input={update_input}, update_dependencies={update_dependencies}")
        
        # 1. Vérification si la valeur est la même (évite les oscillations)
        if hasattr(self, '_value') and self._value == value:
            logger.debug(f"✓ Valeur déjà définie à '{value}' pour {self.field_id}, aucune action nécessaire")
            return True
        
        # 2. Stockage de la valeur interne
        self._value = value
        
        # 3. Mise à jour du widget si demandé et disponible
        if update_input and hasattr(self, 'select') and not self._updating_widget:
            try:
                # Marquer que nous mettons à jour le widget pour éviter les cycles
                self._updating_widget = True
                
                # Vérifier que la valeur existe dans les options
                available_values = [opt[1] for opt in self.options]
                
                # Cas 1: Correspondance exacte
                if value in available_values:
                    logger.debug(f"✓ Valeur '{value}' trouvée dans les options pour {self.field_id}")
                    if self.select.value != value:
                        logger.debug(f"Mise à jour du widget select pour {self.field_id}: '{self.select.value}' → '{value}'")
                        self.select.value = value
                # Cas 2: Correspondance partielle (ex: 'KM227' correspondant à 'KM227.yml')
                else:
                    found = False
                    for option_value in available_values:
                        # Vérifier si la valeur commence par notre recherche ou l'inverse
                        prefix_match = option_value.startswith(value) 
                        base_match = value.startswith(option_value.split('.')[0])
                        
                        if prefix_match or base_match:
                            # Seulement mettre à jour si nécessaire
                            if self.select.value != option_value:
                                logger.debug(f"Correspondance partielle pour {self.field_id}: '{value}' → '{option_value}'")
                                self.select.value = option_value
                            found = True
                            break
                    
                    if not found:
                        logger.warning(f"⚠️ Valeur '{value}' non trouvée dans les options pour {self.field_id}")
            finally:
                # Toujours réinitialiser le flag
                self._updating_widget = False
        
        # 4. Mise à jour des dépendances si demandé
        if update_dependencies:
            from .config_container import ConfigContainer
            parent = next((a for a in self.ancestors_with_self if isinstance(a, ConfigContainer)), None)
            if parent:
                logger.debug(f"Mise à jour des dépendances pour {self.field_id} avec '{value}'")
                parent.update_dependent_fields(self)
        
        return True
    
    # Property getter/setter pour la manipulation via self.value
    @property
    def value(self):
        """Récupère la valeur actuelle, priorité au widget s'il existe"""
        if hasattr(self, 'select'):
            return self.select.value
        return self._value if hasattr(self, '_value') else None

    @value.setter
    def value(self, new_value):
        """Définit la valeur via la méthode set_value standard"""
        # Utiliser la méthode standard pour éviter la duplication de code
        self.set_value(new_value)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Gestionnaire d'événement quand le select change de valeur"""
        if event.select.id == f"select_{self.field_id}":
            # Si nous sommes déjà en train de mettre à jour le widget, ignorer l'événement
            if self._updating_widget:
                logger.debug(f"⚠️ Ignorer l'événement on_select_changed pendant la mise à jour du widget pour {self.field_id}")
                return
                
            # Vérifier si la valeur est différente de celle stockée
            if hasattr(self, '_value') and self._value == event.value:
                logger.debug(f"✓ On_select_changed: valeur inchangée pour {self.field_id}: {event.value}")
                return
                
            # Valeur différente, mettre à jour via set_value
            logger.debug(f"On_select_changed: valeur modifiée pour {self.field_id}: {event.value}")
            self.set_value(event.value, update_input=False)  # Ne pas mettre à jour le widget qui vient de changer

    def get_value(self) -> str:
        """Get the current value"""
        # Filter out special error/fallback values
        if self.value in ["no_options", "placeholder", "fallback", "error_loading",
                        "function_not_found", "script_error", "invalid_format",
                        "no_data", "script_exception", "no_options_defined"]:
            return ""
        return self.value