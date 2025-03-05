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

class ConfigContainer(VerticalGroup):
    """Base container for configuration fields (both plugins and global configs)"""
    # Define reactive attributes
    source_id = reactive("")       # Source identifier (plugin ID or global config ID)
    title = reactive("")           # Display name/title
    icon = reactive("")            # Display icon
    description = reactive("")     # Description
    is_global = reactive(False)    # Whether this is a global configuration

    def __init__(self, source_id: str, title: str, icon: str, description: str,
                 fields_by_id: dict, config_fields: list, is_global: bool = False, **kwargs):
        if "classes" in kwargs:
            if "config-container" not in kwargs["classes"]:
                kwargs["classes"] += " config-container"
        else:
            kwargs["classes"] = "config-container"

        super().__init__(**kwargs)
        # Set the reactive attributes
        self.source_id = source_id
        self.title = title
        self.icon = icon
        self.description = description
        self.is_global = is_global
        # Non-reactive attributes
        self.fields_by_id = fields_by_id
        self.config_fields = config_fields


    def compose(self) -> ComposeResult:
        # Title and description
        with VerticalGroup(classes="config-header"):
            yield Label(f"{self.icon} {self.title}", classes="config-title")
            if self.description:
                yield Label(self.description, classes="config-description")

        if not self.config_fields:
            with HorizontalGroup(classes="no-config-container"):
                yield Label("ℹ️", classes="no-config-icon")
                yield Label(f"Rien à configurer pour {self.title}", classes="no-config")
            return

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
                'select': SelectField
            }.get(field_type, TextField)

            # Create field with access to other fields and whether it's global
            field = field_class(self.source_id, field_id, field_config, self.fields_by_id, is_global=self.is_global)
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

        # Parse field ID from checkbox ID
        for field_id, field in self.fields_by_id.items():
            if isinstance(field, CheckboxField) and checkbox_id == f"checkbox_{field.source_id}_{field.field_id}":
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