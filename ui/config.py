"""Plugin configuration UI"""
import os
import traceback
from textual.app import ComposeResult
from textual.containers import Container, VerticalGroup, HorizontalGroup, ScrollableContainer
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Label, Header, Footer
from ruamel.yaml import YAML

from .components.base.component_registry import ComponentRegistry
from .choice import get_plugin_folder_name

# Configure logging
from .logging import get_logger
logger = get_logger('config')

# Discover all available components and plugins
ComponentRegistry.discover()

# Load validation plugins
from .components.validation import list_plugins
logger.info(f"Available validation plugins: {list_plugins()}")

class PluginConfigContainer(VerticalGroup):
    """Container for plugin configuration fields"""
    
    def __init__(self, plugin: str, name: str, icon: str, description: str,
                 config_fields: list, id: str = None, classes: str = None):
        super().__init__(id=id, classes=classes)
        self.plugin_id = plugin
        self.plugin_name = name
        self.plugin_icon = icon
        self.plugin_description = description
        self.config_fields = config_fields
        self.fields_by_id = {}
        
    def compose(self) -> ComposeResult:
        """Create configuration fields"""
        logger.debug(f"=== Starting composition of plugin {self.plugin_id} ===")
        logger.debug(f"Plugin name: {self.plugin_name}")
        logger.debug(f"Plugin icon: {self.plugin_icon}")
        logger.debug(f"Plugin description: {self.plugin_description}")
        logger.debug(f"Number of fields: {len(self.config_fields)}")
        logger.debug(f"Fields list: {self.config_fields}")
        
        with Container(classes="plugin-container"):
            # Plugin header
            logger.debug("Creating plugin header")
            with VerticalGroup(classes="plugin-header"):
                logger.debug(f"Adding title: {self.plugin_icon} {self.plugin_name}")
                yield Label(f"{self.plugin_icon} {self.plugin_name}", classes="plugin-title")
                if self.plugin_description:
                    logger.debug(f"Adding description: {self.plugin_description}")
                    yield Label(self.plugin_description, classes="plugin-description")
                logger.debug("Header created successfully")
            
                # Configuration fields
                logger.debug("=== Starting field creation ===")
                with VerticalGroup(classes="plugin-fields"):
                    logger.debug(f"Created fields group with class 'plugin-fields'")
                    for field_config in self.config_fields:
                        field_id = field_config.get('id')
                        if not field_id:
                            logger.error(f"Field config missing id: {field_config}")
                            continue
                            
                        field_type = field_config.get('type', 'text')
                        logger.debug(f"=== Processing field {field_id} (type: {field_type}) ===")
                        logger.debug(f"Complete field config: {field_config}")
                        
                        # Get field class from registry
                        logger.debug(f"Looking up component for type '{field_type}'")
                        field_class = ComponentRegistry.get(field_type)
                        if not field_class:
                            logger.error(f"No component found for field type: {field_type}")
                            continue
                            
                        logger.debug(f"Found field class: {field_class.__name__}")
                        
                        # Create field instance
                        try:
                            logger.debug(f"Creating field instance with plugin_id={self.plugin_id}, field_id={field_id}")
                            field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
                            logger.debug(f"Field instance created successfully: {field.__class__.__name__}")
                            self.fields_by_id[field_id] = field
                            logger.debug(f"Field added to fields_by_id dictionary")
                            
                            # Vérifier si le champ a une méthode compose valide
                            if not hasattr(field, 'compose') or not callable(field.compose):
                                logger.error(f"Field {field_id} ({field.__class__.__name__}) missing compose method")
                                continue
                                
                            try:
                                logger.debug(f"Composing field {field_id}")
                                yield field
                                logger.debug(f"Field {field_id} composed successfully")
                            except Exception as compose_error:
                                logger.error(f"Error composing field {field_id}: {str(compose_error)}")
                                logger.error(f"Composition traceback: {traceback.format_exc()}")
                                
                        except Exception as e:
                            logger.error(f"Error creating field {field_id} of type {field_type}: {str(e)}")
                            logger.error(f"Creation traceback: {traceback.format_exc()}")
                logger.debug("Finished creating all fields")
            
class PluginConfig(Screen):
    """Screen for plugin configuration"""
    BINDINGS = [
        ("esc", "quit", "Quit"),
    ]
    
    def __init__(self, plugin_instances: list, name: str | None = None) -> None:
        super().__init__(name=name)
        self.plugin_instances = plugin_instances  # List of tuples (plugin_name, instance_id)
        self.current_config = {}
        
    def compose(self) -> ComposeResult:
        """Create the configuration screen"""
        logger.debug("=== Starting configuration screen creation ===")
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            logger.debug(f"Created ScrollableContainer with id 'config-container'")
            logger.debug(f"Processing {len(self.plugin_instances)} plugin instances")
            for plugin_name, instance_id in self.plugin_instances:
                logger.debug(f"=== Creating config for plugin {plugin_name} (instance {instance_id}) ===")
                try:
                    plugin_container = self._create_plugin_config(plugin_name, instance_id)
                    logger.debug(f"Created container: {plugin_container.__class__.__name__}")
                    yield plugin_container
                except Exception as e:
                    logger.error(f"Error creating config for plugin {plugin_name}: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
            
        with HorizontalGroup(id="action_buttons"):
            logger.debug("Creating action buttons")
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Execute", id="validate", variant="primary")
            
        yield Footer()
        logger.debug("Configuration screen creation complete")
    
    def _create_plugin_config(self, plugin: str, instance_id: int) -> PluginConfigContainer:
        """Create configuration fields for a plugin"""
        logger.debug(f"=== Creating config for plugin {plugin} (instance {instance_id}) ===")
        # Get plugin folder name
        plugin_folder = get_plugin_folder_name(plugin)
        # Utiliser os.path.abspath pour garantir des chemins absolus
        base_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_dir = os.path.join(base_dir, '..', 'plugins', plugin_folder)
        logger.debug(f"Plugin directory: {plugin_dir}")
        config_file = None
        
        # Try config.yaml first, then settings.yml
        for filename in ['config.yaml', 'settings.yml']:
            test_file = os.path.join(plugin_dir, filename)
            logger.info(f"Checking for config file: {test_file}")
            if os.path.exists(test_file):
                config_file = test_file
                logger.info(f"Found config file: {config_file}")
                break
                
        if not config_file:
            logger.error(f"Invalid config file for plugin {plugin} in directory {plugin_dir}")
            return PluginConfigContainer(
                plugin=plugin,
                name=f"Error: {plugin}",
                icon="⚠️",
                description="Config file not found",
                config_fields=[],
                id=f"plugin_{plugin}_error"
            )
            
        # Load plugin settings
        yaml = YAML()
        try:
            with open(config_file, 'r') as f:
                # Utiliser safe_load à la place de load
                config = yaml.load(f)
                
            # Get plugin metadata
            plugin_name = config.get('name', plugin)
            plugin_icon = config.get('icon', '🔧')
            plugin_description = config.get('description', '')
            logger.info(f"Plugin metadata: name={plugin_name}, icon={plugin_icon}")
            
            # Get configuration fields and convert to list format
            config_fields_dict = config.get('config_fields', {})
            logger.info(f"Found {len(config_fields_dict)} fields in config")
            config_fields = []
            for field_id, field_config in config_fields_dict.items():
                logger.info(f"Processing field: {field_id} with type {field_config.get('type', 'text')}")
                field_config['id'] = field_id
                config_fields.append(field_config)
            
            # Create configuration container with unique ID
            # Vérifier que instance_id est un entier avant de comparer
            container_id = f"plugin_{plugin}_{instance_id}" if isinstance(instance_id, int) and instance_id > 0 else f"plugin_{plugin}"
            container = PluginConfigContainer(
                plugin=plugin,
                name=plugin_name,
                icon=plugin_icon,
                description=plugin_description,
                config_fields=config_fields,
                id=container_id,
                classes="plugin-config"
            )
            
            return container
            
        except Exception as e:
            logger.error(f"Error loading config for plugin {plugin}: {e}")
            return PluginConfigContainer(
                plugin=plugin,
                name=f"Error: {plugin}",
                icon="⚠️",
                description=f"Error loading config: {str(e)}",
                config_fields=[],
                id=f"plugin_{plugin}_error"
            )
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "validate":
            # Collect all field values
            config = {}
            for container in self.query(PluginConfigContainer):
                plugin_config = {}
                for field_id, field in container.fields_by_id.items():
                    value = field.get_value()
                    if value not in [None, '']:  # Skip empty values
                        plugin_config[field_id] = value
                        
                if plugin_config:  # Only include plugins with non-empty config
                    config[container.plugin_id] = plugin_config
                    
            self.current_config = config
            self.app.pop_screen()

    def action_quit(self) -> None:
        """Handle escape key"""
        self.app.pop_screen()