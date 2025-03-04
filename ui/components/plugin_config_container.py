from textual.app import ComposeResult
from textual.containers import VerticalGroup, HorizontalGroup
from textual.widgets import Label, Input, Select, Button, Checkbox
from textual.reactive import reactive
from textual.widget import Widget

from ..utils import setup_logging
from .text_field import TextField
from .directory_field import DirectoryField
from .ip_field import IPField
from .checkbox_field import CheckboxField
from .select_field import SelectField

logger = setup_logging()

class PluginConfigContainer(VerticalGroup):
    """Container for plugin configuration fields"""
    # Define reactive attributes
    plugin_id = reactive("")  # Plugin identifier
    plugin_title = reactive("")   # Plugin name/title
    plugin_icon = reactive("")    # Plugin icon
    plugin_description = reactive("")  # Plugin description

    def __init__(self, plugin: str, name: str, icon: str, description: str, fields_by_plugin: dict, fields_by_id: dict, config_fields: list, **kwargs):
        super().__init__(**kwargs)
        # Set the reactive attributes
        self.plugin_id = plugin
        self.plugin_title = name
        self.plugin_icon = icon
        self.plugin_description = description
        # Non-reactive attributes
        self.fields_by_plugin = fields_by_plugin
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields

    def compose(self) -> ComposeResult:
        # Title and description
        with VerticalGroup(classes="plugin-header"):
            yield Label(f"{self.plugin_icon} {self.plugin_title}", classes="plugin-title")

        if not self.config_fields:
            with HorizontalGroup(classes="no-config-container"):
                yield Label("ℹ️", classes="no-config-icon")
                yield Label(f"Rien à configurer pour {self.plugin_title}", classes="no-config")
            return

        # Configuration fields
        for field_config in self.config_fields:
            field_id = field_config.get('id')
            if not field_id:
                logger.warning(f"Field without id in plugin {self.plugin_id}")
                continue
            field_type = field_config.get('type', 'text')
            field_class = {
                'text': TextField,
                'directory': DirectoryField,
                'ip': IPField,
                'checkbox': CheckboxField,
                'select': SelectField
            }.get(field_type, TextField)

            # Create field with access to other fields
            field = field_class(self.plugin_id, field_id, field_config, self.fields_by_id)
            self.fields_by_plugin[self.plugin_id][field_id] = field
            self.fields_by_id[field_id] = field

            # If it's a checkbox, add an event handler
            if field_type == 'checkbox':
                field.on_checkbox_changed = self.on_checkbox_changed

            yield field

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes"""
        # Find the field that emitted the event
        checkbox_id = event.checkbox.id
        logger.debug(f"Checkbox changed: {checkbox_id} -> {event.value}")

        for field in self.fields_by_plugin[self.plugin_id].values():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.plugin_path}_{field.field_id}":
                logger.debug(f"Found matching checkbox field: {field.field_id}")
                field.value = event.value

                # Update dependent fields
                for dependent_field in self.fields_by_id.values():
                    if dependent_field.enabled_if and dependent_field.enabled_if['field'] == field.field_id:
                        logger.debug(f"Found dependent field: {dependent_field.field_id} with enabled_if={dependent_field.enabled_if}")

                        # Handle any widget type that can be disabled
                        for widget_type in [Input, Select, Button]:
                            try:
                                widget = dependent_field.query_one(widget_type)
                                logger.debug(f"Found widget of type {widget_type.__name__} for field {dependent_field.field_id}")
                            except Exception:
                                continue

                            # If we got here, we found the widget
                            should_disable = field.value != dependent_field.enabled_if['value']
                            logger.debug(f"Field {dependent_field.field_id}: should_disable={should_disable} (checkbox value={field.value}, enabled_if value={dependent_field.enabled_if['value']})")

                            # Always remove existing classes first
                            dependent_field.remove_class('disabled')
                            dependent_field.disabled = False
                            widget.remove_class('disabled')
                            widget.disabled = False

                            if should_disable:
                                logger.debug(f"Disabling widget for field {dependent_field.field_id}")
                                dependent_field.add_class('disabled')
                                dependent_field.disabled = True
                                widget.add_class('disabled')
                                widget.disabled = True
                                # Clear IP fields when disabled to prevent invalid config
                                if isinstance(widget, Input) and isinstance(dependent_field, IPField):
                                    widget.value = ''
                            else:
                                logger.debug(f"Enabling widget for field {dependent_field.field_id}")
                break