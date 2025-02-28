"""Text length validation"""
from typing import Any, Optional
from ..base import ValidationRule

class LengthValidation(ValidationRule):
    """Validates text length"""
    
    def __init__(self, min_length: Optional[int] = None, 
                 max_length: Optional[int] = None, 
                 message: Optional[str] = None):
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
