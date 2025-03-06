from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Checkbox, Label

from .config_container import ConfigContainer
from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField
from .checkbox_group_field import CheckboxGroupField
from ..utils.logging import get_logger

logger = get_logger('plugin_config_container')

class PluginConfigContainer(ConfigContainer):
    """Container for plugin configuration fields"""

    def __init__(self, plugin: str, name: str, icon: str, description: str,
                 fields_by_plugin: dict, fields_by_id: dict, config_fields: list, **kwargs):
        super().__init__(
            source_id=plugin,
            title=name,
            icon=icon,
            description=description,
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            is_global=False,
            **kwargs
        )
        # Keep reference to plugin-specific field collections
        self.fields_by_plugin = fields_by_plugin
        if plugin not in fields_by_plugin:
            fields_by_plugin[plugin] = {}
        
        # Remote execution field (will be set by PluginConfig if needed)
        self.remote_field = None

    def compose(self) -> ComposeResult:
        """Compose the container with fields and remote execution checkbox if available"""
        # Title and description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        if not self.config_fields and not self.remote_field:
            with VerticalGroup(classes="no-config"):
                with HorizontalGroup(classes="no-config-content"):
                    yield Label("ℹ️", classes="no-config-icon")
                    yield Label(f"Rien à configurer pour ce plugin", classes="no-config-label")
                return

        with VerticalGroup(classes="config-fields"):
            # Configuration fields
            for field_config in self.config_fields:
                field_id = field_config.get('id')
                if not field_id:
                    logger.warning(f"Field without id in {self.source_id}")
                    continue
                field_type = field_config.get('type', 'text')
                field_class = {
                    'text': TextField,
                    'directory': DirectoryField,
                    'ip': IPField,
                    'checkbox': CheckboxField,
                    'select': SelectField,
                    'checkbox_group': CheckboxGroupField
                }.get(field_type, TextField)

                # Create field with access to other fields and whether it's global
                field = field_class(self.source_id, field_id, field_config, self.fields_by_id, is_global=self.is_global)
                self.fields_by_id[field_id] = field

                # If it's a checkbox or checkbox_group, add an event handler
                if field_type in ['checkbox', 'checkbox_group']:
                    field.on_checkbox_changed = self.on_checkbox_changed

                yield field
            
            # If we have a remote execution field, add it at the end of the config-fields container
            if self.remote_field:
                with VerticalGroup(classes="remote-execution-container"):
                    yield self.remote_field

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes with plugin-specific field tracking"""
        # Call the parent implementation first
        super().on_checkbox_changed(event)

        # Additional plugin-specific handling
        checkbox_id = event.checkbox.id

        for field_id, field in self.fields_by_id.items():
            if hasattr(field, 'source_id') and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
                # Store in plugin-specific fields collection
                self.fields_by_plugin[self.source_id][field_id] = field
                break