from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Input, Checkbox, Select, RadioButton, RadioSet
from textual.reactive import reactive
from textual.message import Message
import os
import yaml

from .utils import setup_logging

logger = setup_logging()

class ConfigField(Vertical):
    """Base class for configuration fields"""
    def __init__(self, plugin_id: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(id=f"field_{field_id}")
        self.plugin_id = plugin_id
        self.field_id = field_id
        self.field_config = field_config
        self.fields_by_id = fields_by_id or {}
        self.disabled = False
        
        # Gérer les dépendances
        self.enabled_if = None
        self.enabled_if_value = True
        
        enabled_if = field_config.get('enabled_if', None)
        if enabled_if:
            if isinstance(enabled_if, dict):
                self.enabled_if = enabled_if.get('field')
                self.enabled_if_value = enabled_if.get('value', True)
            else:
                self.enabled_if = enabled_if
                self.enabled_if_value = field_config.get('enabled_if_value', True)
                
            # Vérifier si le champ dépendant existe
            if self.enabled_if not in self.fields_by_id:
                logger.warning(f"Field {field_id} depends on non-existent field {self.enabled_if}")
            else:
                # S'abonner aux changements du champ dépendant
                dep_field = self.fields_by_id[self.enabled_if]
                self.update_enabled_state(dep_field.value)
            
        # Gérer la variable personnalisée
        self.variable_name = field_config.get('variable', field_id)
            
        # Gérer la valeur par défaut (statique ou dynamique)
        if 'dynamic_default' in field_config:
            self.value = self._get_dynamic_default()
        else:
            self.value = field_config.get('default', None)
            
    class FieldChanged(Message):
        """Message émis quand la valeur d'un champ change"""
        def __init__(self, field_id: str, value: any):
            self.field_id = field_id
            self.value = value
            super().__init__()
            
    def update_enabled_state(self, dep_value) -> None:
        """Met à jour l'état activé/désactivé en fonction de la valeur du champ dépendant"""
        if self.enabled_if:
            # Si la valeur attendue est True, vérifier si la valeur est vraie
            # Si la valeur attendue est autre chose, vérifier l'égalité
            if self.enabled_if_value is True:
                self.disabled = not bool(dep_value)
            else:
                self.disabled = dep_value != self.enabled_if_value
            
            logger.debug(f"Field {self.field_id} enabled state updated: disabled={self.disabled} (dep={self.enabled_if}, value={dep_value}, expected={self.enabled_if_value})")
            
            # Mettre à jour l'état visuel
            if hasattr(self, 'input'):
                self.input.disabled = self.disabled
            if hasattr(self, 'select'):
                self.select.disabled = self.disabled
            if hasattr(self, 'checkbox'):
                self.checkbox.disabled = self.disabled
            if hasattr(self, 'radio_group'):
                for radio in self.radio_group.radios:
                    radio.disabled = self.disabled
                    
    def notify_value_changed(self) -> None:
        """Notifie les autres champs du changement de valeur"""
        # Émettre un message pour notifier du changement
        self.post_message(self.FieldChanged(self.field_id, self.value))
        
        # Mettre à jour les champs dépendants
        for field in self.fields_by_id.values():
            if field.enabled_if == self.field_id:
                field.update_enabled_state(self.value)
            
    def _get_dynamic_default(self) -> str:
        """Get dynamic default value from script"""
        dynamic_config = self.field_config['dynamic_default']
        script_path = os.path.join('plugins', self.plugin_id, dynamic_config['script'])
        
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
            data = module.get_default_value()
            
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
        """Compose the field with label and description"""
        label = self.field_config.get('label', self.field_id)
        description = self.field_config.get('description', '')
        
        # Label et étoile si requis
        with Horizontal():
            yield Label(label, classes="field-label")
            if self.field_config.get('required', False):
                yield Label("*", classes="required-star")
        
        # Description si présente
        if description:
            yield Label(description, classes="field-description")

class TextField(ConfigField):
    """Text input field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        self.input = Input(
            value=str(self.value) if self.value is not None else "",
            placeholder=self.field_config.get('placeholder', ''),
            id=f"input_{self.field_id}"
        )
        
        # Gérer l'état activé/désactivé
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
            self.notify_value_changed()

class DirectoryField(TextField):
    """Directory selection field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        with Horizontal():
            yield Button("Parcourir", id=f"browse_{self.field_id}")
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
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
    def __init__(self, plugin_id: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(plugin_id, field_id, field_config, fields_by_id)
        # Si on a une valeur par défaut dynamique, l'utiliser
        if 'dynamic_default' in field_config:
            self.value = self._get_dynamic_default()
        
    def _get_dynamic_default(self) -> str:
        """Get dynamic default value from script"""
        dynamic_config = self.field_config['dynamic_default']
        script_path = os.path.join('plugins', self.plugin_id, dynamic_config['script'])
        
        try:
            # Import the script module
            import sys
            import importlib.util
            
            # Add plugin directory to path
            plugin_dir = os.path.dirname(script_path)
            if plugin_dir not in sys.path:
                sys.path.append(plugin_dir)
            
            # Import the script
            spec = importlib.util.spec_from_file_location(
                f"{self.plugin_id}_{self.field_id}_default",
                script_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get the default value
                if hasattr(module, dynamic_config.get('function', 'get_default')):
                    value = getattr(module, dynamic_config.get('function', 'get_default'))()
                    if isinstance(value, str):
                        return value
                    else:
                        logger.error(f"Dynamic default script returned invalid format: {value}")
                else:
                    logger.error(f"Dynamic default script missing function: {dynamic_config.get('function', 'get_default')}")
            else:
                logger.error(f"Could not load dynamic default script: {script_path}")
        except Exception as e:
            logger.exception(f"Error loading dynamic default from {script_path}: {e}")
        return self.field_config.get('default', '')
        
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
                            self.notify_value_changed()
                        else:
                            event.input.add_class('error')
                    except (ValueError, AttributeError):
                        event.input.add_class('error')
                else:
                    # Empty value is allowed if field is not required
                    self.value = value
                    event.input.remove_class('error')
                    self.notify_value_changed()

class RadioCheckField(ConfigField):
    """Radio check field group"""
    def __init__(self, plugin_id: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(plugin_id, field_id, field_config, fields_by_id)
        self.options = field_config.get('options', [])
        if not self.options:
            logger.warning(f"No options defined for radio group {field_id}")
            self.options = [("none", "Aucune option")]
        
        # Convertir les options au format attendu
        if isinstance(self.options, dict):
            self.options = [(k, v) for k, v in self.options.items()]
        elif isinstance(self.options, list):
            if all(isinstance(opt, dict) and 'value' in opt and 'label' in opt for opt in self.options):
                self.options = [(opt['value'], opt['label']) for opt in self.options]
            else:
                self.options = [(str(i), str(i)) for i in self.options]
        
        # S'assurer qu'une valeur est sélectionnée
        if not self.value or self.value not in [opt[0] for opt in self.options]:
            self.value = self.options[0][0] if self.options else None
        
    def compose(self) -> ComposeResult:
        """Créer les widgets de configuration"""
        yield from super().compose()
        
        # Créer le groupe de radios
        self.radio_group = RadioSet(id=f"radioset_{self.field_id}")
        for value, label in self.options:
            radio = RadioButton(label, id=f"radio_{self.field_id}_{value}")
            if value == self.value:
                radio.pressed = True
            self.radio_group.mount(radio)
            
        yield self.radio_group
        
    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Gérer le changement de sélection"""
        # Trouver la valeur correspondant au radio sélectionné
        selected_id = event.radio.id
        if selected_id.startswith(f"radio_{self.field_id}_"):
            value = selected_id[len(f"radio_{self.field_id}_"):]
            self.value = value
            self.notify_value_changed()

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        self.checkbox = Checkbox(value=bool(self.value), id=f"checkbox_{self.field_id}")
        yield self.checkbox
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.value = event.value
        self.notify_value_changed()

class SelectField(ConfigField):
    """Select field with options"""
    def __init__(self, plugin_id: str, field_id: str, field_config: dict, fields_by_id: dict = None):
        super().__init__(plugin_id, field_id, field_config, fields_by_id)
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
        # Vérifier si on a un script pour les options dynamiques
        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']
            script_path = os.path.join('plugins', self.plugin_id, dynamic_config['script'])
            
            try:
                # Import the script module
                import sys
                import importlib.util
                
                # Add plugin directory to path
                plugin_dir = os.path.dirname(script_path)
                if plugin_dir not in sys.path:
                    sys.path.append(plugin_dir)
                
                # Import the script
                spec = importlib.util.spec_from_file_location(
                    f"{self.plugin_id}_{self.field_id}_options",
                    script_path
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Get the options
                    if hasattr(module, dynamic_config.get('function', 'get_options')):
                        options = getattr(module, dynamic_config.get('function', 'get_options'))()
                        if isinstance(options, list):
                            return options
                        else:
                            logger.error(f"Dynamic options script returned invalid format: {options}")
                    else:
                        logger.error(f"Dynamic options script missing function: {dynamic_config.get('function', 'get_options')}")
                else:
                    logger.error(f"Could not load dynamic options script: {script_path}")
            except Exception as e:
                logger.exception(f"Error loading dynamic options from {script_path}: {e}")
                return []
        
        # Si pas d'options dynamiques ou en cas d'erreur, utiliser les options statiques
        options = self.field_config.get('options', [])
        if isinstance(options, dict):
            return [(k, v) for k, v in options.items()]
        elif isinstance(options, list):
            if all(isinstance(opt, dict) and 'value' in opt and 'label' in opt for opt in options):
                return [(opt['value'], opt['label']) for opt in options]
            else:
                return [(str(i), str(i)) for i in options]
        return []

    def compose(self) -> ComposeResult:
        """Créer les widgets de configuration"""
        # D'abord, yield les widgets du parent
        yield from super().compose()
        
        # Récupérer les options
        self.options = self._get_options()
        
        # S'assurer qu'il y a au moins une option
        if not self.options:
            self.options = [("none", "Aucune option disponible")]
            
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
            else:
                self.notify_value_changed()
            
    def get_value(self) -> str:
        """Get the current value"""
        return self.value if self.value != "none" else ""

class PluginConfigContainer(Vertical):
    """Container for plugin configuration"""
    def __init__(self, plugin_id: str, title: str, icon_str: str, desc: str, config_fields: list, fields_by_plugin: dict = None, fields_by_id: dict = None, instance_number: int = 1):
        super().__init__(id=f"plugin_{plugin_id}")
        self.plugin_id = plugin_id
        self.plugin_title = f"{title} #{instance_number}" if instance_number > 1 else title
        self.plugin_icon = icon_str
        self.plugin_desc = desc
        self.config_fields = config_fields
        self.fields_by_plugin = fields_by_plugin or {}
        self.fields_by_id = fields_by_id or {}
        self.instance_number = instance_number
        
    def on_config_field_field_changed(self, event: ConfigField.FieldChanged) -> None:
        """Gérer les changements de valeur des champs"""
        # Mettre à jour les champs dépendants
        for field in self.fields_by_id.values():
            if field.enabled_if == event.field_id:
                field.update_enabled_state(event.value)

    def compose(self) -> ComposeResult:
        """Compose the plugin configuration container"""
        # En-tête
        with Horizontal(classes="plugin-header"):
            yield Label(self.plugin_icon, classes="plugin-icon")
            yield Label(self.plugin_title, classes="plugin-title")
        
        if self.plugin_desc:
            yield Label(self.plugin_desc, classes="plugin-description")
        
        if not self.config_fields:
            with Horizontal(classes="no-config-container"):
                yield Label("ℹ️", classes="no-config-icon")
                yield Label(f"Rien à configurer pour {self.plugin_title}", classes="no-config")
            return
        
        # Conteneur des champs
        with Vertical(classes="fields-container"):
            for field_config in self.config_fields:
                field_id = field_config.get('id')
                if not field_id:
                    logger.warning(f"Field without id in plugin {self.plugin_id}")
                    continue
                
                field_type = field_config.get('type', 'text')
                field_class = {
                    'text': TextField,
                    'directory': DirectoryField,
                    'checkbox': CheckboxField,
                    'select': SelectField,
                    'ip': IPField,
                    'radio': RadioCheckField
                }.get(field_type, TextField)
                
                field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
                self.fields_by_id[field_id] = field
                yield field

    def get_config(self) -> dict:
        """Get the configuration values"""
        return {field.variable_name: field.value for field in self.fields_by_id.values() if not field.disabled}

class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [("esc", "quit", "Quitter")]
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/config.css")

    def __init__(self, plugins: list, name: str | None = None):
        super().__init__(name=name)
        # Compter les occurrences de chaque plugin
        plugin_counts = {}
        self.plugins = []
        for plugin in plugins:
            plugin_counts[plugin] = plugin_counts.get(plugin, 0) + 1
            self.plugins.append((plugin, plugin_counts[plugin]))
        self.containers = {}
        self._instance_counts = {}
        self.fields_by_plugin = {}

    def compose(self) -> ComposeResult:
        """Compose the configuration screen"""
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            # Réinitialiser les compteurs d'instances
            self._instance_counts = {}
            
            for plugin, instance_number in self.plugins:
                container = self._create_plugin_config(plugin, instance_number)
                if container:
                    self.containers[plugin] = container
                    yield container
        
        with Container(id="button-container"):
            yield Button("Valider", id="validate", variant="primary")
            yield Button("Annuler", id="cancel", variant="error")
        
        yield Footer()

    def _create_plugin_config(self, plugin: str, instance_number: int = 1) -> PluginConfigContainer | None:
        """Create a plugin configuration container"""
        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', plugin, 'settings.yml')
        
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
        except Exception as e:
            logger.exception(f"Error loading settings for {plugin}: {e}")
            return None

        # Convertir les champs de config_fields (dict) en liste
        config_fields = []
        for field_id, field_config in settings.get('config_fields', {}).items():
            field_config['id'] = field_id
            config_fields.append(field_config)

        # Stocker les champs dans fields_by_plugin
        self.fields_by_plugin[plugin] = {}
        
        return PluginConfigContainer(
            plugin_id=f"{plugin}_{instance_number}",
            title=settings.get('name', plugin),
            icon_str=settings.get('icon', '📦'),
            desc=settings.get('description', ''),
            config_fields=config_fields,
            fields_by_plugin=self.fields_by_plugin,
            fields_by_id=self.fields_by_plugin[plugin],
            instance_number=instance_number
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "validate":
            self.action_validate()
        elif event.button.id == "cancel":
            self.action_quit()
            
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Gère le changement d'état d'une case à cocher"""
        # Trouver le champ qui a émis l'événement
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changed: {checkbox_id} -> {event.value}")
        
        for field in self.fields_by_id.values():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.plugin_id}_{field.field_id}":
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

    def action_validate(self) -> None:
        """Save configuration and close"""
        config = {plugin: container.get_config() 
                 for plugin, container in self.containers.items()}
        self.app.save_config(config)
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Close without saving"""
        self.app.pop_screen()
