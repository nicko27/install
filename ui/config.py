from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Input, Checkbox, Select
from textual.widget import Widget
from textual.reactive import reactive
import os
import yaml

from .utils import setup_logging

logger = setup_logging()

class ConfigField(Vertical):
    """Base class for configuration fields"""
    def __init__(self, plugin_path: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__()
        self.plugin_path = plugin_path
        self.field_id = field_id
        self.field_config = field_config
        self.fields_by_id = fields_by_id or {}
        
        # Si le champ a une dépendance enabled_if
        if 'enabled_if' in field_config:
            self.enabled_if = field_config['enabled_if']
        else:
            self.enabled_if = None
        self.variable_name = field_config.get('variable', field_id)
        
        # Gérer la valeur par défaut (statique ou dynamique)
        if 'dynamic_default' in field_config:
            self.value = self._get_dynamic_default()
        else:
            self.value = field_config.get('default', None)
            
    def _get_dynamic_default(self) -> str:
        """Get dynamic default value from script"""
        dynamic_config = self.field_config['dynamic_default']
        script_path = os.path.join('plugins', self.plugin_path, dynamic_config['script'])
        
        try:
            # Import the script module
            import sys
            import importlib.util
            
            # Add plugin directory to path
            plugin_dir = os.path.dirname(script_path)
            if plugin_dir not in sys.path:
                sys.path.append(plugin_dir)
            
            # Import the script
            spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
            if not spec:
                logger.error("Failed to create module spec")
                return None
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get the data
            data = module.get_default_ip()
            
            # Get the value
            if isinstance(data, dict):
                return str(data.get('value', ''))
            elif isinstance(data, (str, int, float)):
                return str(data)
            return None
            
        except Exception as e:
            logger.exception(f"Error loading dynamic default from {script_path}: {e}")
            return None

    def compose(self) -> ComposeResult:
        label = self.field_config.get('label', self.field_id)
        description = self.field_config.get('description', '')
        
        with Horizontal():
            if description:
                yield Label(description, classes="field-description")
            else:
                yield Label(label, classes="field-label")
            if self.field_config.get('required', False):
                yield Label("*", classes="required-star")
                
        # Vérifier si le champ doit être activé ou non
        if self.enabled_if:
            dep_field = self.fields_by_id.get(self.enabled_if['field'])
            logger.debug(f"Field {self.field_id}: enabled_if={self.enabled_if}, dep_field={dep_field and dep_field.field_id}, dep_value={dep_field and dep_field.value}")
            if dep_field and dep_field.value != self.enabled_if['value']:
                logger.debug(f"Field {self.field_id} should be initially disabled")
                self.disabled = True
                self.add_class('disabled')

    def get_value(self):
        return self.value

class TextField(ConfigField):
    """Text input field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        self.input = Input(
            placeholder=self.field_config.get('placeholder', ''),
            value=self.value or '',
            id=f"input_{self.field_id}"
        )
        # Toujours initialiser à l'état activé d'abord
        self.input.disabled = False
        self.input.remove_class('disabled')
        
        if self.disabled:
            logger.debug(f"TextField {self.field_id} is initially disabled")
            self.input.disabled = True
            self.input.add_class('disabled')
        yield self.input

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            value = event.value
            
            # Validation
            if 'validate' in self.field_config:
                validate_type = self.field_config['validate']
                
                if validate_type == 'no_spaces':
                    if ' ' in value:
                        self.input.add_class('error')
                        return
                    else:
                        self.input.remove_class('error')
                        
            self.value = value

class DirectoryField(TextField):
    """Directory selection field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Button("Parcourir...", id=f"browse_{self.field_id}")
        
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == f"browse_{self.field_id}":
            from subprocess import Popen, PIPE
            process = Popen(['zenity', '--file-selection', '--directory'], stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                selected_dir = stdout.decode().strip()
                self.input.value = selected_dir
                self.value = selected_dir

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
            value=self.value or False
        )
        yield self.checkbox

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == f"checkbox_{self.plugin_path}_{self.field_id}":
            self.value = event.value

class SelectField(ConfigField):
    """Select field with options"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        # Récupérer les options au format (value, label)
        self.options = self._get_options()
        if not self.options:
            logger.warning(f"No options available for select {self.field_id}")
            self.options = [("none", "Aucune option disponible")]
        
        # S'assurer que la valeur par défaut est dans les options disponibles
        available_values = [opt[1] for opt in self.options]  # La valeur est en deuxième position
        if not self.value or str(self.value) not in available_values:
            self.value = available_values[0] if available_values else None
        
        # Créer le composant Select avec les options
        self.select = Select(
            options=self.options,  # Les options sont déjà au bon format (value, label)
            value=self.value,
            id=f"select_{self.field_id}",
            allow_blank=self.field_config.get('allow_blank', False)
        )
        # Toujours initialiser à l'état activé d'abord
        self.select.disabled = False
        self.select.remove_class('disabled')
        
        if self.disabled:
            logger.debug(f"SelectField {self.field_id} is initially disabled")
            self.select.disabled = True
            self.select.add_class('disabled')
        yield self.select

    def _get_options(self) -> list:
        """Get options for the select field, either static or dynamic"""
        if 'options' in self.field_config:
            logger.debug(f"Using static options: {self.field_config['options']}")
            # Pour les options statiques
            options = self.field_config['options']
            if isinstance(options[0], dict):
                # Format avec value/label
                return [(opt['label'], opt['value']) for opt in options]
            else:
                # Format simple (même valeur pour label et value)
                return [(str(opt), str(opt)) for opt in options]
        
        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']
            script_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', self.plugin_path, dynamic_config['script'])
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
                    return [("error", "Erreur de chargement du module")]
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get the data
                func_name = next(name for name in dir(module) 
                              if name.startswith('get_') and callable(getattr(module, name)))
                logger.debug(f"Found function: {func_name}")
                
                data = getattr(module, func_name)()
                logger.debug(f"Got data: {data}")
                
                # Format the options using the template or label_key
                value_key = dynamic_config.get('value_key', 'value')
                label_template = dynamic_config.get('label_template')
                label_key = dynamic_config.get('label_key', 'label')
                
                # Ensure we have at least one option
                if not data:
                    logger.warning("No data returned from script")
                    return [("no_data", "Aucune donnée disponible")]
                
                options = []
                for item in data:
                    if isinstance(item, dict):
                        value = str(item.get(value_key, ''))
                        if label_template:
                            label = label_template.format(**item)
                        else:
                            label = str(item.get(label_key, value))
                    else:
                        # Si l'item n'est pas un dict, utiliser la même valeur pour value et label
                        value = str(item)
                        label = str(item)
                    options.append((label, value))  # Inverser l'ordre pour le composant Select
                logger.debug(f"Final options: {options}")
                return options
                
            except Exception as e:
                logger.exception(f"Error loading dynamic options from {script_path}: {e}")
                return [("error", "Erreur de chargement des options")]
            finally:
                if os.path.dirname(script_path) in sys.path:
                    sys.path.remove(os.path.dirname(script_path))
        
        logger.debug("No options found in config")
        return []

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == f"select_{self.field_id}":
            self.value = event.value  # event.value contient déjà la valeur (pas le label)
            logger.debug(f"Select changed to: {self.value}")
            
    def get_value(self) -> str:
        """Get the current value"""
        return self.value if self.value != "none" else ""

class PluginConfigContainer(Vertical):
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
        # Titre et description
        with Vertical(classes="plugin-header"):
            yield Label(f"{self.plugin_icon} {self.plugin_title}", classes="plugin-title")
            if self.plugin_description:
                yield Label(self.plugin_description, classes="plugin-description")
        
        if not self.config_fields:
            with Horizontal(classes="no-config-container"):
                yield Label("ℹ️", classes="no-config-icon")
                yield Label(f"Rien à configurer pour {self.plugin_title}", classes="no-config")
            return

        # Champs de configuration
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
                'select': SelectField
            }.get(field_type, TextField)
            
            # Créer le champ avec accès aux autres champs
            field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
            self.fields_by_plugin[self.plugin_id][field_id] = field
            self.fields_by_id[field_id] = field
            
            # Si c'est une checkbox, ajouter un gestionnaire d'événements
            if field_type == 'checkbox':
                field.on_checkbox_changed = self.on_checkbox_changed
            
            yield field
            
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gère le changement d'état d'une case à cocher"""
        # Trouver le champ qui a émis l'événement
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changed: {checkbox_id} -> {event.value}")
        
        for field in self.fields_by_plugin[self.plugin_id].values():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.plugin_path}_{field.field_id}":
                logger.debug(f"Found matching checkbox field: {field.field_id}")
                field.value = event.value
                
                # Mettre à jour les champs dépendants
                for dependent_field in self.fields_by_id.values():
                    if dependent_field.enabled_if and dependent_field.enabled_if['field'] == field.field_id:
                        logger.debug(f"Found dependent field: {dependent_field.field_id} with enabled_if={dependent_field.enabled_if}")
                        
                        # Handle any widget type that can be disabled
                        for widget_type in [Input, Select, Button]:
                            try:
                                widget = dependent_field.query_one(widget_type)
                                logger.debug(f"Found widget of type {widget_type.__name__} for field {dependent_field.field_id}")
                            except Exception:
                                continue
                                
                            # Si on arrive ici, c'est qu'on a trouvé le widget
                            should_disable = field.value != dependent_field.enabled_if['value']
                            logger.debug(f"Field {dependent_field.field_id}: should_disable={should_disable} (checkbox value={field.value}, enabled_if value={dependent_field.enabled_if['value']})")
                            
                            # Toujours retirer les classes existantes d'abord
                            dependent_field.remove_class('disabled')
                            dependent_field.disabled = False
                            widget.remove_class('disabled')
                            widget.disabled = False
                            
                            if should_disable:
                                logger.debug(f"Disabling widget for field {dependent_field.field_id}")
                                dependent_field.add_class('disabled')
                                dependent_field.disabled = True
                                widget.add_class('disabled')
                                widget.disabled = True
                                # Clear IP fields when disabled to prevent invalid config
                                if isinstance(widget, Input) and isinstance(dependent_field, IPField):
                                    widget.value = ''
                            else:
                                logger.debug(f"Enabling widget for field {dependent_field.field_id}")
                break
            





class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [
        ("esc", "quit", "Quitter"),
    ]
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/config.css")

    def __init__(self, plugin_instances: list, name: str | None = None) -> None:
        super().__init__(name=name)
        self.plugin_instances = plugin_instances  # Liste de tuples (plugin_name, instance_id)
        self.current_config = {}
        self.fields_by_plugin = {}

    def compose(self) -> ComposeResult:
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            for plugin_name, instance_id in self.plugin_instances:
                yield self._create_plugin_config(plugin_name, instance_id)
            
        with Horizontal(id="button-container"):
            yield Button("Annuler", id="cancel", variant="error")
            yield Button("Executer", id="validate", variant="primary")
            
        yield Footer()

    def _create_plugin_config(self, plugin: str, instance_id: int) -> Widget:
        """Create configuration fields for a plugin"""
        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', plugin, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
        except Exception as e:
            logger.exception(f"Error loading settings for {plugin}: {e}")
            return Container()
            
        # Stocker les champs pour pouvoir les retrouver plus tard
        self.fields_by_plugin[plugin] = {}
        fields_by_id = {}

        name = settings.get('name', plugin)
        icon = settings.get('icon', '📦')
        description = settings.get('description', '')
        
        # Convertir les champs de config_fields (dict) en liste de champs
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
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            id=f"plugin_{plugin}_{instance_id}",
            classes="plugin-config"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "validate":
            # Collect all field values
            self.current_config = {}
            for plugin_name, instance_id in self.plugin_instances:
                plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
                if plugin_fields:
                    # Stocker la configuration avec l'ID d'instance
                    config_key = f"{plugin_name}_{instance_id}"
                    self.current_config[config_key] = {
                        field.variable_name: field.get_value()
                        for field in plugin_fields
                    }
            
            # Créer la liste des plugins avec leurs infos
            plugin_list = []
            for plugin_name, instance_id in self.plugin_instances:
                # Lire le settings.yml du plugin
                settings_path = os.path.join('plugins', plugin_name, 'settings.yml')
                try:
                    with open(settings_path, 'r') as f:
                        settings = yaml.safe_load(f)
                    
                    # Ajouter les infos du plugin
                    plugin_list.append({
                        'plugin': plugin_name,
                        'instance_id': instance_id,
                        'name': settings.get('name', plugin_name),
                        'icon': settings.get('icon', '📦')
                    })
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture de {settings_path}: {e}")
                    # Fallback sur les valeurs par défaut
                    plugin_list.append({
                        'plugin': plugin_name,
                        'instance_id': instance_id,
                        'name': plugin_name,
                        'icon': '📦'
                    })
            
            # Import here to avoid circular imports
            from .execution import ExecutionScreen
            
            # Créer l'écran d'exécution
            execution_screen = ExecutionScreen(self.current_config)
            
            # Remplacer l'écran actuel par l'écran d'exécution
            self.app.switch_screen(execution_screen)
        elif event.button.id and event.button.id.startswith('browse_'):
            # TODO: Implement directory browser
            pass
            
    def action_quit(self) -> None:
        """Handle escape key"""
        self.app.pop_screen()
        
        
    def action_validate(self) -> None:
        """Handle validate binding"""
        # Collect all field values
        self.current_config = {}
        for plugin in self.plugins:
            plugin_fields = self.query(f"#plugin_{plugin} ConfigField")
            if plugin_fields:
                self.current_config[plugin] = {
                    field.variable_name: field.get_value()
                    for field in plugin_fields
                }
        self.app.pop_screen()
