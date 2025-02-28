"""Number validation rules"""
from typing import Any, Optional, Union
from ..base import ValidationRule

class IntegerValidation(ValidationRule):
    """Validates that a value is an integer"""
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            int(value)
            return True, None
        except (ValueError, TypeError):
            return False, self.message or "Must be an integer"

class FloatValidation(ValidationRule):
    """Validates that a value is a float"""
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            float(value)
            return True, None
        except (ValueError, TypeError):
            return False, self.message or "Must be a number"

class RangeValidation(ValidationRule):
    """Validates that a number is within a range"""
    
    def __init__(self, min_value: Optional[float] = None, 
                 max_value: Optional[float] = None, message: Optional[str] = None):
        super().__init__(message)
        self.min_value = min_value
        self.max_value = max_value
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            num_value = float(value)
            if self.min_value is not None and num_value < self.min_value:
                return False, self.message or f"Must be greater than {self.min_value}"
            if self.max_value is not None and num_value > self.max_value:
                return False, self.message or f"Must be less than {self.max_value}"
            return True, None
        except (ValueError, TypeError):
            return False, "Invalid number format"
