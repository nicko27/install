"""Selection validation"""
from typing import Any, Optional, List
from ..base import ValidationRule

class MultipleSelectionValidation(ValidationRule):
    """Validates multiple selection count"""
    
    def __init__(self, min_selected: Optional[int] = None, 
                 max_selected: Optional[int] = None,
                 message: Optional[str] = None):
        super().__init__(message)
        self.min_selected = min_selected
        self.max_selected = max_selected
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            selected_count = 0
        else:
            selected_count = len(str(value).split(','))
            
        if self.min_selected is not None and selected_count < self.min_selected:
            return False, self.message or f"Please select at least {self.min_selected} options"
            
        if self.max_selected is not None and selected_count > self.max_selected:
            return False, self.message or f"Please select at most {self.max_selected} options"
            
        return True, None
