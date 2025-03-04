from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Label
import os
from ruamel.yaml import YAML
from .utils import setup_logging
from .choice import get_plugin_folder_name
from .components.plugin_config_container import PluginConfigContainer
from .components.global_config_container import GlobalConfigContainer
from .components.text_field import TextField
from .components.checkbox_field import CheckboxField
from .config_manager import ConfigManager

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
        self.fields_by_id = {}  # All fields by ID regardless of source
        self.plugins_remote_enabled = {}  # Plugins with remote execution enabled
        self.remote_config_fields = {}  # Remote configuration fields
        self.ssh_container = None

        # Initialize the configuration manager
        self.config_manager = ConfigManager()

        # Load SSH configuration
        ssh_config_path = os.path.join(os.path.dirname(__file__), 'ssh_manager', 'ssh_fields.yml')
        self.config_manager.load_global_config('ssh', ssh_config_path)

        # Initialize field collections
        for plugin_name, _ in plugin_instances:
            self.fields_by_plugin[plugin_name] = {}

            # Load plugin configuration
            folder_name = get_plugin_folder_name(plugin_name)
            settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')
            self.config_manager.load_plugin_config(plugin_name, settings_path)

    def compose(self) -> ComposeResult:
        yield Header()

        # Determine if any plugins support remote execution
        remote_plugins = self.get_remote_execution_plugins()
        has_remote_plugins = len(remote_plugins) > 0
        logger.debug(f"Has remote plugins: {has_remote_plugins}")

        with ScrollableContainer(id="config-container"):
            # Add plugin configurations
            for plugin_name, instance_id in self.plugin_instances:
                plugin_container = self._create_plugin_config(plugin_name, instance_id)

                # If plugin supports remote execution, prepare its checkbox
                if plugin_name in remote_plugins:
                    logger.debug(f"Preparing remote execution checkbox for plugin {plugin_name}_{instance_id}")

                    # Create unique ID for the checkbox
                    remote_field_id = f"remote_exec_{plugin_name}_{instance_id}"

                    # Store ID and plugin reference for later processing
                    self.remote_config_fields[f"{plugin_name}_{instance_id}"] = {
                        "field_id": remote_field_id,
                        "plugin_name": plugin_name,
                        "instance_id": instance_id,
                        "container": plugin_container
                    }

                # Render the plugin container
                yield plugin_container

            # If any plugins support remote execution, add SSH section at the bottom
            if has_remote_plugins:
                logger.debug("Adding SSH configuration section")

                # Get SSH configuration
                ssh_config = self.config_manager.global_configs.get('ssh', {})
                ssh_fields = self.config_manager.get_fields('ssh', is_global=True)

                # Convert fields dictionary to list format for the container
                ssh_field_list = []
                for field_id, field_config in ssh_fields.items():
                    field_config['id'] = field_id
                    ssh_field_list.append(field_config)

                # Create and store SSH container
                with GlobalConfigContainer(
                    config_id='ssh',
                    name=ssh_config.get('name', 'Configuration SSH'),
                    icon=ssh_config.get('icon', '🔒'),
                    description=ssh_config.get('hint', ''),
                    fields_by_id=self.fields_by_id,
                    config_fields=ssh_field_list,
                    id="ssh-config",
                    classes="config-container disabled-container"
                ) as ssh_container:
                    self.ssh_container = ssh_container
                    yield ssh_container

        with Horizontal(id="button-container"):
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Execute", id="validate", variant="primary")

        yield Footer()


    async def on_mount(self) -> None:
        """Called when screen is mounted - used to add remote execution checkboxes"""
        # Now that the interface is mounted, we can add remote execution checkboxes
        for plugin_key, config in self.remote_config_fields.items():
            plugin_name = config["plugin_name"]
            instance_id = config["instance_id"]
            field_id = config["field_id"]
            container = config["container"]

            logger.debug(f"Adding remote execution checkbox for {plugin_key}")

            # Create checkbox configuration
            remote_config = {
                "type": "checkbox",
                "label": "Activer l'exécution distante pour ce plugin",
                "default": False,
                "id": field_id
            }

            # Create checkbox field
            remote_field = CheckboxField(plugin_name, field_id, remote_config, is_global=False)

            # Store field for future reference
            self.fields_by_plugin[plugin_name][field_id] = remote_field
            self.plugins_remote_enabled[plugin_key] = remote_field

            # Mount checkbox in the plugin container
            await container.mount(remote_field)

    def get_remote_execution_plugins(self) -> list:
        """Return list of plugins that support remote execution"""
        remote_plugins = []

        for plugin_name, _ in self.plugin_instances:
            # Get plugin folder name
            folder_name = get_plugin_folder_name(plugin_name)
            settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')

            try:
                yaml = YAML()
                with open(settings_path, 'r') as f:
                    settings = yaml.load(f)
                    remote_exec = settings.get('remote_execution', False)
                    logger.debug(f"Plugin {plugin_name} remote_execution: {remote_exec}")
                    if remote_exec:
                        logger.debug(f"Found remote execution plugin: {plugin_name}")
                        remote_plugins.append(plugin_name)
            except Exception as e:
                logger.error(f"Error reading {settings_path}: {e}")

        logger.debug(f"Remote execution plugins: {remote_plugins}")
        return remote_plugins

    def _create_plugin_config(self, plugin: str, instance_id: int) -> Container:
        """Create configuration container for a plugin"""
        plugin_config = self.config_manager.plugin_configs.get(plugin, {})

        if not plugin_config:
            logger.error(f"No configuration found for plugin {plugin}")
            return Container()

        # Store fields for later lookup
        self.fields_by_plugin[plugin] = {}
        fields_by_id = self.fields_by_id  # Reference to global fields collection

        name = plugin_config.get('name', plugin)
        icon = plugin_config.get('icon', '📦')
        description = plugin_config.get('description', '')

        # Get field configurations
        config_fields = []
        for field_id, field_config in plugin_config.get('config_fields', {}).items():
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
            classes="config-container"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "validate":
            # Check all fields
            has_errors = False

            # Check global SSH fields if present
            has_remote_enabled = False
            for plugin_key, field in self.plugins_remote_enabled.items():
                if field.get_value():
                    has_remote_enabled = True
                    break

            # Validate fields
            for field_id, field in self.fields_by_id.items():
                if isinstance(field, TextField) and not field.disabled:
                    value = field.input.value
                    is_valid, error_msg = field.validate_input(value)
                    if not is_valid:
                        field.input.add_class('error')
                        field.input.tooltip = error_msg
                        has_errors = True
                        logger.error(f"Validation error in field {field_id}: {error_msg}")

            if has_errors:
                return

            # Collect configurations
            self.collect_configurations()

            # Import here to avoid circular imports
            from .executor import ExecutionScreen

            # Create execution screen
            execution_screen = ExecutionScreen(self.current_config)

            # Replace current screen with execution screen
            self.app.switch_screen(execution_screen)

    def on_checkbox_changed(self, event):
        """Handle checkbox state changes for remote execution and SSH"""
        checkbox_id = event.checkbox.id
        value = event.value

        logger.debug(f"Checkbox changed: {checkbox_id} -> {value}")

        # Check if it's a remote execution checkbox
        is_remote_checkbox = False
        for plugin_key, field in self.plugins_remote_enabled.items():
            if checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                is_remote_checkbox = True
                break

        if is_remote_checkbox:
            # Check if at least one plugin has remote execution enabled
            has_remote_enabled = False
            for _, field in self.plugins_remote_enabled.items():
                if field.get_value():
                    has_remote_enabled = True
                    break

            # Enable/disable SSH config
            self.toggle_ssh_config(has_remote_enabled)
        # Check if it's the SMS authentication checkbox
        elif checkbox_id == f"checkbox_ssh_ssh_sms_enabled":
            self.toggle_ssh_sms(value)

    def toggle_ssh_config(self, enable: bool):
        """Enable or disable SSH configuration"""
        if self.ssh_container:
            if enable:
                self.ssh_container.remove_class("disabled-container")
            else:
                self.ssh_container.add_class("disabled-container")

            # Update SSH field states
            for field_id, field in self.fields_by_id.items():
                # Only process fields from the SSH source
                if hasattr(field, 'source_id') and field.source_id != 'ssh':
                    continue