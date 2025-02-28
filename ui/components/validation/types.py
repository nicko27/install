"""Common validation types and utilities"""
import re
from typing import Any, Callable, Dict, Optional, Pattern, Union
from datetime import datetime
from email_validator import validate_email, EmailNotValidError

class ValidationRule:
    """Base class for validation rules"""
    def __init__(self, message: Optional[str] = None):
        self.message = message
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        raise NotImplementedError

class Required(ValidationRule):
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, self.message or "This field is required"
        return True, None

class IsInteger(ValidationRule):
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            int(value)
            return True, None
        except (ValueError, TypeError):
            return False, self.message or "Must be an integer"

class IsFloat(ValidationRule):
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            float(value)
            return True, None
        except (ValueError, TypeError):
            return False, self.message or "Must be a number"

class IsEmail(ValidationRule):
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            validate_email(value)
            return True, None
        except EmailNotValidError:
            return False, self.message or "Invalid email address"

class Pattern(ValidationRule):
    def __init__(self, pattern: Union[str, Pattern], message: Optional[str] = None):
        super().__init__(message)
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        if not self.pattern.match(str(value)):
            return False, self.message or "Invalid format"
        return True, None

class Range(ValidationRule):
    def __init__(self, min_value: Optional[float] = None, max_value: Optional[float] = None, 
                 message: Optional[str] = None):
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

class Length(ValidationRule):
    def __init__(self, min_length: Optional[int] = None, max_length: Optional[int] = None,
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

class DateRange(ValidationRule):
    def __init__(self, min_date: Optional[str] = None, max_date: Optional[str] = None,
                 format: str = "%Y-%m-%d", message: Optional[str] = None):
        super().__init__(message)
        self.min_date = datetime.strptime(min_date, format) if min_date else None
        self.max_date = datetime.strptime(max_date, format) if max_date else None
        self.format = format
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if not value:
            return True, None
        try:
            date_value = datetime.strptime(value, self.format)
            if self.min_date and date_value < self.min_date:
                return False, self.message or f"Date must be after {self.min_date.strftime(self.format)}"
            if self.max_date and date_value > self.max_date:
                return False, self.message or f"Date must be before {self.max_date.strftime(self.format)}"
            return True, None
        except ValueError:
            return False, f"Invalid date format (use {self.format})"

class CrossFieldValidation(ValidationRule):
    def __init__(self, other_field: str, compare_func: Callable[[Any, Any], bool], 
                 message: Optional[str] = None):
        super().__init__(message)
        self.other_field = other_field
        self.compare_func = compare_func
        
    def __call__(self, value: Any, fields_by_id: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if not value or self.other_field not in fields_by_id:
            return True, None
        other_value = fields_by_id[self.other_field].get_value()
        if not self.compare_func(value, other_value):
            return False, self.message or f"Invalid value compared to {self.other_field}"
        return True, None

# Validation functions for cross-field validation
def greater_than(a: Any, b: Any) -> bool:
    try:
        return float(a) > float(b)
    except (ValueError, TypeError):
        return False

def after_date(a: Any, b: Any, format: str = "%Y-%m-%d") -> bool:
    try:
        date_a = datetime.strptime(a, format)
        date_b = datetime.strptime(b, format)
        return date_a > date_b
    except ValueError:
        return False
