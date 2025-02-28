"""Validation system with plugin support"""
from .base import ValidationRule
from .plugin_registry import ValidationPluginRegistry, register_plugin

__all__ = [
    'ValidationRule',
    'create_rule',
    'list_plugins',
    'register_plugin'
]

# Initialize plugin registry
_registry = ValidationPluginRegistry()

def create_rule(plugin_type: str, **kwargs) -> ValidationRule:
    """Create a validation rule"""
    return _registry.create_rule(plugin_type, **kwargs)

def list_plugins() -> dict[str, str]:
    """List available validation plugins"""
    return _registry.list_plugins()
