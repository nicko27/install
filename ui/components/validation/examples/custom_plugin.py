"""Example of creating a custom validation plugin"""
from typing import Any, Optional
from ..base import ValidationRule

class PhoneValidation(ValidationRule):
    """Validates phone numbers"""
    
    def __init__(self, country_code: str = 'FR', message: Optional[str] = None):
        super().__init__(message)
        self.country_code = country_code
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
            
        # Remove spaces and dashes
        value = str(value).replace(' ', '').replace('-', '')
        
        # French phone number
        if self.country_code == 'FR':
            if not value.startswith('+33') and not value.startswith('0'):
                return False, self.message or "Must start with +33 or 0"
            if value.startswith('+33'):
                value = '0' + value[3:]
            if not value.startswith('0') or len(value) != 10:
                return False, self.message or "Must be 10 digits"
            return True, None
            
        # Add more country codes as needed
        return False, f"Unsupported country code: {self.country_code}"
