"""File validation"""
import os
from typing import Any, Optional, List
from ..base import ValidationRule

class FileExistsValidation(ValidationRule):
    """Validates that a file exists"""
    
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
            
        if not os.path.exists(str(value)):
            return False, self.message or "File does not exist"
            
        return True, None

class FileExtensionValidation(ValidationRule):
    """Validates file extension"""
    
    def __init__(self, extensions: List[str], message: Optional[str] = None):
        super().__init__(message)
        self.extensions = [ext.lower().strip('.') for ext in extensions]
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
            
        ext = os.path.splitext(str(value))[1].lower().strip('.')
        if ext not in self.extensions:
            return False, self.message or f"File must have one of these extensions: {', '.join(self.extensions)}"
            
        return True, None
