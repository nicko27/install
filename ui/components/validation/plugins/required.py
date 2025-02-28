"""Required field validation"""
from typing import Any, Optional
from ..base import ValidationRule

class RequiredValidation(ValidationRule):
    """Validates that a field is not empty"""
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, self.message or "This field is required"
        return True, None
