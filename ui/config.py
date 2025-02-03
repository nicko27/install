from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Input, Checkbox, Select
from textual.widget import Widget
from textual.reactive import reactive
import os
import yaml

class ConfigField(Vertical):
    """Base class for configuration fields"""
    def __init__(self, plugin_path: str, field_id: str, field_config: dict):
        super().__init__()
        self.plugin_path = plugin_path
        self.field_id = field_id
        self.field_config = field_config
        self.value = field_config.get('default', None)
        self.variable_name = field_config.get('variable', field_id)

    def compose(self) -> ComposeResult:
        label = self.field_config.get('label', self.field_id)
        description = self.field_config.get('description', '')
        display_text = description if description else label
        
        with Horizontal():
            yield Label(display_text, classes="field-label")
            if self.field_config.get('required', False):
                yield Label("*", classes="required-star")

    def get_value(self):
        return self.value

class TextField(ConfigField):
    """Text input field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Input(
            placeholder=self.field_config.get('placeholder', ''),
            id=f"input_{self.field_id}"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        self.value = event.value

class DirectoryField(TextField):
    """Directory selection field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Button("Parcourir...", id=f"browse_{self.field_id}")
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == f"browse_{self.field_id}":
            # TODO: Implémenter la sélection de dossier avec une commande shell
            # Par exemple : zenity --file-selection --directory
            pass

class IPField(TextField):
    """IP address input field with validation"""
    def on_input_changed(self, event: Input.Changed) -> None:
        # TODO: Add IP validation
        self.value = event.value

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Checkbox(id=f"checkbox_{self.field_id}", value=self.field_config.get('default', False))
            yield Label(self.field_config['label'])
        yield Label(self.field_config['description'], classes="field-description")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.value = event.value

class SelectField(ConfigField):
    """Select field with options"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        options = self._get_options()
        yield Select(
            options=options,
            id=f"select_{self.field_id}"
        )

    def _get_options(self) -> list:
        """Get options for the select field, either static or dynamic"""
        if 'options' in self.field_config:
            return [(opt, opt) for opt in self.field_config['options']]
        
        if 'dynamic_options' in self.field_config:
            dynamic_config = self.field_config['dynamic_options']
            script_path = os.path.join('plugins', os.path.dirname(self.plugin_path), dynamic_config['script'])
            
            try:
                # Import the script module
                import importlib.util
                spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get the data
                if hasattr(module, 'get_network_interfaces'):
                    data = module.get_network_interfaces()
                    
                    # Format the options using the template
                    value_key = dynamic_config['value_key']
                    label_template = dynamic_config['label_template']
                    
                    return [
                        (item[value_key], label_template.format(**item))
                        for item in data
                    ]
            except Exception as e:
                print(f"Error loading dynamic options from {script_path}: {e}")
                return [("error", "Erreur de chargement des options")]
        
        return []

    def on_select_changed(self, event: Select.Changed) -> None:
        self.value = event.value

class PluginConfig(Screen):
    """Plugin configuration screen"""
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/config.css")

    def __init__(self, plugins: list, name: str | None = None) -> None:
        super().__init__(name=name)
        self.plugins = plugins
        self.current_config = {}

    def compose(self) -> ComposeResult:
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            for plugin in self.plugins:
                yield self._create_plugin_config(plugin)
        
        with Horizontal(id="button-container"):
            yield Button("Annuler", id="cancel", variant="error")
            yield Button("Valider", id="validate", variant="primary")
        
        yield Footer()

    def _create_plugin_config(self, plugin: str) -> Widget:
        """Create configuration fields for a plugin"""
        settings_path = os.path.join('plugins', plugin, 'settings.yml')
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading settings for {plugin}: {e}")
            return Container()

        class PluginConfigContainer(Vertical):
            def compose(self) -> ComposeResult:
                yield Label(f"{icon} {name}", classes="plugin-title")
                
                if not config_fields:
                    with Horizontal(classes="no-config-container"):
                        yield Label("ℹ️", classes="no-config-icon")
                        yield Label(f"Rien à configurer pour {name}", classes="no-config")
                    return

                for field_id, field_config in config_fields.items():
                    field_type = field_config.get('type', 'text')
                    field_class = {
                        'text': TextField,
                        'directory': DirectoryField,
                        'ip': IPField,
                        'checkbox': CheckboxField,
                        'select': SelectField
                    }.get(field_type, TextField)
                    
                    yield field_class(plugin, field_id, field_config)

        name = settings.get('name', plugin)
        icon = settings.get('icon', '📦')
        config_fields = settings.get('config_fields', {})
        
        return PluginConfigContainer(id=f"plugin_{plugin}", classes="plugin-config")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.exit()
        elif event.button.id == "validate":
            # Collect all field values
            self.current_config = {}
            for plugin in self.plugins:
                plugin_container = self.query_one(f"#plugin_{plugin}", Vertical)
                if not plugin_container:
                    continue
                
                self.current_config[plugin] = {}
                for field in plugin_container.query(ConfigField):
                    self.current_config[plugin][field.field_id] = field.get_value()
            
            self.exit(self.current_config)
        elif event.button.id and event.button.id.startswith('browse_'):
            # TODO: Implement directory browser
            pass
