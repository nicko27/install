"""Components for plugin configuration UI

This package provides a modular system for building configuration UIs with:
- Field components with built-in validation
- Dependency management between fields
- Plugin system for custom validation and transformation
- Debug tools and notifications

Example:
    from ui.components import ComponentRegistry
    from ui.components.fields import TextField, NumberField
    from ui.components.validation import Required, Range
    
    registry = ComponentRegistry()
    registry.register_field('text', TextField)
    registry.register_field('number', NumberField)
"""

from .base import ComponentRegistry, BaseField
from .fields import (
    TextField, NumberField, DateField, SelectField,
    CheckboxField, CheckboxGroupField, RadioGroupField, FileField,
    DirectoryField, IPField, PasswordField, TextAreaField
)
from .validation import (
    ValidationRule, create_rule
)
from .utils import (
    ValidationNotification, FieldError,
    DependencyManager, DependencyRule,
    DebugManager, DebugView
)
from .plugins import Plugin, ValidationPlugin, TransformPlugin, PluginManager

__version__ = '1.0.0'

__all__ = [
    # Base
    'ComponentRegistry',
    'BaseField',
    
    # Fields
    'TextField',
    'NumberField',
    'DateField',
    'SelectField',
    'CheckboxField',
    'RadioGroupField',
    'FileField',
    'DirectoryField',
    'IPField',
    'PasswordField',
    'TextAreaField',
    
    # Validation
    'ValidationRule',
    'create_rule',
    
    # Utils
    'ValidationNotification',
    'FieldError',
    'DependencyManager',
    'DependencyRule',
    'DebugManager',
    'DebugView',
    
    # Plugins
    'Plugin',
    'ValidationPlugin',
    'TransformPlugin',
    'PluginManager'
]
