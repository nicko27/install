from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Label, Header, Footer, Button, Input, Checkbox, Select
from textual.reactive import reactive
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
        self.value = field_config.get('default', None)
        self.disabled = False

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
        yield self.input
        
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            self.value = event.value

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

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        self.checkbox = Checkbox(value=bool(self.value), id=f"checkbox_{self.field_id}")
        yield self.checkbox
    
    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self.value = event.value

class SelectField(ConfigField):
    """Select field with options"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        
        options = self.field_config.get('options', [])
        if isinstance(options, dict):
            options = [(k, v) for k, v in options.items()]
        elif isinstance(options, list):
            options = [(str(i), str(i)) for i in options]
            
        # S'assurer qu'il y a au moins une option
        if not options:
            options = [("default", "default")]
            
        # Si la valeur est None, utiliser la première option
        if self.value is None and options:
            self.value = options[0][1]
            
        self.select = Select(
            options=options,
            value=str(self.value),
            id=f"select_{self.field_id}"
        )
        yield self.select
    
    def on_select_changed(self, event: Select.Changed) -> None:
        self.value = event.value

class PluginConfigContainer(Vertical):
    """Container for plugin configuration"""
    def __init__(self, plugin_id: str, title: str, icon_str: str, desc: str, config_fields: list):
        super().__init__(id=f"plugin_{plugin_id}")
        self.plugin_id = plugin_id
        self.plugin_title = title
        self.plugin_icon = icon_str
        self.plugin_desc = desc
        self.config_fields = config_fields
        self.fields_by_id = {}

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
                    'select': SelectField
                }.get(field_type, TextField)
                
                field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
                self.fields_by_id[field_id] = field
                yield field

    def get_config(self) -> dict:
        """Get the configuration values"""
        return {field_id: field.value for field_id, field in self.fields_by_id.items()}

class PluginConfig(Screen):
    """Plugin configuration screen"""
    BINDINGS = [("esc", "quit", "Quitter")]
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles/config.css")

    def __init__(self, plugins: list, name: str | None = None):
        super().__init__(name=name)
        self.plugins = plugins
        self.containers = {}
        self._instance_counts = {}

    def compose(self) -> ComposeResult:
        """Compose the configuration screen"""
        yield Header()
        
        with ScrollableContainer(id="config-container"):
            # Réinitialiser les compteurs d'instances
            self._instance_counts = {}
            
            for plugin in self.plugins:
                container = self._create_plugin_config(plugin)
                if container:
                    self.containers[plugin] = container
                    yield container
        
        with Container(id="button-container"):
            yield Button("Valider", id="validate", variant="primary")
            yield Button("Annuler", id="cancel", variant="error")
        
        yield Footer()

    def _create_plugin_config(self, plugin: str) -> PluginConfigContainer | None:
        """Create a plugin configuration container"""
        settings_path = os.path.join(os.path.dirname(__file__), '..', 'plugins', plugin, 'settings.yml')
        
        # Incrémenter le compteur d'instances pour ce plugin
        if plugin not in self._instance_counts:
            self._instance_counts[plugin] = 0
        self._instance_counts[plugin] += 1
        instance_num = self._instance_counts[plugin]
        
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

        return PluginConfigContainer(
            plugin_id=f"{plugin}_{instance_num}",
            title=settings.get('name', plugin),
            icon_str=settings.get('icon', '📦'),
            desc=settings.get('description', ''),
            config_fields=config_fields
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "validate":
            self.action_validate()
        elif event.button.id == "cancel":
            self.action_quit()

    def action_validate(self) -> None:
        """Save configuration and close"""
        config = {plugin: container.get_config() 
                 for plugin, container in self.containers.items()}
        self.app.save_config(config)
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Close without saving"""
        self.app.pop_screen()
