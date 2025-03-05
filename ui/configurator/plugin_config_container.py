from .config_container import ConfigContainer
from textual.widgets import Checkbox
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