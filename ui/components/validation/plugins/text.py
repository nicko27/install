"""Text validation rules"""
import re
from typing import Any, Optional, Union, Pattern
from ..base import ValidationRule

class PatternValidation(ValidationRule):
    """Validates that text matches a pattern"""
    
    def __init__(self, pattern: Union[str, Pattern], message: Optional[str] = None):
        super().__init__(message)
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        if not self.pattern.match(str(value)):
            return False, self.message or "Invalid format"
        return True, None

class LengthValidation(ValidationRule):
    """Validates text length"""
    
    def __init__(self, min_length: Optional[int] = None, 
                 max_length: Optional[int] = None, message: Optional[str] = None):
        super().__init__(message)
        self.min_length = min_length
        self.max_length = max_length
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        length = len(str(value))
        if self.min_length is not None and length < self.min_length:
            return False, self.message or f"Must be at least {self.min_length} characters"
        if self.max_length is not None and length > self.max_length:
            return False, self.message or f"Must be at most {self.max_length} characters"
        return True, None

class EmailValidation(ValidationRule):
    """Validates email addresses using a simple regex pattern"""
    
    EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        if not self.EMAIL_PATTERN.match(str(value)):
            return False, self.message or "Invalid email address"
        return True, None
