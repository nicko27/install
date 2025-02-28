"""IP address validation"""
import re
from typing import Any, Optional
from ..base import ValidationRule
from .. import register_plugin

class IPAddressValidation(ValidationRule):
    """Validates IP address format"""
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
            
        # Basic IPv4 pattern
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, str(value)):
            return False, self.message or "Invalid IP address format"
            
        # Validate each number is between 0 and 255
        try:
            parts = [int(part) for part in str(value).split('.')]
            if all(0 <= part <= 255 for part in parts):
                return True, None
        except (ValueError, TypeError):
            pass
            
        return False, self.message or "IP address numbers must be between 0 and 255"

# Register the plugin
register_plugin('ip', IPAddressValidation)
