from textual.app import ComposeResult
from textual.widgets import Checkbox
from textual.containers import VerticalGroup, HorizontalGroup
from .config_field import ConfigField

from ..utils.logging import get_logger

logger = get_logger('checkbox_field')

class CheckboxField(ConfigField):
    """Checkbox field"""
    def compose(self) -> ComposeResult:
        yield from super().compose()

        # Ajouter un conteneur pour le checkbox
        with VerticalGroup(classes="checkbox-container"):
            self.checkbox = Checkbox(
                id=f"checkbox_{self.source_id}_{self.field_id}",
                value=self.value or False,
                classes="field-checkbox"
            )
            yield self.checkbox

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == f"checkbox_{self.source_id}_{self.field_id}":
            self.value = event.value
