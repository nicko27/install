"""Validation plugins package"""
from .required import RequiredValidation
from .number import IntegerValidation, FloatValidation, RangeValidation
from .date import DateFormatValidation
from .ip import IPAddressValidation
from .length import LengthValidation
from .file import FileExistsValidation, FileExtensionValidation
from .selection import MultipleSelectionValidation
from .text import PatternValidation, EmailValidation
from .cross_field import CrossFieldValidation, greater_than, after_date

# Register validation plugins
from .. import registry

# Basic validation
registry.register('required', RequiredValidation)

# Number validation
registry.register('integer', IntegerValidation)
registry.register('float', FloatValidation)
registry.register('number', FloatValidation)  # Alias for float
registry.register('range', RangeValidation)

# Text validation
registry.register('length', LengthValidation)
registry.register('pattern', PatternValidation)
registry.register('email', EmailValidation)

# Special types
registry.register('date', DateFormatValidation)
registry.register('ip', IPAddressValidation)
registry.register('file_exists', FileExistsValidation)
registry.register('file_extension', FileExtensionValidation)
registry.register('multiple_selection', MultipleSelectionValidation)

# Cross-field validation
registry.register('cross_field', CrossFieldValidation)
