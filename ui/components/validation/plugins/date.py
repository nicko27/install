"""Date validation rules"""
from datetime import datetime
from typing import Any, Optional
from ..base import ValidationRule

class DateFormatValidation(ValidationRule):
    """Validates date format"""
    
    def __init__(self, format: str = "%Y-%m-%d", message: Optional[str] = None):
        super().__init__(message)
        self.format = format
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            datetime.strptime(str(value), self.format)
            return True, None
        except ValueError:
            return False, self.message or f"Invalid date format (use {self.format})"

class DateRangeValidation(ValidationRule):
    """Validates date range"""
    
    def __init__(self, min_date: Optional[str] = None, max_date: Optional[str] = None,
                 format: str = "%Y-%m-%d", message: Optional[str] = None):
        super().__init__(message)
        self.format = format
        self.min_date = datetime.strptime(min_date, format) if min_date else None
        self.max_date = datetime.strptime(max_date, format) if max_date else None
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            date_value = datetime.strptime(str(value), self.format)
            if self.min_date and date_value < self.min_date:
                return False, self.message or f"Date must be after {self.min_date.strftime(self.format)}"
            if self.max_date and date_value > self.max_date:
                return False, self.message or f"Date must be before {self.max_date.strftime(self.format)}"
            return True, None
        except ValueError:
            return False, f"Invalid date format (use {self.format})"
