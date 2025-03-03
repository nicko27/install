from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer, Horizontal
from textual.widgets import Header, Footer, Button
import os
from ruamel.yaml import YAML

from .utils import setup_logging
from .choice import get_plugin_folder_name
from .components.plugin_config_container import PluginConfigContainer
from .components.text_field import TextField

logger = setup_logging()

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

    def compose(self) -> ComposeResult:
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            for plugin_name, instance_id in self.plugin_instances:
                yield self._create_plugin_config(plugin_name, instance_id)
            
        with Horizontal(id="button-container"):
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Execute", id="validate", variant="primary")
            
        yield Footer()

    def _create_plugin_config(self, plugin: str, instance_id: int) -> Container:
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
        fields_by_id = {}

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
            # Check all fields
            has_errors = False
            for plugin_name, instance_id in self.plugin_instances:
                plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
                for field in plugin_fields:
                    if isinstance(field, TextField):
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
                    
                    # Collect configuration values
                    config_values = {
                        field.variable_name: field.get_value()
                        for field in plugin_fields
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
