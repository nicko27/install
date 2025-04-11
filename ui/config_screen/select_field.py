from textual.app import ComposeResult
from textual.widgets import Select
from textual.containers import VerticalGroup, HorizontalGroup
import os
import importlib.util
import sys
import traceback
from typing import Any

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
        try:
            if 'options' in self.field_config:
                logger.debug(f"Using static options from config: {self.field_config['options']}")
                return self._normalize_options(self.field_config['options'])

            if 'dynamic_options' in self.field_config:
                dynamic_config = self.field_config['dynamic_options']
                
                # Vérifier que le script existe
                if 'script' not in dynamic_config:
                    logger.error(f"No script specified in dynamic_options for {self.field_id}")
                    return [("Error: No script specified", "error_no_script")]

                # Déterminer le chemin du script (plugin ou scripts)
                script_path = self._resolve_script_path(dynamic_config)
                if not os.path.exists(script_path):
                    logger.error(f"Script not found: {script_path}")
                    return [("Error: Script not found", "error_script_not_found")]

                logger.debug(f"Loading script from: {script_path}")

                try:
                    # Importer le module
                    module = self._import_script_module(script_path)
                    if not module:
                        logger.error("Failed to import script module")
                        return [("Error loading module", "error_loading_module")]

                    # Obtenir le nom de la fonction
                    func_name = self._get_function_name(module, dynamic_config)
                    if not func_name or not hasattr(module, func_name):
                        logger.error(f"Function not found: {func_name}")
                        return [("Error: Function not found", "error_function_not_found")]

                    logger.debug(f"Using function: {func_name}")

                    # Préparer les arguments
                    function_args = self._prepare_function_args(dynamic_config)
                    
                    # Appeler la fonction
                    logger.debug(f"Calling {func_name} with kwargs: {function_args}")
                    result = getattr(module, func_name)(**function_args)
                    logger.debug(f"Got result from {func_name}: {type(result)}")

                    # Traiter le résultat
                    options = self._process_dynamic_result(result, dynamic_config)
                    
                    # Vérifier que nous avons au moins une option
                    if not options:
                        logger.warning(f"No options generated from {func_name}")
                        return [("No data available", "no_data")]

                    logger.debug(f"Final options count: {len(options)}")
                    return options

                except Exception as e:
                    logger.error(f"Error loading dynamic options: {e}")
                    logger.error(traceback.format_exc())
                    return [(f"Error: {str(e)}", "script_exception")]

            # Par défaut si aucune option n'est définie
            logger.warning(f"No options defined for {self.field_id}")
            return [("No options defined", "no_options_defined")]
        except Exception as e:
            logger.error(f"Unexpected error in _get_options: {e}")
            logger.error(traceback.format_exc())
            return [("Error: Internal error", "internal_error")]
        
    def _resolve_script_path(self, dynamic_config: dict) -> str:
        """
        Résout le chemin du script en fonction de la configuration.
        
        Args:
            dynamic_config: Configuration dynamique du champ
            
        Returns:
            str: Chemin résolu du script
        """
        script_name = dynamic_config.get('script', '')
        
        # Vérifier si c'est un script global ou spécifique au plugin
        if dynamic_config.get('global', False):
            # Script dans le dossier scripts
            script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', script_name)
        else:
            # Déterminer le nom du plugin à partir de source_id
            plugin_name = self.source_id.split('_')[0] if '_' in self.source_id else self.source_id
            # Script dans le dossier du plugin
            script_path = os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', plugin_name, script_name)
        
        logger.debug(f"Resolved script path: {script_path}")
        return script_path

    def _import_script_module(self, script_path: str) -> Any:
        """
        Importe un module script à partir d'un chemin.
        
        Args:
            script_path: Chemin vers le script
            
        Returns:
            Any: Module importé ou None en cas d'erreur
        """
        try:
            # Ajouter le dossier contenant le script au path
            script_dir = os.path.dirname(script_path)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            
            # Importer le module
            spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
            if not spec:
                logger.error("Failed to create module spec")
                return None
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.error(f"Error importing script module: {e}")
            logger.error(traceback.format_exc())
            return None

    def _get_function_name(self, module: Any, dynamic_config: dict) -> str:
        """
        Récupère le nom de la fonction à appeler dans le module.
        
        Args:
            module: Module importé
            dynamic_config: Configuration dynamique
            
        Returns:
            str: Nom de la fonction ou None si non trouvée
        """
        # Utiliser la fonction spécifiée ou chercher une fonction commençant par 'get_'
        func_name = dynamic_config.get('function')
        if not func_name:
            logger.debug("No function name specified, looking for function starting with 'get_'")
            func_name = next((name for name in dir(module)
                        if name.startswith('get_') and callable(getattr(module, name))), None)
        
        logger.debug(f"Function name: {func_name}")
        return func_name

    def _prepare_function_args(self, dynamic_config: dict) -> dict:
        """
        Prépare les arguments à passer à la fonction.
        
        Args:
            dynamic_config: Configuration dynamique
            
        Returns:
            dict: Arguments à passer à la fonction
        """
        function_args = {}
        
        # Si pas d'arguments spécifiés, retourner un dictionnaire vide
        if 'args' not in dynamic_config:
            return function_args
        
        for arg in dynamic_config.get('args', []):
            # Si l'argument fait référence à un autre champ
            if 'field' in arg:
                field_id = arg['field']
                # Récupérer le champ
                field = self._get_field_by_id(field_id)
                if field:
                    # Récupérer la valeur du champ
                    field_value = self._get_field_value(field)
                    # Utiliser le nom de paramètre spécifié ou le nom du champ
                    param_name = arg.get('param_name', field_id.split('.')[-1])
                    function_args[param_name] = field_value
                    logger.debug(f"Added arg from field {field_id}: {param_name}={field_value}")
                else:
                    logger.warning(f"Field not found for arg: {field_id}")
            
            # Si l'argument est une valeur directe
            elif 'value' in arg:
                param_name = arg.get('param_name')
                if param_name:
                    function_args[param_name] = arg['value']
                    logger.debug(f"Added direct arg: {param_name}={arg['value']}")
        
        return function_args

    def _process_dynamic_result(self, result: Any, dynamic_config: dict) -> list:
        """
        Traite le résultat de la fonction dynamique.
        
        Args:
            result: Résultat de la fonction
            dynamic_config: Configuration dynamique
            
        Returns:
            list: Options normalisées
        """
        # Initialiser data comme None
        data = None
        
        # Traiter le résultat en fonction de son format
        if isinstance(result, tuple) and len(result) == 2:
            # Format (success, data)
            success, value = result
            
            if not success:
                logger.error(f"Dynamic options script returned failure: {value}")
                return [("Error: Script failed", "script_failed")]
            
            # Si c'est un succès, la valeur devient notre data
            data = value
        else:
            # Si le résultat n'est pas un tuple, le considérer directement comme data
            data = result
        
        logger.debug(f"Processing result of type: {type(data)}")
        
        # Traiter les différents formats de données
        if isinstance(data, list):
            # Si data est une liste, la normaliser directement
            return self._normalize_options(data)
        
        elif isinstance(data, dict):
            # Si data est un dictionnaire
            dict_key = dynamic_config.get('dict')
            if dict_key and dict_key in data:
                # Extraire les données via la clé spécifiée
                extracted_data = data[dict_key]
                logger.debug(f"Extracted data using key '{dict_key}'")
                
                if isinstance(extracted_data, list):
                    desc_key = dynamic_config.get('description', 'description')
                    value_key = dynamic_config.get('value', 'value')
                    
                    # Transformer la liste d'objets en options
                    options = []
                    for item in extracted_data:
                        if isinstance(item, dict):
                            if desc_key in item and value_key in item:
                                options.append((item[desc_key], item[value_key]))
                            else:
                                # Fallback: utiliser la première clé comme description et valeur
                                first_key = next(iter(item), None)
                                if first_key:
                                    options.append((str(first_key), str(item[first_key])))
                        else:
                            # Fallback: utiliser l'élément comme description et valeur
                            options.append((str(item), str(item)))
                    
                    return self._normalize_options(options)
                else:
                    logger.warning(f"Extracted data is not a list: {type(extracted_data)}")
            
            # Si pas de dict_key ou pas trouvé, traiter le dictionnaire entier
            dict_options = []
            for key, value in data.items():
                if isinstance(value, dict) and 'description' in value and 'value' in value:
                    dict_options.append((value['description'], value['value']))
                else:
                    dict_options.append((str(key), str(value)))
            
            return self._normalize_options(dict_options)
        
        # Pour tout autre type de données
        logger.warning(f"Unhandled data type: {type(data)}")
        return [("Invalid data format", "invalid_format")]

    def update_dynamic_options(self) -> None:
        """
        Met à jour les options dynamiques du champ.
        """
        try:
            logger.debug(f"Updating dynamic options for {self.field_id}")
            
            # Vérifier si le champ a des options dynamiques
            if 'dynamic_options' not in self.field_config:
                logger.debug(f"No dynamic options for {self.field_id}")
                return
            
            # Récupérer les nouvelles options
            new_options = self._get_options()
            if not new_options:
                logger.warning(f"No options returned for {self.field_id}")
                return
            
            # Mettre à jour les options
            old_value = self.value
            old_options = getattr(self, 'options', [])
            
            # Récupérer les valeurs disponibles
            new_values = [opt[1] for opt in new_options]
            
            # Mettre à jour le widget Select
            try:
                # Mettre à jour les options du widget
                self.options = new_options
                
                # Vérifier si l'ancienne valeur est toujours valide
                if old_value in new_values:
                    logger.debug(f"Keeping current value: {old_value}")
                    self.value = old_value
                else:
                    # Essayer une correspondance partielle
                    match_found = False
                    for option_value in new_values:
                        if option_value.startswith(str(old_value)) or str(old_value).startswith(option_value.split('.')[0]):
                            logger.debug(f"Found partial match for {old_value}: {option_value}")
                            self.value = option_value
                            match_found = True
                            break
                    
                    # Si aucune correspondance, utiliser la première valeur
                    if not match_found and new_values:
                        logger.debug(f"No match found for {old_value}, using first available: {new_values[0]}")
                        self.value = new_values[0]
                
                # Mettre à jour le widget
                if hasattr(self, 'select'):
                    self.select.options = self.options
                    self.select.value = self.value
                    logger.debug(f"Select widget updated with {len(self.options)} options")
                
                # Notifier les dépendances du changement
                self._notify_dependencies()
                
            except Exception as e:
                logger.error(f"Error updating Select widget: {e}")
                logger.error(traceback.format_exc())
            
        except Exception as e:
            logger.error(f"Error in update_dynamic_options: {e}")
            logger.error(traceback.format_exc())

    def on_select_changed(self, event: Select.Changed) -> None:
        """
        Gère l'événement de changement de sélection.
        
        Args:
            event: Événement de changement
        """
        try:
            # Eviter les mises à jour en boucle
            if self._updating_widget:
                return
            
            logger.debug(f"Select changed for {self.field_id}: {event.value}")
            
            # Mettre à jour la valeur
            self._value = event.value
            
            # Obtenir le parent pour mettre à jour les dépendances
            parent = self._get_parent_container()
            if parent and hasattr(parent, 'update_dependent_fields'):
                logger.debug(f"Notifying parent container of change in {self.field_id}")
                parent.update_dependent_fields(self)
            else:
                logger.warning(f"Pas de conteneur parent avec update_dependent_fields trouvé pour {self.field_id}")
                # Tenter de notifier les dépendances directement
                self._notify_dependencies()
        except Exception as e:
            logger.error(f"Error handling select change: {e}")
            logger.error(traceback.format_exc())

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

    def get_value(self) -> str:
        """Get the current value"""
        # Filter out special error/fallback values
        if self.value in ["no_options", "placeholder", "fallback", "error_loading",
                        "function_not_found", "script_error", "invalid_format",
                        "no_data", "script_exception", "no_options_defined"]:
            return ""
        return self.value