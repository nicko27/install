from textual.app import ComposeResult
from textual.widgets import Checkbox

from .config_field import ConfigField

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()
        self.checkbox = Checkbox(
            id=f"checkbox_{self.plugin_path}_{self.field_id}",
            value=self.value or False
        )
        yield self.checkbox

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == f"checkbox_{self.plugin_path}_{self.field_id}":
            self.value = event.value
