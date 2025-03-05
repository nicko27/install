from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Label
import os
import traceback
from ruamel.yaml import YAML

from .utils import setup_logging
from .choice_management.plugin_utils import get_plugin_folder_name
from .components.plugin_config_container import PluginConfigContainer
from .components.text_field import TextField
from .components.checkbox_field import CheckboxField
from .config_manager import ConfigManager

logger = setup_logging()
yaml = YAML()

class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [
        ("esc", "quit", "Quit"),
    ]
    CSS_PATH = "styles/config.css"

    def __init__(self, plugin_instances: list, name: str | None = None) -> None:
        try:
            logger.debug("Initializing PluginConfig")
            super().__init__(name=name)

            logger.debug(f"Plugin instances: {plugin_instances}")
            self.plugin_instances = plugin_instances
            self.current_config = {}
            self.fields_by_plugin = {}
            self.fields_by_id = {}
            self.plugins_remote_enabled = {}
            self.remote_config_fields = {}
            self.ssh_container = None

            # Initialize the configuration manager
            logger.debug("Creating ConfigManager")
            self.config_manager = ConfigManager()

            # Load SSH configuration
            ssh_config_path = os.path.join(os.path.dirname(__file__), 'ssh_manager', 'ssh_fields.yml')
            logger.debug(f"Loading SSH config from: {ssh_config_path}")
            self.config_manager.load_global_config('ssh', ssh_config_path)

            # Initialize field collections
            for plugin_name, _ in plugin_instances:
                logger.debug(f"Initializing fields for plugin: {plugin_name}")
                self.fields_by_plugin[plugin_name] = {}

                # Load plugin configuration
                folder_name = get_plugin_folder_name(plugin_name)
                settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')
                logger.debug(f"Loading plugin config from: {settings_path}")
                self.config_manager.load_plugin_config(plugin_name, settings_path)

            logger.debug("PluginConfig initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing PluginConfig: {e}")
            logger.error(traceback.format_exc())
            raise

    def compose(self) -> ComposeResult:
        try:
            logger.debug("PluginConfig.compose() started")
            print("PluginConfig.compose() started")  # Pour debugging direct

            yield Header()

            # Determine if any plugins support remote execution
            remote_plugins = self.get_remote_execution_plugins()
            has_remote_plugins = len(remote_plugins) > 0
            logger.debug(f"Has remote plugins: {has_remote_plugins}")

            # Fallback label pour s'assurer que quelque chose s'affiche
            yield Label("Configuration des plugins", id="config-title", classes="section-title")

            with ScrollableContainer(id="config-container"):
                # Add plugin configurations
                for plugin_name, instance_id in self.plugin_instances:
                    logger.debug(f"Creating config for plugin: {plugin_name}_{instance_id}")
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

                # For SSH section, use a simple container and yield it directly
                if has_remote_plugins:
                    logger.debug("Adding SSH configuration section")
                    yield Container(id="ssh-config", classes="config-container disabled-container")

            with Horizontal(id="button-container"):
                yield Button("Cancel", id="cancel", variant="error")
                yield Button("Execute", id="validate", variant="primary")

            yield Footer()

            logger.debug("PluginConfig.compose() completed")
            print("PluginConfig.compose() completed")  # Pour debugging direct

        except Exception as e:
            logger.error(f"Error in PluginConfig.compose(): {e}")
            logger.error(traceback.format_exc())
            print(f"Error in PluginConfig.compose(): {e}")  # Pour debugging direct

            # En cas d'erreur, au moins retourner des widgets de base sans essayer de les monter
            yield Label("Une erreur s'est produite lors du chargement de la configuration", id="error-message")
            yield Button("Retour", id="cancel", variant="error")

    async def on_mount(self) -> None:
        """Called when screen is mounted - used to add remote execution checkboxes"""
        try:
            logger.debug("PluginConfig.on_mount() started")

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
                try:
                    remote_field = CheckboxField(plugin_name, field_id, remote_config, is_global=False)

                    # Store field for future reference
                    self.fields_by_plugin[plugin_name][field_id] = remote_field
                    self.plugins_remote_enabled[plugin_key] = remote_field

                    # Mount checkbox in the plugin container
                    await container.mount(remote_field)
                    logger.debug(f"Successfully mounted checkbox for {plugin_key}")
                except Exception as e:
                    logger.error(f"Error creating checkbox for {plugin_key}: {e}")

            logger.debug("PluginConfig.on_mount() completed")
        except Exception as e:
            logger.error(f"Error in PluginConfig.on_mount(): {e}")
            logger.error(traceback.format_exc())

    def get_remote_execution_plugins(self) -> list:
        """Return list of plugins that support remote execution"""
        try:
            remote_plugins = []

            for plugin_name, _ in self.plugin_instances:
                # Get plugin folder name
                folder_name = get_plugin_folder_name(plugin_name)
                settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')

                try:
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
        except Exception as e:
            logger.error(f"Error in get_remote_execution_plugins: {e}")
            return []

    def _create_plugin_config(self, plugin: str, instance_id: int) -> Container:
        """Create configuration container for a plugin"""
        try:
            plugin_config = self.config_manager.plugin_configs.get(plugin, {})

            if not plugin_config:
                logger.error(f"No configuration found for plugin {plugin}")
                container = Container(id=f"plugin_{plugin}_{instance_id}", classes="config-container")
                # Ne pas utiliser mount ici
                # Au lieu de cela, retourner le conteneur vide et le laisser être monté par compose
                return container

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

            # Utiliser PluginConfigContainer qui fonctionne correctement avec compose
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

        except Exception as e:
            logger.error(f"Error in _create_plugin_config for {plugin}: {e}")
            # Au lieu de monter des widgets, simplement retourner un conteneur vide
            return Container(id=f"plugin_{plugin}_{instance_id}", classes="config-container error-container")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        logger.debug(f"Button pressed: {event.button.id}")

        try:
            if event.button.id == "cancel":
                logger.debug("Cancel button pressed, popping screen")
                self.app.pop_screen()

            elif event.button.id == "validate":
                logger.debug("Validate button pressed")

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
                    logger.debug("Validation errors found, stopping")
                    return

                # Collect configurations
                self.collect_configurations()
                logger.debug(f"Collected configuration: {self.current_config}")

                # Import here to avoid circular imports
                try:
                    from .executor import ExecutionScreen

                    # Create execution screen
                    logger.debug("Creating ExecutionScreen")
                    execution_screen = ExecutionScreen(self.current_config)

                    # Replace current screen with execution screen
                    logger.debug("Switching to ExecutionScreen")
                    self.app.switch_screen(execution_screen)
                except Exception as e:
                    logger.error(f"Error switching to execution screen: {e}")
                    logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error in on_button_pressed: {e}")
            logger.error(traceback.format_exc())

    def on_checkbox_changed(self, event):
        """Handle checkbox state changes for remote execution and SSH"""
        try:
            checkbox_id = event.checkbox.id
            value = event.value

            logger.debug(f"Checkbox changed: {checkbox_id} -> {value}")

            # Check if it's a remote execution checkbox
            is_remote_checkbox = False
            for plugin_key, field in self.plugins_remote_enabled.items():
                if hasattr(field, 'source_id') and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
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
        except Exception as e:
            logger.error(f"Error in on_checkbox_changed: {e}")

    def toggle_ssh_config(self, enable: bool):
        """Enable or disable SSH configuration"""
        try:
            logger.debug(f"Toggling SSH config: enable={enable}")
            if self.ssh_container:
                if enable:
                    self.ssh_container.remove_class("disabled-container")
                else:
                    self.ssh_container.add_class("disabled-container")

                # Update SSH field states
                for field_id, field in self.fields_by_id.items():
                    # Only process fields from the SSH source
                    if hasattr(field, 'source_id') and field.source_id == 'ssh':
                        self.toggle_field_state(field, enable)
        except Exception as e:
            logger.error(f"Error in toggle_ssh_config: {e}")

    def toggle_ssh_sms(self, enable: bool):
        """Enable or disable SMS field based on SMS authentication checkbox"""
        try:
            logger.debug(f"Toggling SSH SMS field: enable={enable}")
            if "ssh_sms" in self.fields_by_id:
                sms_field = self.fields_by_id["ssh_sms"]
                self.toggle_field_state(sms_field, enable)
        except Exception as e:
            logger.error(f"Error in toggle_ssh_sms: {e}")

    def toggle_field_state(self, field, enable: bool):
        """Toggle enabled state of a field and its widgets"""
        try:
            field.disabled = not enable

            # Handle different widget types
            if hasattr(field, 'input'):
                field.input.disabled = not enable
                if enable:
                    field.input.remove_class('disabled')
                else:
                    field.input.add_class('disabled')
            elif hasattr(field, 'checkbox'):
                field.checkbox.disabled = not enable
                if enable:
                    field.checkbox.remove_class('disabled')
                else:
                    field.checkbox.add_class('disabled')
            elif hasattr(field, 'select'):
                field.select.disabled = not enable
                if enable:
                    field.select.remove_class('disabled')
                else:
                    field.select.add_class('disabled')
        except Exception as e:
            logger.error(f"Error in toggle_field_state: {e}")

    def collect_configurations(self):
        """Collect configurations from all fields"""
        try:
            logger.debug("Collecting configurations")
            self.current_config = {}

            # Get SSH config values
            ssh_config = {}
            ssh_fields = [f for f in self.fields_by_id.values() if hasattr(f, 'source_id') and f.source_id == 'ssh']

            if ssh_fields:
                logger.debug(f"Found {len(ssh_fields)} SSH fields")
                ssh_config = {
                    field.field_id: field.get_value()
                    for field in ssh_fields
                }

            # Collect plugin configurations
            for plugin_name, instance_id in self.plugin_instances:
                logger.debug(f"Collecting config for plugin: {plugin_name}_{instance_id}")
                # Determine if plugin supports remote execution
                supports_remote = False

                try:
                    # Get plugin folder name
                    folder_name = get_plugin_folder_name(plugin_name)
                    settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')

                    with open(settings_path, 'r') as f:
                        settings = yaml.load(f)
                        supports_remote = settings.get('remote_execution', False)
                except Exception as e:
                    logger.error(f"Error checking remote execution for {plugin_name}: {e}")

                # Check if remote execution is enabled for this plugin
                plugin_key = f"{plugin_name}_{instance_id}"
                remote_enabled = False
                if plugin_key in self.plugins_remote_enabled:
                    remote_enabled = self.plugins_remote_enabled[plugin_key].get_value()

                # Get plugin fields
                plugin_fields = [
                    field for field in self.fields_by_id.values()
                    if hasattr(field, 'source_id') and field.source_id == plugin_name and
                    not field.field_id.startswith(f"remote_exec_{plugin_name}")
                ]

                if plugin_fields:
                    logger.debug(f"Found {len(plugin_fields)} fields for plugin {plugin_name}")
                    # Collect field values
                    config_values = {}

                    for field in plugin_fields:
                        if hasattr(field, 'variable_name'):
                            config_values[field.variable_name] = field.get_value()

                    # Add SSH variables if plugin supports remote execution and it's enabled
                    if supports_remote and remote_enabled:
                        config_values.update(ssh_config)
                        config_values["remote_execution"] = True
                    else:
                        config_values["remote_execution"] = False

                    # Get original plugin settings
                    plugin_settings = {}
                    try:
                        folder_name = get_plugin_folder_name(plugin_name)
                        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')
                        with open(settings_path, 'r') as f:
                            plugin_settings = yaml.load(f)
                    except Exception as e:
                        logger.error(f"Error loading settings for {plugin_name}: {e}")

                    # Store complete configuration
                    self.current_config[plugin_key] = {
                        'plugin_name': plugin_name,
                        'instance_id': instance_id,
                        'name': plugin_settings.get('name', plugin_name),
                        'show_name': plugin_settings.get('plugin_name', plugin_name),
                        'icon': plugin_settings.get('icon', '📦'),
                        'config': config_values,
                        'remote_execution': supports_remote and remote_enabled
                    }

            logger.debug(f"Collected configuration: {self.current_config}")
        except Exception as e:
            logger.error(f"Error in collect_configurations: {e}")
            logger.error(traceback.format_exc())
            # Ensure we have at least an empty config
            self.current_config = {}

    def action_quit(self) -> None:
        """Handle escape key"""
        logger.debug("Quit action triggered")
        self.app.pop_screen()