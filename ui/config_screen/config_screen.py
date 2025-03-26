from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical, VerticalGroup
from textual.widgets import Header, Footer, Button, Label
import os
import traceback
from ruamel.yaml import YAML
import asyncio

from ..utils.logging import get_logger
from ..choice_screen.plugin_utils import get_plugin_folder_name
from .plugin_config_container import PluginConfigContainer
from .global_config_container import GlobalConfigContainer
from .text_field import TextField
from .checkbox_field import CheckboxField
from .config_manager import ConfigManager

logger = get_logger('config_screen')
# Configuration de ruamel.yaml pour préserver les commentaires
yaml = YAML()
yaml.preserve_quotes = True

class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [
        ("esc", "quit", "Quit"),
    ]
    CSS_PATH = "../styles/config.tcss"

    def __init__(self, plugin_instances: list, name: str | None = None, sequence_file: str | None = None) -> None:
        try:
            logger.debug("Initialisation de PluginConfig")
            super().__init__(name=name)

            logger.debug(f"Instances de plugins: {plugin_instances}")
            self.plugin_instances = plugin_instances
            self.current_config = {}
            self.fields_by_plugin = {}
            self.fields_by_id = {}
            self.containers_by_id = {}  # Dictionnaire des containers par ID
            self.plugins_remote_enabled = {}
            self.ssh_container = None
            self.sequence_file = sequence_file
            self.sequence_data = None
            # Attribut pour indiquer si nous revenons de l'écran d'exécution
            self.returning_from_execution = False

            # Charger la séquence si spécifiée
            if sequence_file and os.path.exists(sequence_file):
                try:
                    yaml = YAML()
                    with open(sequence_file, 'r') as f:
                        self.sequence_data = yaml.load(f)
                    logger.info(f"Séquence chargée: {sequence_file}")
                except Exception as e:
                    logger.error(f"Erreur chargement séquence: {e}")

            # Initialiser le gestionnaire de configuration
            logger.debug("Création ConfigManager")
            self.config_manager = ConfigManager()

            # Charger la configuration SSH
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
            ssh_config_path = os.path.join(project_root, 'ui', 'ssh_manager', 'ssh_fields.yml')
            logger.debug(f"Chargement config SSH depuis: {ssh_config_path}")
            self.config_manager.load_global_config('ssh', ssh_config_path)

            # Initialiser les collections de champs
            for plugin_name, instance_id in plugin_instances:
                logger.debug(f"Initialisation champs pour plugin: {plugin_name}")
                self.fields_by_plugin[plugin_name] = {}

                # Charger la configuration du plugin
                folder_name = get_plugin_folder_name(plugin_name)
                settings_path = os.path.join(project_root, 'plugins', folder_name, 'settings.yml')
                logger.debug(f"Chargement config plugin depuis: {settings_path}")
                self.config_manager.load_plugin_config(plugin_name, settings_path)

                # Charger les valeurs prédéfinies de la séquence
                if self.sequence_data and 'plugins' in self.sequence_data:
                    for plugin_config in self.sequence_data['plugins']:
                        if (plugin_config['name'] == plugin_name and
                            'variables' in plugin_config):
                            logger.info(f"Variables prédéfinies trouvées pour {plugin_name}")
                            self.current_config[f"{plugin_name}_{instance_id}"] = plugin_config['variables'].copy()

            logger.debug("PluginConfig initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing PluginConfig: {e}")
            logger.error(traceback.format_exc())
            raise

    def compose(self) -> ComposeResult:
        try:
            logger.debug("PluginConfig.compose() started")
            
            # Import widgets at the beginning of the method
            from textual.widgets import Label, Button

            yield Header()

            # Determine if any plugins support remote execution
            remote_plugins = self.get_remote_execution_plugins()
            has_remote_plugins = len(remote_plugins) > 0
            logger.debug(f"Has remote plugins: {has_remote_plugins}")
            logger.debug(f"Remote plugins list: {remote_plugins}")

            # Titre de la configuration
            yield Label("Configuration des plugins", id="window-config-title", classes="section-title")

            with ScrollableContainer(id="config-container-list"):
                # Add plugin configurations
                for plugin_name, instance_id in self.plugin_instances:
                    logger.debug(f"Creating config for plugin: {plugin_name}_{instance_id}")
                    plugin_container = self._create_plugin_config(plugin_name, instance_id)

                    # Vérifier si le plugin_container a été créé correctement
                    if plugin_container is None:
                        logger.warning(f"Impossible de créer le conteneur pour {plugin_name}_{instance_id}, probablement une séquence")
                        continue

                    # If plugin supports remote execution, prepare the checkbox for the plugin container
                    logger.debug(f"Checking if {plugin_name} is in remote_plugins: {plugin_name in remote_plugins}")
                    if plugin_name in remote_plugins:
                        logger.debug(f"Adding remote execution checkbox for plugin {plugin_name}_{instance_id}")

                        # Create unique ID for the checkbox
                        remote_field_id = f"remote_exec_{plugin_name}_{instance_id}"
                        
                        # Create checkbox configuration
                        remote_config = {
                            "type": "checkbox",
                            "label": "⚠️  Activer l'exécution distante pour ce plugin",
                            "description": "Cochez cette case pour exécuter ce plugin via SSH sur des machines distantes",
                            "default": False,
                            "id": remote_field_id,
                            "variable": "remote_execution_enabled",
                            "required": True
                        }
                        
                        # Create the checkbox field
                        remote_field = CheckboxField(plugin_name, remote_field_id, remote_config, self.fields_by_id, is_global=False)
                        remote_field.add_class("remote-execution-checkbox")
                        
                        # Store field for future reference
                        self.fields_by_plugin[plugin_name][remote_field_id] = remote_field
                        self.plugins_remote_enabled[f"{plugin_name}_{instance_id}"] = remote_field
                        
                        # Add the remote execution checkbox to the plugin container
                        plugin_container.remote_field = remote_field
                    
                    # Render the plugin container
                    yield plugin_container

                # Add empty SSH configuration container if there are remote plugins
                # Content will be added in on_mount
                if has_remote_plugins:
                    logger.debug("Adding empty SSH container (content will be added in on_mount)")
                    self.ssh_container = Container(id="ssh-config", classes="ssh-container config-container disabled-container")
                    yield self.ssh_container
                
                # Ajouter un espace en bas pour garantir que tout le contenu est visible lors du scroll
                yield Container(classes="scroll-spacer")

            with Horizontal(id="button-container"):
                yield Button("Cancel", id="cancel", variant="error")
                yield Button("Execute", id="validate", variant="primary")

            yield Footer()

            logger.debug("PluginConfig.compose() completed")

        except Exception as e:
            logger.error(f"Error in PluginConfig.compose(): {e}")
            logger.error(traceback.format_exc())

            # En cas d'erreur, au moins retourner des widgets de base sans essayer de les monter
            yield Label("Une erreur s'est produite lors du chargement de la configuration", id="error-message")
            yield Button("Retour", id="cancel", variant="error")

    async def on_mount(self) -> None:
        """Called when screen is mounted - used to add remote execution checkboxes and SSH fields"""
        try:
            # Create containers and plugins input
            self.call_after_refresh(self.create_config_fields)
            
            # Si nous revenons de l'écran d'exécution, restaurer les valeurs des champs
            if self.returning_from_execution and self.current_config:
                logger.debug(f"Restauration de la configuration préservée: {self.current_config}")
                
                # Appeler la méthode de restauration après un court délai pour s'assurer que tous les widgets sont montés
                await asyncio.sleep(0.1)  # court délai pour laisser le DOM se stabiliser
                self.call_after_refresh(self.restore_saved_configuration)
                
            logger.debug("PluginConfig.on_mount() completed")
        except Exception as e:
            logger.error(f"Error in PluginConfig.on_mount(): {e}")
            logger.error(traceback.format_exc())

    def restore_saved_configuration(self):
        """Restaure la configuration sauvegardée lors du retour de l'écran d'exécution"""
        try:
            if not self.current_config:
                logger.debug("Pas de configuration à restaurer")
                return
                
            logger.debug(f"Début de la restauration de la configuration: {len(self.current_config)} plugins")
            
            # Parcourir tous les plugins dans la configuration
            for plugin_id, plugin_config in self.current_config.items():
                logger.debug(f"Restauration de la configuration pour {plugin_id}")
                
                # Extraire le nom du plugin et la configuration
                plugin_name = plugin_id.split('_')[0]
                config = plugin_config.get('config', {})
                
                # Parcourir tous les paramètres de la configuration du plugin
                for param_name, value in config.items():
                    field_id = f"{plugin_name}.{param_name}"
                    
                    # Vérifier si ce champ existe dans notre dictionnaire de champs
                    if field_id in self.fields_by_id:
                        field = self.fields_by_id[field_id]
                        logger.debug(f"Restauration du champ {field_id} avec la valeur {value}")
                        
                        # Mettre à jour la valeur du champ
                        if hasattr(field, 'set_value'):
                            field.set_value(value)
                        elif hasattr(field, 'value'):
                            field.value = value
                            
                            # Si le champ est un widget avec une valeur, mettre à jour également
                            try:
                                for widget_type in [Input, Select, Checkbox]:
                                    try:
                                        widget = field.query_one(widget_type)
                                        if hasattr(widget, 'value'):
                                            widget.value = value
                                            logger.debug(f"Valeur du widget mise à jour pour {field_id}")
                                        break
                                    except Exception:
                                        continue
                            except Exception as e:
                                logger.debug(f"Erreur lors de la mise à jour du widget pour {field_id}: {e}")
                
                # Restaurer également l'état d'activation des plugins distants
                if 'remote_execution' in plugin_config and plugin_name in self.plugins_remote_enabled:
                    ssh_enabled = plugin_config.get('remote_execution', False)
                    logger.debug(f"Restauration de l'état SSH pour {plugin_name}: {ssh_enabled}")
                    
                    # Mettre à jour la case à cocher
                    checkbox_id = f"{plugin_name}_remote"
                    try:
                        checkbox = self.query_one(f"#{checkbox_id}", CheckboxField)
                        if checkbox:
                            checkbox.value = ssh_enabled
                            
                            # Activer/désactiver les champs SSH en fonction de l'état
                            if ssh_enabled:
                                self.toggle_ssh_config(True)
                    except Exception as e:
                        logger.error(f"Erreur lors de la restauration de l'état SSH pour {plugin_name}: {e}")
            
            # Mettre à jour les dépendances entre champs après restauration
            self.update_all_dependencies()
            
            logger.debug("Restauration de la configuration terminée")
        except Exception as e:
            logger.error(f"Erreur lors de la restauration de la configuration: {e}")
            logger.error(traceback.format_exc())
            
    def update_all_dependencies(self):
        """Met à jour toutes les dépendances entre champs"""
        try:
            logger.debug("Mise à jour de toutes les dépendances entre champs")
            
            # Parcourir tous les champs
            for field_id, field in self.fields_by_id.items():
                # Mettre à jour les champs qui dépendent de ce champ
                if hasattr(field, 'value'):
                    # Trouver le container parent du champ
                    container = None
                    for container_id, c in self.containers_by_id.items():
                        if field_id in c.fields_by_id:
                            container = c
                            break
                    
                    # Si le container est trouvé, mettre à jour les dépendances
                    if container and hasattr(container, 'update_dependent_fields'):
                        container.update_dependent_fields(field)
                        logger.debug(f"Mise à jour des dépendances pour {field_id}")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des dépendances: {e}")

    def get_remote_execution_plugins(self) -> list:
        """Return list of plugins that support remote execution"""
        try:
            remote_plugins = []
            logger.debug(f"Plugin instances to check for remote execution: {self.plugin_instances}")

            for plugin_name, _ in self.plugin_instances:
                # Get plugin folder name
                folder_name = get_plugin_folder_name(plugin_name)
                # Utiliser un chemin absolu pour accéder aux fichiers de configuration des plugins
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
                settings_path = os.path.join(project_root, 'plugins', folder_name, 'settings.yml')

                try:
                    logger.debug(f"Reading settings from: {settings_path}")
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        from io import StringIO
                        settings = yaml.load(StringIO(file_content))
                        logger.debug(f"Loaded settings: {settings}")
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
            # Vérifier si c'est une séquence
            if plugin.startswith('__sequence__'):
                logger.warning(f"Skipping configuration for sequence: {plugin}")
                return None
                
            plugin_config = self.config_manager.plugin_configs.get(plugin, {})

            if not plugin_config:
                logger.error(f"No configuration found for plugin {plugin}")
                container = Container(id=f"plugin_{plugin}_{instance_id}", classes="config-container")
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
                field_config_copy = field_config.copy()  # Create a copy to avoid modifying original
                field_config_copy['id'] = field_id
                config_fields.append(field_config_copy)

            # Utiliser PluginConfigContainer avec la classe config-container
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
            logger.error(traceback.format_exc())
            # Au lieu de monter des widgets, simplement retourner None
            return None

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
                    from ..execution_screen.execution_screen import ExecutionScreen

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
                    self.ssh_container.remove_class("disabled-ssh-container")
                else:
                    self.ssh_container.add_class("disabled-ssh-container")

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
            # Check if the field has an enabled_if condition
            if hasattr(field, 'enabled_if') and field.enabled_if:
                # Get the dependency field
                dep_field_id = field.enabled_if['field']
                dep_field = self.fields_by_id.get(dep_field_id)
                
                if dep_field:
                    # Check if the dependency field's value matches the required value
                    dep_value = dep_field.get_value()
                    required_value = field.enabled_if['value']
                    
                    logger.debug(f"Field {field.field_id} has enabled_if condition: {field.enabled_if}")
                    logger.debug(f"Dependency field {dep_field_id} value: {dep_value}, required: {required_value}")
                    
                    # If the dependency condition is not met, force disable regardless of enable parameter
                    if dep_value != required_value:
                        logger.debug(f"Field {field.field_id} disabled due to enabled_if condition")
                        enable = False
            
            # Set the disabled state on the field itself
            field.disabled = not enable
            
            # Handle different widget types
            if hasattr(field, 'input'):
                field.input.disabled = not enable
                if enable:
                    field.input.remove_class('disabled')
                    
                    # If we're enabling a field, restore its value
                    if hasattr(field, 'field_config'):
                        # Case 1: Field has a dynamic default
                        if 'dynamic_default' in field.field_config and hasattr(field, '_get_dynamic_default'):
                            logger.debug(f"Restoring dynamic default value for field {field.field_id}")
                            dynamic_value = field._get_dynamic_default()
                            if dynamic_value:
                                field.value = dynamic_value
                                field.input.value = str(dynamic_value)
                                logger.debug(f"Restored dynamic value: {dynamic_value}")
                        # Case 2: Field has a static default
                        elif 'default' in field.field_config and field.field_config['default'] is not None:
                            default_value = field.field_config['default']
                            logger.debug(f"Restoring static default value for field {field.field_id}: {default_value}")
                            field.value = default_value
                            field.input.value = str(default_value)
                            logger.debug(f"Restored static default value: {default_value}")
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
                    
                    # If we're enabling a field, restore its value
                    if hasattr(field, 'field_config'):
                        # Case 1: Field has a dynamic default
                        if 'dynamic_default' in field.field_config and hasattr(field, '_get_dynamic_default'):
                            logger.debug(f"Restoring dynamic default value for field {field.field_id}")
                            dynamic_value = field._get_dynamic_default()
                            if dynamic_value:
                                field.value = dynamic_value
                                field.select.value = str(dynamic_value)
                                logger.debug(f"Restored dynamic value: {dynamic_value}")
                        # Case 2: Field has a static default
                        elif 'default' in field.field_config and field.field_config['default'] is not None:
                            default_value = field.field_config['default']
                            logger.debug(f"Restoring static default value for field {field.field_id}: {default_value}")
                            field.value = default_value
                            field.select.value = str(default_value)
                            logger.debug(f"Restored static default value: {default_value}")
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
                    settings_path = os.path.join(os.path.dirname(__file__), '..', '..','plugins', folder_name, 'settings.yml')

                    with open(settings_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        from io import StringIO
                        settings = yaml.load(StringIO(file_content))
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
                
                # Always process the plugin, even if it has no fields
                # This ensures all plugins appear in the execution window
                logger.debug(f"Found {len(plugin_fields)} fields for plugin {plugin_name}")
                # Collect field values
                config_values = {}
                
                # Get original plugin settings - moved outside the field loop to ensure it's always defined
                plugin_settings = {}
                try:
                    folder_name = get_plugin_folder_name(plugin_name)
                    settings_path = os.path.join(os.path.dirname(__file__), '..','..', 'plugins', folder_name, 'settings.yml')
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        from io import StringIO
                        plugin_settings = yaml.load(StringIO(file_content))
                except Exception as e:
                    logger.error(f"Error loading settings for {plugin_name}: {e}")
                
                for field in plugin_fields:
                    if hasattr(field, 'variable_name'):
                        value = field.get_value()
                        # Gérer spécifiquement les valeurs des champs checkbox_group
                        if hasattr(field, 'field_config') and field.field_config.get('type') == 'checkbox_group':
                            # Si aucune valeur n'est sélectionnée, utiliser une liste vide
                            if not value:
                                value = []
                            # S'assurer que la valeur est une liste
                            elif not isinstance(value, list):
                                value = [value]
                        config_values[field.variable_name] = value

                # Add SSH variables if plugin supports remote execution and it's enabled
                if supports_remote and remote_enabled:
                    config_values.update(ssh_config)
                    config_values["remote_execution"] = True
                else:
                    config_values["remote_execution"] = False

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
                logger.debug(f"Added plugin {plugin_key} to configuration")

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

    def create_config_fields(self):
        """Crée les champs de configuration après le montage de l'interface"""
        try:
            logger.debug("Création des champs de configuration")
            
            # Réinitialiser le dictionnaire des containers
            self.containers_by_id = {}
            
            # Récupérer tous les containers de configuration
            config_containers = self.query(".config-container")
            logger.debug(f"Nombre de containers trouvés: {len(config_containers)}")
            
            # Indexer les containers par ID
            for container in config_containers:
                if hasattr(container, 'id'):
                    self.containers_by_id[container.id] = container
                    logger.debug(f"Container ajouté: {container.id}")
                    
                    # Si le container est un ConfigContainer, ajouter ses champs à fields_by_id
                    if hasattr(container, 'fields_by_id'):
                        for field_id, field in container.fields_by_id.items():
                            self.fields_by_id[field_id] = field
                            logger.debug(f"Champ ajouté: {field_id}")
            
            logger.debug(f"Nombre total de containers indexés: {len(self.containers_by_id)}")
            logger.debug(f"Nombre total de champs indexés: {len(self.fields_by_id)}")
        except Exception as e:
            logger.error(f"Erreur lors de la création des champs de configuration: {e}")
            logger.error(traceback.format_exc())