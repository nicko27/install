"""Cross-field validation rules"""
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from ..base import ValidationRule

class CrossFieldValidation(ValidationRule):
    """Validates a field against another field"""
    
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

def greater_than(a: Any, b: Any) -> bool:
    """Compare if a > b"""
    try:
        return float(a) > float(b)
    except (ValueError, TypeError):
        return False

def after_date(a: Any, b: Any, format: str = "%Y-%m-%d") -> bool:
    """Compare if date a is after date b"""
    try:
        date_a = datetime.strptime(a, format)
        date_b = datetime.strptime(b, format)
        return date_a > date_b
    except ValueError:
        return False
