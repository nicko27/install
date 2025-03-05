from textual.app import ComposeResult
from textual.widgets import Button
from textual.containers import VerticalGroup
from subprocess import Popen, PIPE

from .text_field import TextField
from ..utils.logging import get_logger

logger = get_logger('directory_field')

class DirectoryField(TextField):
    """Directory selection field"""
    def compose(self) -> ComposeResult:
        # Appeler super().compose() sans yield pour obtenir les widgets générés
        parent_widgets = list(super().compose())
        for widget in parent_widgets:
            yield widget

        # Ajouter le bouton Browse directement à la suite
        yield Button("Browse...", id=f"browse_{self.field_id}", classes="browse-button")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press"""
        if event.button.id == f"browse_{self.field_id}":
            from subprocess import Popen, PIPE
            process = Popen(['zenity', '--file-selection', '--directory'], stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                selected_dir = stdout.decode().strip()
                self.input.value = selected_dir
                self.value = selected_dir