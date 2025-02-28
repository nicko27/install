"""Base classes for validation system"""
from typing import Any, Optional, Dict, List, Tuple

class ValidationRule:
    """Base class for validation rules"""
    
    def __init__(self, message: Optional[str] = None, **kwargs):
        self.message = message
        self.kwargs = kwargs
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        raise NotImplementedError
        
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'ValidationRule':
        """Create validation rule from config"""
        message = config.get('message')
        kwargs = {k: v for k, v in config.items() if k != 'message'}
        return cls(message=message, **kwargs)
        
    def to_config(self) -> Dict[str, Any]:
        """Convert validation rule to config"""
        config = {'message': self.message}
        config.update(self.kwargs)
        return config
