from textual.widgets import Input
from .text_field import TextField
from ..utils.logging import get_logger

logger = get_logger('ip_field')

class IPField(TextField):
    """IP address input field with validation"""
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == f"input_{self.field_id}":
            # Only validate if the field is enabled
            if not event.input.disabled:
                # Ensure value is a string before stripping
                value = str(event.value).strip() if event.value is not None else ""
                
                if value:
                    # Basic IP address validation
                    try:
                        octets = [int(x) for x in value.split('.')]
                        if len(octets) == 4 and all(0 <= x <= 255 for x in octets):
                            self.value = value  # Ensure this is a string
                            event.input.remove_class('error')
                        else:
                            event.input.add_class('error')
                    except (ValueError, AttributeError):
                        event.input.add_class('error')
                else:
                    # Empty value is allowed if field is not required
                    self.value = value  # Ensure this is a string
                    event.input.remove_class('error')
                    
    def get_value(self) -> str:
        """Override to ensure we properly handle tuple values"""
        if isinstance(self.value, tuple) and len(self.value) == 2:
            success, value = self.value
            if success:
                return str(value)
            return ""
        return super().get_value()
