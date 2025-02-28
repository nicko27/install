"""Validation system exceptions"""
from typing import Optional, Any

class ValidationError(Exception):
    """Base validation error"""
    def __init__(self, message: str, field_id: Optional[str] = None):
        super().__init__(message)
        self.field_id = field_id

class PluginNotFoundError(ValidationError):
    """Raised when a validation plugin is not found"""
    def __init__(self, plugin_type: str):
        super().__init__(f"Validation plugin not found: {plugin_type}")
        self.plugin_type = plugin_type

class PluginLoadError(ValidationError):
    """Raised when a validation plugin fails to load"""
    def __init__(self, plugin_file: str, original_error: Exception):
        super().__init__(f"Failed to load validation plugin {plugin_file}: {original_error}")
        self.plugin_file = plugin_file
        self.original_error = original_error

class ValidationConfigError(ValidationError):
    """Raised when validation configuration is invalid"""
    def __init__(self, message: str, config: Any):
        super().__init__(message)
        self.config = config

class CrossFieldError(ValidationError):
    """Raised when cross-field validation fails"""
    def __init__(self, field_id: str, other_field_id: str, message: str):
        super().__init__(message, field_id)
        self.other_field_id = other_field_id
