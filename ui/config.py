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
    def __init__(self, plugin_path: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(plugin_path, field_id, field_config, fields_by_id)
        self.default_value = field_config.get('default', None)
        self.options = self._get_options()
        if not self.options:
            logger.warning(f"No options available for select {self.field_id}")
            self.options = [("none", "Aucune option disponible")]
            
        # S'assurer que la valeur par défaut est dans les options
        available_values = [opt[0] for opt in self.options]
        if not self.value or self.value not in available_values:
            self.value = available_values[0] if available_values else None
            
    def _get_options(self) -> list:
        """Récupérer les options disponibles"""
        available_values = self.field_config.get('options', [])
        
        # Convertir en liste de tuples (value, label)
        options = [
            (opt['value'], opt['label']) 
            for opt in available_values 
            if isinstance(opt, dict) and 'value' in opt and 'label' in opt
        ]
        
        if not options:
            logger.warning(f"No options available for select {self.field_id}")
        
        return options

    def compose(self) -> ComposeResult:
        """Créer les widgets de configuration"""
        # D'abord, yield les widgets du parent
        yield from super().compose()
        
        # Récupérer les options
        self.options = self._get_options()
        
        # Déterminer la valeur initiale
        value_label = (
            self.default_value if self.default_value 
            else (self.options[0][0] if self.options else None)
        )
        
        # Créer les options dans le format (label, value) pour le Select
        select_options = [(opt[1], opt[0]) for opt in self.options]
        
        # Créer et yield le Select
        self.select = Select(
            options=select_options,
            value=value_label,
            id=f"select_{self.field_id}",
        )
        yield self.select

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == f"select_{self.field_id}":
            # event.value contient le label, trouver la valeur correspondante
            self.value = next((opt[0] for opt in self.options if opt[1] == event.value), None)
            logger.debug(f"Select changed to: {self.value} (label: {event.value})")
            if self.value is None:
                logger.error(f"Could not find value for label: {event.value}")
            
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
    
    def __init__(self, plugin: str, name: str, icon: str, description: str, fields_by_plugin: dict, fields_by_id: dict, config_fields: list, instance_number: int = 1, **kwargs):
        super().__init__(**kwargs)
        # Set the reactive attributes
        self.plugin_id = plugin
        self.plugin_title = f"{name} #{instance_number}" if instance_number > 1 else name
        self.plugin_icon = icon
        self.plugin_description = description
        # Non-reactive attributes
        self.fields_by_plugin = fields_by_plugin
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields
        self.instance_number = instance_number

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
            # Stocker le champ dans fields_by_id
            self.fields_by_id[field_id] = field
            yield field
            
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

    def __init__(self, plugins: list, name: str | None = None) -> None:
        super().__init__(name=name)
        # Compter les occurrences de chaque plugin
        plugin_counts = {}
        self.plugins = []
        for plugin in plugins:
            plugin_counts[plugin] = plugin_counts.get(plugin, 0) + 1
            self.plugins.append((plugin, plugin_counts[plugin]))
        self.current_config = {}
        self.fields_by_plugin = {}

    def compose(self) -> ComposeResult:
        """Compose the plugin configuration screen"""
        # Titre principal
        yield Header()
        
        # Conteneur principal pour les plugins
        with Container(id="plugin-config-container"):
            # Créer un conteneur de configuration pour chaque plugin
            for plugin, instance_number in self.plugins:
                plugin_info = self.plugins_by_id.get(plugin, {})
                
                # Créer le conteneur de configuration du plugin
                plugin_container = self._create_plugin_config(
                    (plugin, plugin_info, instance_number)
                )
                
                yield plugin_container
        
        # Conteneur des boutons
        with Container(id="button-container"):
            yield Button("Valider", id="validate", variant="primary")
            yield Button("Annuler", id="cancel", variant="error")
        
        yield Footer()

    def _create_plugin_config(self, plugin_info: tuple) -> Widget:
        """Create configuration fields for a plugin"""
        plugin, instance_number = plugin_info
        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', plugin, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
        except Exception as e:
            logger.exception(f"Error loading settings for {plugin}: {e}")
            return Container()
            
        # Stocker les champs pour pouvoir les retrouver plus tard
        if plugin not in self.fields_by_plugin:
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
        
        container = PluginConfigContainer(
            plugin=plugin,
            name=name,
            icon=icon,
            description=description,
            fields_by_plugin=self.fields_by_plugin,
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            instance_number=instance_number,
            id=f"plugin_{plugin}_{instance_number}",
            classes="plugin-config"
        )
        
        # Stocker les champs dans le dictionnaire du plugin
        self.fields_by_plugin[plugin][instance_number] = fields_by_id
        
        return container

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "validate":
            # Collect all field values
            self.current_config = {}
            for plugin, instance_number in self.plugins:
                plugin_key = f"{plugin}_{instance_number}"
                plugin_fields = self.query(f"#plugin_{plugin}_{instance_number} ConfigField")
                if plugin_fields:
                    # Stocker la configuration sous le nom du plugin (sans numéro d'instance)
                    if plugin not in self.current_config:
                        self.current_config[plugin] = []
                    self.current_config[plugin].append({
                        field.variable_name: field.get_value()
                        for field in plugin_fields
                    })
            
            # Créer la liste des plugins avec leurs infos
            plugin_list = []
            processed_plugins = set()
            for plugin, instance_number in self.plugins:
                # Ne traiter chaque plugin qu'une fois pour les infos
                if plugin in processed_plugins:
                    continue
                processed_plugins.add(plugin)
                
                # Lire le settings.yml du plugin
                settings_path = os.path.join('plugins', plugin, 'settings.yml')
                try:
                    with open(settings_path, 'r') as f:
                        settings = yaml.safe_load(f)
                    
                    # Ajouter les infos du plugin
                    plugin_list.append({
                        'plugin': plugin,
                        'name': settings.get('name', plugin),
                        'icon': settings.get('icon', '📦'),
                        'config': self.current_config.get(plugin, [])
                    })
                except Exception as e:
                    logger.error(f"Erreur lors de la lecture de {settings_path}: {e}")
                    # Fallback sur les valeurs par défaut
                    plugin_list.append({
                        'plugin': plugin,
                        'name': plugin,
                        'icon': '📦',
                        'config': self.current_config.get(plugin, [])
                    })
            
            # Import here to avoid circular imports
            from .execution import PluginExecution
            
            # Créer l'écran d'exécution
            execution_screen = PluginExecution(plugin_list, self.current_config)
            
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
        for plugin, instance_number in self.plugins:
            plugin_fields = self.query(f"#plugin_{plugin}_{instance_number} ConfigField")
            if plugin_fields:
                if plugin not in self.current_config:
                    self.current_config[plugin] = []
                self.current_config[plugin].append({
                    field.variable_name: field.get_value()
                    for field in plugin_fields
                })
        self.app.pop_screen(self.current_config)
