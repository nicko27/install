from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer, HorizontalGroup, VerticalGroup
from textual.widgets import Label, Header, Footer, Button, Input, Checkbox, Select
from textual.widget import Widget
from textual.reactive import reactive
import os
from ruamel.yaml import YAML

from .utils import setup_logging
from .choice import get_plugin_folder_name

logger = setup_logging()

class ConfigField(VerticalGroup):
    """Base class for configuration fields"""
    def __init__(self, plugin_path: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__()
        self.plugin_path = plugin_path
        self.field_id = field_id
        self.field_config = field_config
        self.fields_by_id = fields_by_id or {}
        self.disabled = False  # Attribut pour suivre l'état disabled
        self.needs_refresh_when_enabled = False  # Nouveau: indique si le champ a besoin d'être rafraîchi lorsqu'il est activé
        
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
                
    def _update_dependent_fields(self, old_value):
        """Met à jour tous les champs qui dépendent de ce champ"""
        # Ne rien faire si la valeur n'a pas changé et qu'old_value n'est pas None
        if old_value is not None and old_value == self.value:
            logger.info(f"No value change detected for {self.field_id}, skipping dependent field updates")
            return
        
        logger.info(f"Updating fields that depend on {self.field_id}" + 
                    (f" after change from '{old_value}' to '{self.value}'" if old_value is not None else ""))
        
        # IMPORTANT: Afficher explicitement toutes les clés et dépendances pour le débogage
        logger.debug(f"fields_by_id contains {len(self.fields_by_id)} fields: {sorted(list(self.fields_by_id.keys()))}")
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'field_config') and 'depends_on' in field.field_config:
                logger.debug(f"Field {field_id} depends_on: {field.field_config['depends_on']}")
        
        # SOLUTION: Forcer spécifiquement la mise à jour de user_select si home_src_dir a changé
        if self.field_id == 'home_src_dir' and 'user_select' in self.fields_by_id:
            user_select = self.fields_by_id['user_select']
            logger.info(f"FORCING update of user_select options for new home_dir={self.value}")
            
            if hasattr(user_select, 'refresh_options'):
                try:
                    user_select.refresh_options()
                    logger.info("Successfully refreshed user_select options")
                except Exception as e:
                    logger.error(f"Error refreshing user_select options: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.error("user_select has no refresh_options method")
        
        # Mettre à jour tous les champs dépendants (approche générale)
        updated_fields = []
        
        for field_id, field in self.fields_by_id.items():
            # 1. Vérifier les champs qui dépendent de ce champ pour les valeurs par défaut
            depends_on_current = False
            
            # Vérifier différentes façons de spécifier la dépendance
            if hasattr(field, 'field_config'):
                depends_on = field.field_config.get('depends_on')
                if depends_on == self.field_id:
                    depends_on_current = True
                    logger.info(f"Found dependent field {field_id} to update (via field_config.depends_on)")
            
            if depends_on_current:
                # Important: Si le champ est désactivé, il faut quand même mettre à jour ses options
                # pour qu'elles soient prêtes lorsque le champ sera activé
                if hasattr(field, 'disabled') and field.disabled:
                    logger.info(f"Field {field_id} is disabled but updating its options anyway")
                
                # Recalculer la valeur par défaut
                old_field_value = field.value
                new_value = field._get_dynamic_default()
                logger.info(f"Updating dependent field {field_id} value: '{old_field_value}' -> '{new_value}'")
                
                # Mettre à jour la valeur et le widget
                field.value = new_value
                if hasattr(field, 'input'):
                    field.input.value = new_value
                    logger.debug(f"Updated input widget for {field_id}")
                elif hasattr(field, 'select'):
                    field.select.value = new_value
                    logger.debug(f"Updated select widget for {field_id}")
                elif hasattr(field, 'checkbox'):
                    field.checkbox.value = bool(new_value)
                    logger.debug(f"Updated checkbox widget for {field_id}")
                
                # Si le champ a des options dynamiques, les rafraîchir
                if hasattr(field, 'refresh_options'):
                    logger.info(f"Refreshing options for dependent field {field_id}")
                    try:
                        field.refresh_options()
                        logger.info(f"Successfully refreshed options for {field_id}")
                    except Exception as e:
                        logger.error(f"Error refreshing options for {field_id}: {e}")
                
                updated_fields.append(field_id)
            
            # 2. Vérifier les champs qui sont conditionnellement activés/désactivés
            if hasattr(field, 'enabled_if') and field.enabled_if and field.enabled_if.get('field') == self.field_id:
                logger.info(f"Updating enabled state for field {field_id}")
                # Mettre à jour l'état enabled/disabled
                field.update_enabled_state()
                updated_fields.append(field_id)
        
        if updated_fields:
            logger.info(f"Updated {len(updated_fields)} dependent fields: {', '.join(updated_fields)}")
        else:
            logger.info(f"No dependent fields updated for {self.field_id}")
            
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
                script_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', self.plugin_path, script_name)
                spec = importlib.util.spec_from_file_location("dynamic_default_module", script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                function_name = self.field_config['dynamic_default'].get('function', 'get_default_value')
                if hasattr(module, function_name):
                    default_value = getattr(module, function_name)()
                    logger.info(f"Dynamic default value obtained: {default_value}")
                    return default_value
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
        return default

    def _get_dynamic_options(self, dynamic_config):
        """
        Fonction commune pour obtenir les options dynamiques à partir d'un script.
        
        Args:
            dynamic_config (dict): Configuration des options dynamiques
            
        Returns:
            list: Liste d'options normalisées au format [(label, value), ...]
        """
        logger.info(f"Getting dynamic options for field {self.field_id}")
        
        if not dynamic_config:
            logger.error("Configuration des options dynamiques invalide")
            return [("Configuration invalide", "error")]
        
        # Le fichier et la fonction à appeler
        script_path = dynamic_config.get('script')
        function_name = dynamic_config.get('function')
        
        if not script_path:
            logger.error("Aucun script spécifié dans dynamic_options")
            return [("Script non spécifié", "error")]
        
        # Vérifier si c'est un script global (dans utils)
        is_global_script = dynamic_config.get('global', False)
        
        # Vérifier si le chemin contient une extension .py, sinon l'ajouter
        if not script_path.endswith('.py'):
            script_path += '.py'
        
        # Construire le chemin complet du fichier
        if is_global_script:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', 'utils', script_path)
            logger.info(f"Using global script from utils: {script_path}")
        else:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', self.plugin_path, script_path)
            logger.info(f"Using plugin-specific script: {script_path}")
        
        logger.info(f"Full script path: {script_full_path}")
        
        try:
            # Import the script module
            import sys
            import importlib.util
            
            # Important: Recharger le module pour être sûr d'avoir les données les plus récentes
            # Nous utilisons importlib.reload si le module est déjà dans sys.modules
            module_name = os.path.splitext(os.path.basename(script_path))[0]
            full_module_name = f"dynamic_script_{module_name}_{self.field_id}"
            
            # Assurer que le chemin du script est dans sys.path
            script_dir = os.path.dirname(script_full_path)
            if script_dir not in sys.path:
                sys.path.append(script_dir)
            
            # Toujours charger une nouvelle instance du module pour éviter la mise en cache
            logger.debug(f"Loading module {module_name} from {script_full_path}")
            spec = importlib.util.spec_from_file_location(full_module_name, script_full_path)
            if not spec:
                logger.error(f"Failed to create module spec for {script_full_path}")
                return [("Error loading module", "error")]
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.debug(f"Module {module_name} loaded successfully")
            
            # Déterminer la fonction à appeler
            # 1. Utiliser la fonction spécifiée dans la configuration si elle existe
            # 2. Sinon, trouver une fonction qui commence par 'get_'
            if not function_name:
                function_name = next((name for name in dir(module) 
                            if name.startswith('get_') and callable(getattr(module, name))), None)
                    
            if not function_name:
                logger.error(f"No suitable function found in {script_path}")
                return [("No function found", "error")]
                
            logger.debug(f"Using function: {function_name}")
            func = getattr(module, function_name)
            
            # Préparer les arguments
            args = []
            kwargs = {}
            for arg_config in dynamic_config.get('args', []):
                if isinstance(arg_config, dict):
                    if 'field' in arg_config:
                        field_id = arg_config['field']
                        if field_id in self.fields_by_id:
                            field_value = self.fields_by_id[field_id].get_value()
                            # Si un nom de paramètre est spécifié, utiliser un argument nommé
                            if 'param_name' in arg_config:
                                param_name = arg_config['param_name']
                                kwargs[param_name] = field_value
                                logger.debug(f"Using named parameter {param_name}={field_value}")
                            else:
                                args.append(field_value)
                                logger.debug(f"Using positional parameter: {field_value}")
                        else:
                            logger.warning(f"Field {field_id} not found for argument")
                    elif 'value' in arg_config:
                        arg_value = arg_config['value']
                        # Si un nom de paramètre est spécifié, utiliser un argument nommé
                        if 'param_name' in arg_config:
                            param_name = arg_config['param_name']
                            kwargs[param_name] = arg_value
                            logger.debug(f"Using named value parameter {param_name}={arg_value}")
                        else:
                            args.append(arg_value)
                            logger.debug(f"Using positional value parameter: {arg_value}")
                else:
                    # Si c'est directement une valeur
                    args.append(arg_config)
                    logger.debug(f"Using direct positional parameter: {arg_config}")
            
            logger.info(f"Calling {function_name} with args: {args}, kwargs: {kwargs}")
            
            # Appeler la fonction avec les arguments préparés
            result = func(*args, **kwargs)
            
            # La fonction doit retourner (success, data)
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
                success, data = result
                if not success:
                    logger.error(f"Function {function_name} returned error: {data}")
                    return [("Error: " + str(data), "error")]
                
                logger.info(f"Successfully retrieved data from {function_name}")
                if isinstance(data, list):
                    logger.info(f"Got {len(data)} items from {function_name}")
                elif isinstance(data, dict):
                    logger.info(f"Got {len(data)} keys from {function_name}")
                else:
                    logger.info(f"Got data of type {type(data).__name__} from {function_name}")
            else:
                logger.error(f"Function {function_name} did not return a valid result format (bool, data)")
                return [("Invalid return format", "error")]
            
            if not data:
                logger.warning(f"No data returned from {function_name} in {script_path}")
                return [("No data available", "no_data")]
            
            # Normaliser les données selon le format attendu [(label, value), ...]
            # Conversion des données en liste si c'est un dictionnaire
            if isinstance(data, dict):
                # Pour un dictionnaire, convertir en liste d'éléments
                data_list = []
                for key, value in data.items():
                    # Si la valeur est un dictionnaire, l'utiliser directement
                    if isinstance(value, dict):
                        item = value.copy()
                        # Assurer que l'élément a une clé correspondant à value_key
                        if 'value' not in item and key not in item:
                            item['value'] = key
                        data_list.append(item)
                    else:
                        # Sinon, créer un dictionnaire avec le minimum requis
                        data_list.append({
                            'value': key,
                            'description': str(value) if value is not None else str(key)
                        })
                data = data_list
                logger.debug(f"Converted dictionary to list with {len(data)} items")
                    
            options = self._normalize_options(data, dynamic_config)
            logger.info(f"Normalized {len(options)} options for field {self.field_id}")
            return options
            
        except Exception as e:
            logger.error(f"Error getting dynamic options: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return [("Error: " + str(e), "error")]

    def _normalize_options(self, options, dynamic_config):
        """
        Normalise les options au format [(label, value), ...] uniforme.
        
        Args:
            options: Données brutes retournées par le script
            dynamic_config: Configuration des options dynamiques
            
        Returns:
            list: Liste d'options normalisées
        """
        # Obtenir les clés à utiliser pour l'étiquette et la valeur
        label_key = dynamic_config.get('label_key', 'description')
        value_key = dynamic_config.get('value_key', 'value')
        
        logger.debug(f"Normalizing options with label_key='{label_key}', value_key='{value_key}'")
        
        normalized = []
        
        # Si options est None ou vide, retourner une liste vide
        if not options:
            logger.warning("Options is empty or None")
            return []
        
        # Log détaillé des options brutes
        if isinstance(options, list):
            logger.debug(f"Options is a list with {len(options)} items")
            for i, opt in enumerate(options[:3]):
                logger.debug(f"  Raw option {i}: {type(opt)}: {opt}")
            if len(options) > 3:
                logger.debug(f"  ... and {len(options)-3} more items")
        elif isinstance(options, dict):
            logger.debug(f"Options is a dict with {len(options)} items")
            for i, (k, v) in enumerate(list(options.items())[:3]):
                logger.debug(f"  Raw option {i}: {k} -> {v}")
            if len(options) > 3:
                logger.debug(f"  ... and {len(options)-3} more items")
        else:
            logger.debug(f"Options is of type {type(options)}")
        
        # Traitement selon le type des options
        if isinstance(options, dict):
            # C'est un dictionnaire, convertir en liste de tuples (label, value)
            logger.debug("Converting dict to list of tuples")
            for key, value in options.items():
                if isinstance(value, dict):
                    # Si la valeur est un dictionnaire, chercher label_key et value_key
                    label = value.get(label_key, key)
                    val = value.get(value_key, key)
                else:
                    # Sinon, utiliser la clé comme value et la valeur comme label
                    label = str(value)
                    val = key
                
                normalized.append((str(label), str(val)))
                logger.debug(f"  Normalized from dict: '{label}' -> '{val}'")
        elif isinstance(options, list):
            # C'est une liste, traiter chaque élément
            for opt in options:
                if isinstance(opt, (list, tuple)):
                    # Si c'est déjà un tuple ou une liste, s'assurer qu'elle a 2 éléments
                    if len(opt) >= 2:
                        label = str(opt[0])
                        value = str(opt[1])
                        normalized.append((label, value))
                        logger.debug(f"  From tuple/list: '{label}' -> '{value}'")
                    else:
                        label = value = str(opt[0])
                        normalized.append((label, value))
                        logger.debug(f"  From single item tuple/list: '{label}' -> '{value}'")
                elif isinstance(opt, dict):
                    # Si c'est un dictionnaire, extraire les valeurs selon les clés spécifiées
                    raw_label = opt.get(label_key)
                    raw_value = opt.get(value_key)
                    
                    # Log des valeurs brutes extraites
                    logger.debug(f"  From dict: raw_label='{raw_label}', raw_value='{raw_value}'")
                    
                    # Si label_key n'existe pas, essayer d'autres options
                    if raw_label is None:
                        # Essayer d'autres clés communes en priorité décroissante
                        for fallback_key in ['description', 'label', 'name', 'username', 'device', 'path', 'id']:
                            if fallback_key in opt:
                                raw_label = opt[fallback_key]
                                logger.debug(f"    Fallback to '{fallback_key}' for label: '{raw_label}'")
                                break
                        
                        # Si toujours rien et que le dictionnaire a exactement 2 clés, utiliser les valeurs
                        if raw_label is None and len(opt) == 2:
                            keys = list(opt.keys())
                            raw_label = opt[keys[0]]
                            if raw_value is None:  # Si value n'est pas encore défini
                                raw_value = opt[keys[1]]
                            logger.debug(f"    Using 2-key dict values: label='{raw_label}', value='{raw_value}'")
                        
                        # En dernier recours, convertir tout le dict en chaîne pour l'affichage
                        if raw_label is None:
                            # Construire une description à partir de toutes les clés/valeurs
                            items = []
                            for k, v in opt.items():
                                if isinstance(v, (str, int, float, bool)):
                                    items.append(f"{k}:{v}")
                            if items:
                                raw_label = " ".join(items)
                            else:
                                raw_label = str(opt)
                            logger.debug(f"    Constructed label from dict: '{raw_label}'")
                    
                    # Si value_key n'existe pas, utiliser une valeur de secours
                    if raw_value is None:
                        # Essayer d'autres clés en priorité décroissante
                        for fallback_key in ['id', 'value', 'username', 'device', 'name', 'path']:
                            if fallback_key in opt:
                                raw_value = opt[fallback_key]
                                logger.debug(f"    Fallback to '{fallback_key}' for value: '{raw_value}'")
                                break
                                
                        # Si toujours rien, utiliser la première clé non utilisée pour le label
                        if raw_value is None:
                            for key, val in opt.items():
                                if str(val) != str(raw_label):  # Éviter d'utiliser la même valeur que le label
                                    raw_value = val
                                    logger.debug(f"    Using alternate key '{key}' for value: '{raw_value}'")
                                    break
                        
                        # En dernier recours, utiliser le label ou une clé
                        if raw_value is None:
                            raw_value = raw_label or next(iter(opt.values()), "")
                            logger.debug(f"    Using label as value: '{raw_value}'")
                    
                    # Finaliser les valeurs en les convertissant en chaînes
                    label = str(raw_label) if raw_label is not None else ""
                    value = str(raw_value) if raw_value is not None else ""
                    
                    normalized.append((label, value))
                    logger.debug(f"  Final normalized: '{label}' -> '{value}'")
                else:
                    # Pour les valeurs simples, utiliser la même valeur pour l'étiquette et la valeur
                    label = value = str(opt)
                    normalized.append((label, value))
                    logger.debug(f"  From simple value: '{label}' -> '{value}'")
        else:
            # Pour tout autre type, convertir en chaîne
            label = value = str(options)
            normalized.append((label, value))
            logger.debug(f"  From unexpected type: '{label}' -> '{value}'")
        
        # Résumé final
        logger.info(f"Normalized {len(normalized)} options")
        for i, (label, value) in enumerate(normalized[:5]):
            logger.info(f"  Option {i}: '{label}' -> '{value}'")
        if len(normalized) > 5:
            logger.info(f"  ... and {len(normalized)-5} more options")
        
        return normalized
        
    def compose(self) -> ComposeResult:
        label = self.field_config.get('label', self.field_id)
        
        with HorizontalGroup():
            yield Label(label, classes="field-label")
            if self.field_config.get('required', False):
                yield Label("*", classes="required-star")
                
        # Check if field should be enabled or not
        if self.enabled_if:
            dep_field = self.fields_by_id.get(self.enabled_if['field'])
            if dep_field:
                logger.debug(f"Field {self.field_id}: enabled_if={self.enabled_if}, dep_field={dep_field.field_id}, dep_value={dep_field.value}")
                
                # Vérifier si le champ doit être activé ou non
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
        return self.value
        
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select change"""
        if event.select.id == f"select_{self.field_id}":
            old_value = self.value
            self.value = event.value
            
            logger.debug(f"Field {self.field_id} value changed from {old_value} to {self.value}")
            
            # Mettre à jour tous les champs dépendants
            for field_id, field in self.fields_by_id.items():
                # 1. Vérifier les champs qui dépendent de ce champ pour les valeurs par défaut
                if hasattr(field, 'field_config') and field.field_config.get('depends_on') == self.field_id:
                    # Recalculer la valeur par défaut
                    new_value = field._get_dynamic_default()
                    logger.debug(f"Updating dependent field {field_id} value to {new_value}")
                    
                    # Mettre à jour la valeur et le widget
                    field.value = new_value
                    if hasattr(field, 'input'):
                        field.input.value = new_value
                    elif hasattr(field, 'select'):
                        field.select.value = new_value
                    elif hasattr(field, 'checkbox'):
                        field.checkbox.value = bool(new_value)
                    
                    # Si le champ a des options dynamiques, les rafraîchir
                    if hasattr(field, 'refresh_options'):
                        field.refresh_options()
                
                # 2. Vérifier les champs qui sont conditionnellement activés/désactivés
                if field.enabled_if and field.enabled_if['field'] == self.field_id:
                    # Mettre à jour l'état enabled/disabled
                    field.update_enabled_state()
                    
    def update_enabled_state(self):
        """Met à jour l'état enabled/disabled basé sur la dépendance enabled_if"""
        if not self.enabled_if:
            return
            
        dep_field = self.fields_by_id.get(self.enabled_if['field'])
        if not dep_field:
            return
        
        # Valeur attendue pour l'activation
        expected_value = self.enabled_if['value']
            
        # Déterminer si le champ doit être activé ou désactivé
        should_enable = False
        
        # Cas spécial: valeur "has_options" pour les CheckboxGroupField
        if expected_value == 'has_options' and hasattr(dep_field, 'has_options'):
            should_enable = dep_field.has_options
            logger.debug(f"Checking has_options for {dep_field.field_id}: {should_enable}")
        else:
            # Cas standard: vérifier si la valeur du champ correspond à la valeur attendue
            should_enable = (dep_field.value == expected_value)
        
        was_disabled = self.disabled
        self.disabled = not should_enable
        
        # Mise à jour des classes CSS
        if self.disabled:
            self.add_class('disabled')
        else:
            self.remove_class('disabled')
            
        # Mise à jour du widget spécifique
        self._update_widget_state(was_disabled != self.disabled)
        
        # Si le champ est activé après avoir été désactivé et qu'il a besoin d'être rafraîchi
        if was_disabled and not self.disabled and hasattr(self, 'needs_refresh_when_enabled') and self.needs_refresh_when_enabled:
            logger.info(f"Field {self.field_id} was enabled and needs refresh")
            
            # Effacer le marqueur
            self.needs_refresh_when_enabled = False
            
            # Rafraîchir les options si nécessaire
            if hasattr(self, 'refresh_options') and 'dynamic_options' in self.field_config:
                logger.info(f"Refreshing options for newly enabled field {self.field_id}")
                try:
                    self.refresh_options()
                    logger.info(f"Successfully refreshed options for {self.field_id}")
                except Exception as e:
                    logger.error(f"Error refreshing options for {self.field_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
        
        # Si le champ est désactivé, effacer sa valeur si nécessaire
        if self.disabled and self.field_config.get('clear_on_disable', False):
            self.value = None
            self._clear_widget_value()
            
    def _update_widget_state(self, state_changed: bool):
        """
        Met à jour l'état du widget spécifique (à surcharger dans les sous-classes)
        
        Args:
            state_changed (bool): Indique si l'état a changé
        """
        pass
        
    def _clear_widget_value(self):
        """Efface la valeur du widget (à surcharger dans les sous-classes)"""
        pass

class TextField(ConfigField):
    """Text input field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        self.input = Input(
            placeholder=self.field_config.get('placeholder', ''),
            value=self.value or '',
            id=f"input_{self.field_id}"
        )
        
        # Initialiser correctement l'état disabled
        if self.disabled:
            logger.debug(f"TextField {self.field_id} is initially disabled")
            self.input.disabled = True
            self.input.add_class('disabled')
        else:
            self.input.disabled = False
            self.input.remove_class('disabled')
            
        yield self.input

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            value = event.value
            
            # Validation
            is_valid, error_msg = self.validate_input(value)
            if not is_valid:
                self.input.add_class('error')
                self.input.tooltip = error_msg
                logger.warning(f"Field {self.field_id} validation failed: {error_msg}")
                return
            else:
                self.input.remove_class('error')
                self.input.tooltip = None
                
            # Mettre à jour la valeur si elle est valide
            old_value = self.value
            self.value = value
            
            logger.info(f"Field {self.field_id} value changed from '{old_value}' to '{self.value}'")
            
            # Mettre à jour tous les champs dépendants
            updated_fields = []
            
            for field_id, field in self.fields_by_id.items():
                # 1. Vérifier les champs qui dépendent de ce champ pour les valeurs par défaut
                if hasattr(field, 'field_config') and field.field_config.get('depends_on') == self.field_id:
                    logger.info(f"Found dependent field {field_id} to update")
                    # Recalculer la valeur par défaut
                    old_field_value = field.value
                    new_value = field._get_dynamic_default()
                    logger.info(f"Updating dependent field {field_id} value: '{old_field_value}' -> '{new_value}'")
                    
                    # Mettre à jour la valeur et le widget
                    field.value = new_value
                    if hasattr(field, 'input'):
                        field.input.value = new_value
                        logger.debug(f"Updated input widget for {field_id}")
                    elif hasattr(field, 'select'):
                        field.select.value = new_value
                        logger.debug(f"Updated select widget for {field_id}")
                    elif hasattr(field, 'checkbox'):
                        field.checkbox.value = bool(new_value)
                        logger.debug(f"Updated checkbox widget for {field_id}")
                    
                    # Si le champ a des options dynamiques, les rafraîchir
                    if hasattr(field, 'refresh_options'):
                        logger.info(f"Refreshing options for dependent field {field_id}")
                        field.refresh_options()
                    
                    updated_fields.append(field_id)
                
                # 2. Vérifier les champs qui sont conditionnellement activés/désactivés
                if field.enabled_if and field.enabled_if['field'] == self.field_id:
                    was_disabled = field.disabled
                    logger.info(f"Updating enabled state for field {field_id} (currently disabled: {was_disabled})")
                    # Mettre à jour l'état enabled/disabled
                    field.update_enabled_state()
                    
                    if was_disabled != field.disabled:
                        logger.info(f"Field {field_id} disabled state changed: {was_disabled} -> {field.disabled}")
                        updated_fields.append(field_id)
            
            if updated_fields:
                logger.info(f"Updated {len(updated_fields)} dependent fields: {', '.join(updated_fields)}")
            else:
                logger.info(f"No dependent fields updated for {self.field_id}")

    def validate_input(self, value: str) -> tuple[bool, str]:
        """Validate input value according to configured rules"""
        # Vérifier si le champ est désactivé par enabled_if
        if self.enabled_if and self.disabled:
            return True, ""

        # Vérifier not_empty
        if self.field_config.get('not_empty', False) and not value:
            return False, "Ce champ ne peut pas être vide"
            
        # Vérifier min_length
        min_length = self.field_config.get('min_length')
        if min_length and len(value) < min_length:
            return False, f"La longueur minimale est de {min_length} caractères"
            
        # Vérifier max_length
        max_length = self.field_config.get('max_length')
        if max_length and len(value) > max_length:
            return False, f"La longueur maximale est de {max_length} caractères"
            
        # Vérifier no_spaces
        if self.field_config.get('validate') == 'no_spaces' and ' ' in value:
            return False, "Les espaces ne sont pas autorisés"
            
        return True, ""
        
    def _update_widget_state(self, state_changed: bool):
        """Met à jour l'état disabled du widget Input"""
        if hasattr(self, 'input'):
            if self.disabled:
                self.input.disabled = True
                self.input.add_class('disabled')
            else:
                self.input.disabled = False
                self.input.remove_class('disabled')
                
    def _clear_widget_value(self):
        """Efface la valeur du widget Input"""
        if hasattr(self, 'input'):
            self.input.value = ''

class DirectoryField(TextField):
    """Directory selection field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Button("Browse...", id=f"browse_{self.field_id}")
        
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == f"browse_{self.field_id}":
            try:
                # Vérifier si l'environnement graphique est disponible
                if os.environ.get('DISPLAY') is None:
                    # Environnement non graphique, demander le chemin manuellement
                    selected_dir = await self.app.prompt("Veuillez entrer le chemin du répertoire:")
                else:
                    # Environnement graphique, utiliser zenity
                    from subprocess import Popen, PIPE
                    process = Popen(['zenity', '--file-selection', '--directory'], stdout=PIPE, stderr=PIPE)
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        selected_dir = stdout.decode().strip()
                    else:
                        logger.error(f"Erreur lors de la sélection du répertoire: {stderr.decode().strip()}")
                        return

                # IMPORTANT: Stocker l'ancienne valeur avant de changer
                old_value = self.value
                new_value = selected_dir
                
                # Mettre à jour la valeur du champ avec le répertoire sélectionné
                self.input.value = new_value
                self.value = new_value
                
                logger.info(f"Directory field {self.field_id} changed via button: '{old_value}' -> '{new_value}'")
                
                # IMPORTANT: Chercher d'abord le conteneur parent qui a le dictionnaire fields_by_id global
                self._force_update_all_dependents(old_value, new_value)

            except Exception as e:
                logger.error(f"Erreur lors de la sélection du répertoire: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
    
    def _force_update_all_dependents(self, old_value, new_value):
        """Force la mise à jour de tous les champs qui dépendent de celui-ci"""
        logger.info(f"Forcing update of all fields depending on {self.field_id}")
        
        # IMPORTANT: Vérifier si fields_by_id est vide et si oui, chercher un conteneur parent avec un dictionnaire valide
        fields_dict = self.fields_by_id
        if not fields_dict:
            logger.warning(f"self.fields_by_id is empty for {self.field_id}, trying to find a parent container with fields_by_id")
            
            # Chercher le PluginConfigContainer parent
            plugin_container = None
            try:
                plugin_container = self.ancestors_with_self[-1]  # Prendre le conteneur le plus haut dans la hiérarchie
                if hasattr(plugin_container, 'fields_by_id') and plugin_container.fields_by_id:
                    fields_dict = plugin_container.fields_by_id
                    logger.info(f"Found fields_by_id in parent container: {plugin_container}")
                else:
                    # Chercher un autre widget avec fields_by_id
                    for ancestor in reversed(self.ancestors_with_self):
                        if hasattr(ancestor, 'fields_by_id') and ancestor.fields_by_id:
                            fields_dict = ancestor.fields_by_id
                            logger.info(f"Found fields_by_id in ancestor: {ancestor}")
                            break
            except Exception as e:
                logger.error(f"Error finding parent container: {e}")
        
        # Si on a toujours un dictionnaire vide, essayer une approche alternative
        if not fields_dict:
            logger.warning("Could not find fields_by_id in any parent, trying to find fields via app.screen")
            try:
                # Essayer d'accéder au screen actuel et à ses champs
                screen = self.app.screen
                if hasattr(screen, 'fields_by_id') and screen.fields_by_id:
                    fields_dict = screen.fields_by_id
                    logger.info(f"Found fields_by_id in current screen")
                elif hasattr(screen, 'plugin_instances'):
                    # Si screen a plugin_instances, chercher fields_by_id
                    logger.info(f"Trying to find fields through plugin_instances")
                    for container in screen.query("PluginConfigContainer"):
                        if hasattr(container, 'fields_by_id') and container.fields_by_id:
                            fields_dict = container.fields_by_id
                            logger.info(f"Found fields_by_id in PluginConfigContainer: {container}")
                            break
            except Exception as e:
                logger.error(f"Error accessing screen or containers: {e}")
        
        # Journaliser les résultats
        if not fields_dict:
            logger.error(f"Could not find fields_by_id anywhere. Cannot update dependents for {self.field_id}")
            return
        else:
            logger.info(f"Using fields_dict with {len(fields_dict)} fields: {list(fields_dict.keys())}")
        
        # Maintenant, parcourir tous les champs pour trouver ceux qui dépendent de ce champ
        dependents = []
        for field_id, field in fields_dict.items():
            # Vérifier différentes façons de spécifier la dépendance
            if hasattr(field, 'field_config') and field.field_config.get('depends_on') == self.field_id:
                dependents.append((field_id, field))
                logger.info(f"Found dependent field: {field_id}")
        
        # Si aucun dépendant trouvé, vérifier à nouveau avec des logs détaillés
        if not dependents:
            logger.debug(f"No dependents found for {self.field_id}, checking field_config of all fields:")
            for field_id, field in fields_dict.items():
                if hasattr(field, 'field_config'):
                    depends_on = field.field_config.get('depends_on')
                    logger.debug(f"Field {field_id} has depends_on = {depends_on}")
            logger.info(f"No fields depend on {self.field_id}")
            return
            
        # Mettre à jour chaque champ dépendant
        for field_id, field in dependents:
            logger.info(f"Updating dependent field {field_id}")
            
            # Si le champ a des options dynamiques, les rafraîchir explicitement
            if hasattr(field, 'field_config') and 'dynamic_options' in field.field_config:
                # 1. Récupérer la config dynamique
                dynamic_config = field.field_config['dynamic_options']
                script = dynamic_config.get('script')
                function = dynamic_config.get('function')
                is_global = dynamic_config.get('global', False)
                
                logger.info(f"Field {field_id} has dynamic options from script={script}, function={function}, global={is_global}")
                
                # 2. Vérifier si le champ a une méthode refresh_options
                if hasattr(field, 'refresh_options'):
                    try:
                        # Forcer la mise à jour des options
                        logger.info(f"Calling refresh_options for {field_id}")
                        field.refresh_options()
                        logger.info(f"Successfully refreshed options for {field_id}")
                    except Exception as e:
                        logger.error(f"Error refreshing options for {field_id}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.warning(f"Field {field_id} has dynamic_options but no refresh_options method")
            
            # Si le champ est actuellement désactivé, marquer qu'il a besoin d'être mis à jour
            # lorsqu'il sera activé
            if hasattr(field, 'disabled') and field.disabled:
                logger.info(f"Field {field_id} is currently disabled, marking for later refresh")
                field.needs_refresh_when_enabled = True


class IPField(TextField):
    """IP address input field with validation"""
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            # Only validate if the field is enabled
            if not event.input.disabled:
                value = event.value.strip()
                if value:
                    # Basic IP address validation
                    try:
                        octets = [int(x) for x in value.split('.')]
                        if len(octets) == 4 and all(0 <= x <= 255 for x in octets):
                            self.value = value
                            event.input.remove_class('error')
                        else:
                            event.input.add_class('error')
                    except (ValueError, AttributeError):
                        event.input.add_class('error')
                else:
                    # Empty value is allowed if field is not required
                    self.value = value
                    event.input.remove_class('error')

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        self.checkbox = Checkbox(
            id=f"checkbox_{self.plugin_path}_{self.field_id}",
            value=self.value or False,
            classes="CheckBox",
        )
        
        # Initialiser correctement l'état disabled
        if self.disabled:
            logger.debug(f"CheckboxField {self.field_id} is initially disabled")
            self.checkbox.disabled = True
            self.checkbox.add_class('disabled')
        else:
            self.checkbox.disabled = False
            self.checkbox.remove_class('disabled')
            
        yield self.checkbox

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == f"checkbox_{self.plugin_path}_{self.field_id}":
            self.value = event.value
            
            # Mise à jour des champs dépendants
            for field_id, field in self.fields_by_id.items():
                if field.enabled_if and field.enabled_if['field'] == self.field_id:
                    # Mettre à jour l'état enabled/disabled
                    field.update_enabled_state()
                    
    def _update_widget_state(self, state_changed: bool):
        """Met à jour l'état disabled du widget Checkbox"""
        if hasattr(self, 'checkbox'):
            if self.disabled:
                self.checkbox.disabled = True
                self.checkbox.add_class('disabled')
            else:
                self.checkbox.disabled = False
                self.checkbox.remove_class('disabled')
                
    def _clear_widget_value(self):
        """Réinitialise la valeur du widget Checkbox à False"""
        if hasattr(self, 'checkbox'):
            self.checkbox.value = False

class SelectField(ConfigField):
    """Select field with options"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        # Get options in (label, value) format
        self.options = self._get_options()
        if not self.options:
            logger.warning(f"No options available for select {self.field_id}")
            self.options = [("No options available", "none")]
        
        # Make sure the default value is in the available options
        available_values = [opt[1] for opt in self.options]  # Value is in second position
        if not self.value or str(self.value) not in available_values:
            self.value = available_values[0] if available_values else None
        
        # Create Select component with options
        self.select = Select(
            options=self.options,  # Options are already in correct format (label, value)
            value=self.value,
            id=f"select_{self.field_id}",
            allow_blank=self.field_config.get('allow_blank', False)
        )
        
        # Initialiser correctement l'état disabled
        if self.disabled:
            logger.debug(f"SelectField {self.field_id} is initially disabled")
            self.select.disabled = True
            self.select.add_class('disabled')
        else:
            self.select.disabled = False
            self.select.remove_class('disabled')
            
        yield self.select

    def _get_options(self) -> list:
        """Get options for the select field, either static or dynamic"""
        if 'options' in self.field_config:
            logger.debug(f"Using static options: {self.field_config['options']}")
            return self._normalize_options(self.field_config['options'], {})
            
        if 'dynamic_options' in self.field_config:
            return self._get_dynamic_options(self.field_config['dynamic_options'])
                
        return [("No options available", "none")]
        
    def _update_widget_state(self, state_changed: bool):
        """Met à jour l'état disabled du widget Select"""
        if hasattr(self, 'select'):
            if self.disabled:
                self.select.disabled = True
                self.select.add_class('disabled')
            else:
                self.select.disabled = False
                self.select.remove_class('disabled')
                
    def _clear_widget_value(self):
            """Réinitialise la valeur du widget Select à la première option"""
            if hasattr(self, 'select') and self.options:
                self.select.value = self.options[0][1]  # La première valeur disponible
            
    def get_value(self) -> str:
        """Get the current value"""
        return self.value if self.value != "none" else ""
class CheckboxGroupField(ConfigField):
    """Group of checkboxes, one for each option"""
    
    # Ajouter une propriété pour savoir si le champ a des options
    @property
    def has_options(self):
        """Return True if the field has at least one option"""
        return hasattr(self, 'options') and len(self.options) > 0

    def _get_options(self) -> list:
        """Get options for checkboxes, either static or dynamic"""
        if 'options' in self.field_config:
            logger.debug(f"Using static options: {self.field_config['options']}")
            return self._normalize_options(self.field_config['options'], {})
            
        if 'dynamic_options' in self.field_config:
            return self._get_dynamic_options(self.field_config['dynamic_options'])
                
        return [("No options available", "none")]
    
    # Ajouter méthode pour mettre à jour les champs qui dépendent de has_options
    def _update_fields_dependent_on_has_options(self):
        """Update fields that depend on whether this field has options"""
        if not self.fields_by_id:
            logger.warning(f"self.fields_by_id is empty for {self.field_id}, cannot update dependent fields")
            return
            
        logger.info(f"Checking fields dependent on has_options status of {self.field_id}")
        for field_id, field in self.fields_by_id.items():
            if (hasattr(field, 'enabled_if') and 
                field.enabled_if and 
                field.enabled_if.get('field') == self.field_id and 
                field.enabled_if.get('value') == 'has_options'):
                
                logger.info(f"Field {field_id} depends on has_options status of {self.field_id}")
                
                # Nous devons mettre à jour la valeur temporairement pour la vérification
                old_value = field.value
                
                # Nouveau: Si nous avons des options, ce champ devrait être visible
                if self.has_options:
                    logger.info(f"{self.field_id} has {len(self.options)} options, enabling {field_id}")
                    field.disabled = False
                    field.remove_class('disabled')
                    if hasattr(field, '_update_widget_state'):
                        field._update_widget_state(True)
                else:
                    logger.info(f"{self.field_id} has no options, disabling {field_id}")
                    field.disabled = True
                    field.add_class('disabled')
                    if hasattr(field, '_update_widget_state'):
                        field._update_widget_state(True)
                
                # Restaurer la valeur
                field.value = old_value

    def refresh_options(self):
        """Refresh the options based on updated dependencies"""
        logger.info(f"Refreshing options for field {self.field_id} (depends on {self.field_config.get('depends_on')})")
        
        # Save current selections
        current_selections = self.selected_values if hasattr(self, 'selected_values') else set()
        logger.debug(f"Current selections before refresh: {current_selections}")
        
        # Get container and clear it
        try:
            checkbox_container = self.query_one(f"#checkboxgroup_{self.field_id}")
            checkbox_container.remove_children()
            logger.debug(f"Cleared all checkboxes in container for {self.field_id}")
        except Exception as e:
            logger.error(f"Error clearing checkboxes for {self.field_id}: {e}")
            return
        
        # Get fresh options
        logger.info(f"Getting new options for {self.field_id} - calling dynamic script")
        old_options = self.options if hasattr(self, 'options') else []
        
        # Si le champ a des options dynamiques, récupérer les paramètres de configuration
        dynamic_config = self.field_config.get('dynamic_options', {})
        value_key = dynamic_config.get('value_key', 'value')
        label_key = dynamic_config.get('label_key', 'description')
        logger.info(f"Using value_key='{value_key}' and label_key='{label_key}' for {self.field_id}")
        
        # Obtenir les options brutes
        raw_options = None
        if 'dynamic_options' in self.field_config:
            # Récupérer les données brutes avant normalisation
            result = self._get_dynamic_options_raw(self.field_config['dynamic_options'])
            if isinstance(result, tuple) and len(result) == 2:
                success, data = result
                if success:
                    raw_options = data
                    # Log des données brutes pour debug
                    logger.info(f"Raw data from dynamic options for {self.field_id}:")
                    if isinstance(raw_options, list):
                        for i, item in enumerate(raw_options[:5]):
                            logger.info(f"  Item {i}: {item}")
                        if len(raw_options) > 5:
                            logger.info(f"  ... and {len(raw_options)-5} more items")
                    elif isinstance(raw_options, dict):
                        for i, (key, val) in enumerate(list(raw_options.items())[:5]):
                            logger.info(f"  Item {i}: {key} -> {val}")
                        if len(raw_options) > 5:
                            logger.info(f"  ... and {len(raw_options)-5} more items")
        
        # Normaliser les options
        self.options = self._get_options()
        logger.info(f"Retrieved {len(self.options)} options for {self.field_id} (had {len(old_options)} before)")
        
        # Debug log of new options
        logger.info(f"Normalized options for {self.field_id}:")
        for i, (label, value) in enumerate(self.options[:10]):
            logger.info(f"  Option {i}: '{label}' -> '{value}'")
        if len(self.options) > 10:
            logger.info(f"  ... and {len(self.options)-10} more options")
        
        # IMPORTANT: Pour chaque option, créer un groupe et tous ses enfants,
        # puis monter le groupe complet dans le conteneur
        for option in self.options:
            option_label = option[0]  # label is in first position
            option_value = option[1]  # value is in second position
            
            logger.debug(f"Creating checkbox for option: '{option_label}' (value: '{option_value}')")
            
            # Check if this option was previously selected
            is_selected = option_value in current_selections
            
            # ORDRE CORRECT DE MONTAGE:
            # 1. Créer tous les widgets
            hgroup = HorizontalGroup()
            checkbox = Checkbox(
                id=f"checkbox_{self.field_id}_{option_value}",
                value=is_selected
            )
            label_widget = Label(option_label)
            
            # Appliquer l'état disabled si nécessaire
            if self.disabled:
                checkbox.disabled = True
                checkbox.add_class('disabled')
            
            # 2. D'abord monter le groupe dans le conteneur parent
            checkbox_container.mount(hgroup)
            
            # 3. Ensuite monter les widgets dans le groupe
            hgroup.mount(checkbox)
            hgroup.mount(label_widget)
        
        # IMPORTANT: Recalculate selected values to ONLY include options that still exist
        # This fixes the issue where old values remained when changing the dependency
        available_values = {opt[1] for opt in self.options}
        old_selections = self.selected_values.copy() if hasattr(self, 'selected_values') else set()
        self.selected_values = {v for v in current_selections if v in available_values}
        
        # Log if any selections were dropped because the options no longer exist
        dropped_selections = old_selections - self.selected_values
        if dropped_selections:
            logger.info(f"Dropped {len(dropped_selections)} selections that no longer exist: {dropped_selections}")
        
        # Update the value string
        self.value = ",".join(sorted(self.selected_values))
        logger.info(f"Updated value for {self.field_id}: {self.value}")
        
        # NOUVEAU: Mettre à jour les champs qui dépendent du nombre d'options
        # Cela permet de cacher/montrer user_all en fonction de la présence d'utilisateurs
        self._update_fields_dependent_on_has_options()

    def _get_dynamic_options_raw(self, dynamic_config):
        """
        Récupère les données brutes des options dynamiques, avant normalisation.
        
        Args:
            dynamic_config (dict): Configuration des options dynamiques
            
        Returns:
            tuple(bool, data): Résultat brut de l'appel au script
        """
        if not dynamic_config or 'script' not in dynamic_config:
            logger.error("Configuration des options dynamiques invalide")
            return False, "Configuration invalide"
        
        # Le fichier et la fonction à appeler
        script_path = dynamic_config.get('script')
        function_name = dynamic_config.get('function')
        
        if not script_path:
            logger.error("Aucun script spécifié dans dynamic_options")
            return False, "Script non spécifié"
        
        # Vérifier si c'est un script global (dans utils)
        is_global_script = dynamic_config.get('global', False)
        
        # Vérifier si le chemin contient une extension .py, sinon l'ajouter
        if not script_path.endswith('.py'):
            script_path += '.py'
        
        # Construire le chemin complet du fichier
        if is_global_script:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', 'utils', script_path)
        else:
            script_full_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', self.plugin_path, script_path)
        
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
                return False, "Error loading module"
                
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
                return False, "No function found"
                
            logger.debug(f"Using function: {function_name}")
            func = getattr(module, function_name)
            
            # Préparer les arguments
            args = []
            kwargs = {}
            for arg_config in dynamic_config.get('args', []):
                if isinstance(arg_config, dict):
                    if 'field' in arg_config:
                        field_id = arg_config['field']
                        if field_id in self.fields_by_id:
                            # Si un nom de paramètre est spécifié, utiliser un argument nommé
                            if 'param_name' in arg_config:
                                kwargs[arg_config['param_name']] = self.fields_by_id[field_id].get_value()
                            else:
                                args.append(self.fields_by_id[field_id].get_value())
                        else:
                            logger.warning(f"Field {field_id} not found for argument")
                    elif 'value' in arg_config:
                        # Si un nom de paramètre est spécifié, utiliser un argument nommé
                        if 'param_name' in arg_config:
                            kwargs[arg_config['param_name']] = arg_config['value']
                        else:
                            args.append(arg_config['value'])
                else:
                    # Si c'est directement une valeur
                    args.append(arg_config)
            
            logger.debug(f"Calling {function_name} with args: {args}, kwargs: {kwargs}")
            
            # Appeler la fonction avec les arguments préparés
            result = func(*args, **kwargs)
            
            # La fonction doit retourner (success, data)
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
                return result
            else:
                logger.error(f"Function {function_name} did not return a valid result format (bool, data)")
                return False, "Invalid return format"
            
        except Exception as e:
            logger.error(f"Error getting dynamic options: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)

class PluginConfigContainer(VerticalGroup):
    """Container for plugin configuration fields"""
    # Define reactive attributes
    plugin_id = reactive("")  # Plugin identifier
    plugin_title = reactive("")   # Plugin name/title
    plugin_icon = reactive("")    # Plugin icon
    plugin_description = reactive("")  # Plugin description
    
    def __init__(self, plugin: str, name: str, icon: str, description: str, fields_by_plugin: dict, fields_by_id: dict, config_fields: list, **kwargs):
        super().__init__(**kwargs)
        # Set the reactive attributes
        self.plugin_id = plugin
        self.plugin_title = name
        self.plugin_icon = icon
        self.plugin_description = description
        # Non-reactive attributes
        self.fields_by_plugin = fields_by_plugin
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields

    def compose(self) -> ComposeResult:
        # Title and description
        with VerticalGroup(classes="plugin-header"):
            yield Label(f"{self.plugin_icon} {self.plugin_title}", classes="plugin-title")
            if self.plugin_description:
                yield Label(self.plugin_description, classes="plugin-description")
        
        if not self.config_fields:
            with HorizontalGroup(classes="no-config-container"):
                yield Label("ℹ️", classes="no-config-icon")
                yield Label(f"Nothing to configure for {self.plugin_title}", classes="no-config")
            return

        # Configuration fields
        for field_config in self.config_fields:
            field_id = field_config.get('id')
            if not field_id:
                logger.warning(f"Field without id in plugin {self.plugin_id}")
                continue
                
            field_type = field_config.get('type', 'text')
            field_class = {
                'text': TextField,
                'directory': DirectoryField,
                'ip': IPField,
                'checkbox': CheckboxField,
                'select': SelectField,
                'checkbox_group': CheckboxGroupField
            }.get(field_type, TextField)
            
            # Create field with access to other fields
            field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
            self.fields_by_plugin[self.plugin_id][field_id] = field
            self.fields_by_id[field_id] = field
            
            yield field

    def on_mount(self) -> None:
        """Handler called when the widget is mounted"""
        logger.info(f"Plugin {self.plugin_id} mounted, initializing dependencies...")
        
        # DEBUG: Vérifier que les configuration fields ont tous les attributs nécessaires
        for field_id, field in self.fields_by_id.items():
            # Vérifier si le champ a bien field_config
            if not hasattr(field, 'field_config'):
                logger.error(f"ERROR: Field {field_id} has no field_config attribute!")
                continue
            
            # Vérifier les dépendances
            depends_on = field.field_config.get('depends_on')
            if depends_on:
                if depends_on in self.fields_by_id:
                    logger.debug(f"Field {field_id} correctly depends on {depends_on}")
                else:
                    logger.error(f"ERROR: Field {field_id} depends on {depends_on} which does not exist!")
            
            # Vérifier enabled_if
            if hasattr(field, 'enabled_if') and field.enabled_if:
                enabled_field = field.enabled_if.get('field')
                if enabled_field in self.fields_by_id:
                    logger.debug(f"Field {field_id} enabled_if correctly references {enabled_field}")
                else:
                    logger.error(f"ERROR: Field {field_id} enabled_if references {enabled_field} which does not exist!")
        
        # 1. D'abord, initialiser l'état enabled/disabled de tous les champs
        for field_id, field in self.fields_by_id.items():
            if field.enabled_if:
                field.update_enabled_state()
                logger.debug(f"Initialized enabled state for field {field_id}: disabled={field.disabled}")
        
        # 2. Construire l'arbre de dépendances
        dependency_tree = {}
        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'field_config') and field.field_config.get('depends_on'):
                parent_field = field.field_config.get('depends_on')
                if parent_field not in dependency_tree:
                    dependency_tree[parent_field] = []
                dependency_tree[parent_field].append(field_id)
        
        # 3. Initialiser les champs dépendants par ordre de dépendance
        # Pour chaque champ parent, mettre à jour ses dépendants
        for parent_field, dependent_fields in dependency_tree.items():
            logger.info(f"Field {parent_field} has {len(dependent_fields)} dependent fields: {dependent_fields}")
            
            if parent_field in self.fields_by_id:
                parent = self.fields_by_id[parent_field]
                
                # Forcer la mise à jour des champs dépendants
                # On utilise une approche plus sûre qui ne repose pas sur refresh_options directement
                
                parent_value = parent.get_value()
                logger.info(f"Parent field {parent_field} has value '{parent_value}'")
                
                for dep_field_id in dependent_fields:
                    if dep_field_id in self.fields_by_id:
                        dep_field = self.fields_by_id[dep_field_id]
                        
                        # Si le champ a des options dynamiques, on veut s'assurer qu'elles sont initialisées
                        # même si le champ est désactivé
                        if 'dynamic_options' in dep_field.field_config:
                            logger.info(f"Initializing dynamic options for dependent field {dep_field_id}")
                            
                            # On s'assure que les options sont initialisées même si le champ est désactivé
                            dep_field.options = dep_field._get_options()
                            logger.info(f"Field {dep_field_id} has {len(dep_field.options)} options")
        
        # 4. Attacher les événements de changement aux checkboxes
        # Cette étape est importante pour s'assurer que les checkboxes peuvent réagir aux clics
        self.refresh()  # Forcer un rafraîchissement pour s'assurer que tous les widgets sont montés
        logger.info(f"Plugin {self.plugin_id} initialization completed")
        
class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [
        ("esc", "quit", "Quit"),
    ]
    CSS_PATH = "styles/config.css"

    def __init__(self, plugin_instances: list, name: str | None = None) -> None:
        super().__init__(name=name)
        self.plugin_instances = plugin_instances  # List of tuples (plugin_name, instance_id)
        self.current_config = {}
        self.fields_by_plugin = {}
        self.fields_by_id = {}  # Registre global des champs pour les dépendances

    def compose(self) -> ComposeResult:
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            for plugin_name, instance_id in self.plugin_instances:
                yield self._create_plugin_config(plugin_name, instance_id)
            
        with Horizontal(id="button-container"):
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Execute", id="validate", variant="primary")
            
        yield Footer()

    def _create_plugin_config(self, plugin: str, instance_id: int) -> Widget:
        """Create configuration fields for a plugin"""
        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', plugin, 'settings.yml')
        yaml = YAML()
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.load(f)
        except Exception as e:
            logger.exception(f"Error loading settings for {plugin}: {e}")
            return Container()
            
        # Store fields for later lookup
        self.fields_by_plugin[plugin] = {}

        name = settings.get('name', plugin)
        icon = settings.get('icon', '📦')
        description = settings.get('description', '')
        
        # Convert config_fields (dict) to field list
        config_fields = []
        for field_id, field_config in settings.get('config_fields', {}).items():
            field_config['id'] = field_id
            config_fields.append(field_config)
        
        return PluginConfigContainer(
            plugin=plugin,
            name=name,
            icon=icon,
            description=description,
            fields_by_plugin=self.fields_by_plugin,
            fields_by_id=self.fields_by_id,
            config_fields=config_fields,
            id=f"plugin_{plugin}_{instance_id}",
            classes="plugin-config"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "validate":
            # Check all fields
            has_errors = False
            for plugin_name, instance_id in self.plugin_instances:
                plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
                for field in plugin_fields:
                    if isinstance(field, TextField) and not field.disabled:  # Ne valider que les champs actifs
                        value = field.input.value
                        is_valid, error_msg = field.validate_input(value)
                        if not is_valid:
                            field.input.add_class('error')
                            field.input.tooltip = error_msg
                            has_errors = True
                            logger.error(f"Validation error in {field.field_id}: {error_msg}")
            
            if has_errors:
                return
            
            # If no errors, collect values
            self.current_config = {}
            for plugin_name, instance_id in self.plugin_instances:
                plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
                if plugin_fields:
                    # Store configuration with instance ID
                    config_key = f"{plugin_name}_{instance_id}"
                    
                    # Read the plugin's settings.yml
                    settings_path = os.path.join('plugins', get_plugin_folder_name(plugin_name), 'settings.yml')
                    yaml = YAML()
                    try:
                        with open(settings_path, 'r') as f:
                            settings = yaml.load(f)
                    except Exception as e:
                        logger.error(f"Error reading {settings_path}: {e}")
                        settings = {}
                    
                    # Collect configuration values - n'inclure que les champs activés
                    config_values = {
                        field.variable_name: field.get_value()
                        for field in plugin_fields
                        if not hasattr(field, 'disabled') or not field.disabled
                    }
                    
                    # Add additional plugin information
                    self.current_config[config_key] = {
                        'plugin_name': plugin_name,
                        'instance_id': instance_id,
                        'name': settings.get('name', plugin_name),
                        'show_name': settings.get('plugin_name', plugin_name),
                        'icon': settings.get('icon', '📦'),
                        'config': config_values
                    }
            
            # Display configurations for verification (optional)
            logger.debug(f"Collected configuration: {self.current_config}")
            
            # Import here to avoid circular imports
            from .execution import ExecutionScreen
            
            # Create execution screen
            execution_screen = ExecutionScreen(self.current_config)
            
            # Replace current screen with execution screen
            self.app.switch_screen(execution_screen)
        elif event.button.id and event.button.id.startswith('browse_'):
            # Handle browse button
            field_id = event.button.id.replace('browse_', '')
            for field in self.query(ConfigField):
                if hasattr(field, 'field_id') and field.field_id == field_id:
                    if hasattr(field, 'on_button_pressed'):
                        field.on_button_pressed(event)
                    break
            
    def action_quit(self) -> None:
        """Handle escape key"""
        self.app.pop_screen()
        
    def action_validate(self) -> None:
        """Handle validate binding"""
        # Find the validate button and simulate a press
        validate_button = self.query_one("#validate")
        self.on_button_pressed(Button.Pressed(validate_button))