from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, ScrollableContainer, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Label
import os
from ruamel.yaml import YAML

from .utils import setup_logging
from .choice import get_plugin_folder_name
from .components.plugin_config_container import PluginConfigContainer
from .components.text_field import TextField
from .components.checkbox_field import CheckboxField
# Si vous avez créé le fichier password_field.py, importez-le ici
# from .components.password_field import PasswordField
# Sinon, nous utiliserons TextField pour les mots de passe temporairement

# Import du nouveau gestionnaire SSH
from .ssh_manager.ssh_manager import SSHManager

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
        self.global_fields = {}  # Pour stocker les champs globaux
        self.plugins_remote_enabled = {}  # Pour stocker les plugins ayant l'exécution distante activée
        self.remote_config_fields = {}  # Pour stocker les champs de config distante
        self.ssh_container = None  # Pour stocker le conteneur SSH
        self.ssh_manager = SSHManager()  # Initialisation du gestionnaire SSH
        
        # Initialiser le dictionnaire pour les plugins
        for plugin_name, _ in plugin_instances:
            self.fields_by_plugin[plugin_name] = {}

    def compose(self) -> ComposeResult:
        yield Header()
    
        # Vérifier si des plugins supportent l'exécution distante
        remote_plugins = self.get_remote_execution_plugins()
        has_remote_plugins = len(remote_plugins) > 0
        logger.debug(f"Has remote plugins: {has_remote_plugins}")
        
        with ScrollableContainer(id="config-container"):
            # Ajouter les configurations de chaque plugin
            for plugin_name, instance_id in self.plugin_instances:
                # Créer un conteneur de configuration pour le plugin
                plugin_container = self._create_plugin_config(plugin_name, instance_id)
                
                # Si le plugin supporte l'exécution distante, on prépare son checkbox
                # mais on ne l'ajoute pas maintenant pour éviter l'erreur de montage
                if plugin_name in remote_plugins:
                    logger.debug(f"Preparing remote execution checkbox for plugin {plugin_name}_{instance_id}")
                    
                    # Créer un ID unique pour le checkbox
                    remote_field_id = f"remote_exec_{plugin_name}_{instance_id}"
                    
                    # Stocker l'ID et la référence au plugin pour traitement ultérieur
                    self.remote_config_fields[f"{plugin_name}_{instance_id}"] = {
                        "field_id": remote_field_id,
                        "plugin_name": plugin_name,
                        "instance_id": instance_id,
                        "container": plugin_container
                    }
                
                # Rendre le conteneur du plugin
                yield plugin_container
                
            # Si des plugins supportent l'exécution distante, ajouter la section SSH en bas
            if has_remote_plugins:
                logger.debug("Adding SSH configuration section at the bottom")
                # Créer le conteneur pour les paramètres SSH
                with Container(id="ssh-config", classes="plugin-config disabled-container") as ssh_container:
                    self.ssh_container = ssh_container
                    # En-tête de la section
                    with Vertical(classes="plugin-header"):
                        yield Label(f"{self.ssh_manager.get_ssh_icon()} {self.ssh_manager.get_ssh_name()}", classes="plugin-title")
                        yield Label(self.ssh_manager.get_ssh_hint(), classes="ssh-hint")
                    
                    # Créer et ajouter les champs SSH directement ici
                    ssh_fields = self.ssh_manager.get_ssh_fields()
                    fields_by_id = {}  # Pour les dépendances entre champs
                    
                    for field_id, field_config in ssh_fields.items():
                        field_type = field_config.get("type", "text")
                        
                        if field_type == "checkbox":
                            field = CheckboxField("global", field_id, field_config, fields_by_id)
                        # Si on a implémenté PasswordField et que le type est password
                        # elif field_type == "password" and "PasswordField" in globals():
                        #     field = PasswordField("global", field_id, field_config, fields_by_id)
                        else:
                            field = TextField("global", field_id, field_config, fields_by_id)
                        
                        # Désactiver initialement tous les champs SSH
                        field.disabled = True
                        
                        # Enregistrer le champ pour un usage futur
                        self.global_fields[field_id] = field
                        fields_by_id[field_id] = field
                        
                        yield field
        
        with Horizontal(id="button-container"):
            yield Button("Cancel", id="cancel", variant="error")
            yield Button("Execute", id="validate", variant="primary")
            
        yield Footer()

        
    async def on_mount(self) -> None:
        """Appelé lorsque l'écran est monté - utilisé pour ajouter les checkboxes d'exécution distante"""
        # Maintenant que l'interface est montée, nous pouvons ajouter les checkboxes
        # d'exécution distante aux plugins qui le supportent
        for plugin_key, config in self.remote_config_fields.items():
            plugin_name = config["plugin_name"]
            instance_id = config["instance_id"]
            field_id = config["field_id"]
            container = config["container"]
            
            logger.debug(f"Adding remote execution checkbox for {plugin_key}")
            
            # Créer le checkbox
            remote_config = {
                "type": "checkbox",
                "label": "Activer l'exécution distante pour ce plugin",
                "default": False,
                "id": field_id
            }
            
            remote_field = CheckboxField(plugin_name, field_id, remote_config)
            
            # Stocker le champ pour référence future
            self.fields_by_plugin[plugin_name][field_id] = remote_field
            self.plugins_remote_enabled[plugin_key] = remote_field
            
            # Monter le checkbox dans le conteneur du plugin maintenant qu'il est attaché
            await container.mount(remote_field)

    def get_remote_execution_plugins(self) -> list:
        """Renvoie la liste des plugins qui supportent l'exécution distante"""
        remote_plugins = []
        
        logger.debug("Checking for remote execution plugins")
        
        for plugin_name, _ in self.plugin_instances:
            # Récupérer le nom du dossier du plugin
            folder_name = get_plugin_folder_name(plugin_name)
            logger.debug(f"Checking plugin {plugin_name} with folder {folder_name}")
            
            # Construire le chemin vers le fichier settings.yml
            settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', folder_name, 'settings.yml')
            logger.debug(f"Settings path: {settings_path}")
            
            if not os.path.exists(settings_path):
                logger.error(f"Settings file not found: {settings_path}")
                continue
                
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
            
            # Vérifier les champs globaux SSH s'ils sont présents
            has_remote_enabled = False
            for plugin_key, field in self.plugins_remote_enabled.items():
                if field.get_value():
                    has_remote_enabled = True
                    break
            
            if has_remote_enabled and self.global_fields:
                for field_id, field in self.global_fields.items():
                    if isinstance(field, TextField):
                        # Vérifier si le champ est actif (non désactivé par une dépendance)
                        if not field.disabled:
                            value = field.input.value
                            is_valid, error_msg = field.validate_input(value)
                            if not is_valid:
                                field.input.add_class('error')
                                field.input.tooltip = error_msg
                                has_errors = True
                                logger.error(f"Validation error in global field {field_id}: {error_msg}")
            
            # Vérifier les champs des plugins
            for plugin_name, instance_id in self.plugin_instances:
                plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
                for field in plugin_fields:
                    if isinstance(field, TextField):
                        # Vérifier si le champ est actif (non désactivé par une dépendance)
                        if not field.disabled:
                            value = field.input.value
                            is_valid, error_msg = field.validate_input(value)
                            if not is_valid:
                                field.input.add_class('error')
                                field.input.tooltip = error_msg
                                has_errors = True
                                logger.error(f"Validation error in {field.field_id}: {error_msg}")
            
            if has_errors:
                return
            
            # Collecter les configurations
            self.collect_configurations()
            
            # Import here to avoid circular imports
            from .execution import ExecutionScreen
            
            # Create execution screen
            execution_screen = ExecutionScreen(self.current_config)
            
            # Replace current screen with execution screen
            self.app.switch_screen(execution_screen)

    def on_checkbox_changed(self, event):
        """Gère les changements d'état des checkboxes d'exécution distante et SSH"""
        checkbox_id = event.checkbox.id
        value = event.value

        logger.debug(f"Checkbox changed: {checkbox_id} -> {value}")

        # Vérifier s'il s'agit d'un checkbox d'exécution distante
        is_remote_checkbox = False
        for plugin_key, field in self.plugins_remote_enabled.items():
            if checkbox_id == f"checkbox_{field.plugin_path}_{field.field_id}":
                is_remote_checkbox = True
                break

        if is_remote_checkbox:
            # Vérifier si au moins un plugin a l'exécution distante activée
            has_remote_enabled = False
            for _, field in self.plugins_remote_enabled.items():
                if field.get_value():
                    has_remote_enabled = True
                    break
            
            # Activation/désactivation des champs SSH
            self.toggle_ssh_config(has_remote_enabled)
        # Vérifier si c'est le checkbox d'authentification par SMS
        elif checkbox_id == f"checkbox_global_ssh_sms_enabled":
            self.toggle_ssh_sms(value)

    def toggle_ssh_config(self, enable: bool):
        """Active ou désactive la configuration SSH"""
        if self.ssh_container:
            if enable:
                self.ssh_container.remove_class("disabled-container")
            else:
                self.ssh_container.add_class("disabled-container")

            # Mettre à jour l'état des champs SSH
            for field_id, field in self.global_fields.items():
                # Ne pas modifier l'état du champ SMS s'il dépend du checkbox d'authentification SMS
                if field_id == "ssh_sms" and "ssh_sms_enabled" in self.global_fields:
                    if not enable:
                        # Si on désactive tout, on désactive aussi le champ SMS
                        field.disabled = True
                        if hasattr(field, 'input'):
                            field.input.disabled = True
                            field.input.add_class('disabled')
                    else:
                        # Si on active tout, on vérifie l'état du checkbox d'authentification SMS
                        sms_enabled = self.global_fields["ssh_sms_enabled"].get_value()
                        field.disabled = not sms_enabled
                        if hasattr(field, 'input'):
                            field.input.disabled = not sms_enabled
                            if sms_enabled:
                                field.input.remove_class('disabled')
                            else:
                                field.input.add_class('disabled')
                else:
                    # Pour les autres champs, on les active/désactive selon le paramètre
                    field.disabled = not enable
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

    def toggle_ssh_sms(self, enable: bool):
        """Active ou désactive le champ SMS en fonction de l'authentification par SMS"""
        if "ssh_sms" in self.global_fields:
            sms_field = self.global_fields["ssh_sms"]
            sms_field.disabled = not enable
            if hasattr(sms_field, 'input'):
                sms_field.input.disabled = not enable
                if enable:
                    sms_field.input.remove_class('disabled')
                else:
                    sms_field.input.add_class('disabled')

    def collect_configurations(self):
        """Collecte toutes les configurations, y compris les variables SSH globales"""
        self.current_config = {}
        
        # Récupérer les valeurs des champs SSH globaux
        ssh_config = {}
        if self.global_fields:
            ssh_config = {
                "ssh_ips": self.global_fields.get("ssh_ips").get_value(),
                "ssh_user": self.global_fields.get("ssh_user").get_value(),
                "ssh_passwd": self.global_fields.get("ssh_passwd").get_value(),
                "ssh_sms_enabled": self.global_fields.get("ssh_sms_enabled").get_value(),
            }
            
            if ssh_config["ssh_sms_enabled"]:
                ssh_config["ssh_sms"] = self.global_fields.get("ssh_sms").get_value()
        
        # Collecter les configurations de chaque plugin
        for plugin_name, instance_id in self.plugin_instances:
            # Déterminer si le plugin supporte l'exécution distante
            supports_remote = False
            remote_enabled = False
            
            # Vérifier si le plugin a l'option remote_execution
            folder_name = get_plugin_folder_name(plugin_name)
            settings_path = os.path.join('plugins', folder_name, 'settings.yml')
            
            yaml = YAML()
            settings = {}
            
            try:
                with open(settings_path, 'r') as f:
                    settings = yaml.load(f)
                    supports_remote = settings.get('remote_execution', False)
            except Exception as e:
                logger.error(f"Error reading {settings_path}: {e}")
                supports_remote = False
            
            # Vérifier si l'exécution distante est activée pour ce plugin
            plugin_key = f"{plugin_name}_{instance_id}"
            if plugin_key in self.plugins_remote_enabled:
                remote_enabled = self.plugins_remote_enabled[plugin_key].get_value()
            
            # Récupérer les valeurs des champs du plugin
            plugin_fields = self.query(f"#plugin_{plugin_name}_{instance_id} ConfigField")
            
            if plugin_fields:
                config_values = {
                    field.variable_name: field.get_value()
                    for field in plugin_fields
                    if not field.field_id.startswith(f"remote_exec_{plugin_name}")  # Exclure la checkbox de config remote
                }
                
                # Ajouter les variables SSH si le plugin est compatible et si l'exécution distante est activée
                if supports_remote and remote_enabled:
                    config_values.update(ssh_config)
                    config_values["remote_execution"] = True
                else:
                    config_values["remote_execution"] = False
                
                # Stocker la configuration complète
                self.current_config[plugin_key] = {
                    'plugin_name': plugin_name,
                    'instance_id': instance_id,
                    'name': settings.get('name', plugin_name),
                    'show_name': settings.get('plugin_name', plugin_name),
                    'icon': settings.get('icon', '📦'),
                    'config': config_values,
                    'remote_execution': supports_remote and remote_enabled
                }
        
        # Afficher la configuration pour débogage
        logger.debug(f"Collected configuration: {self.current_config}")
            
    def action_quit(self) -> None:
        """Handle escape key"""
        self.app.pop_screen()