"""Default configuration for validation plugins"""
from typing import Dict, Any

# Default messages for validation rules
DEFAULT_MESSAGES = {
    'required': 'This field is required',
    'integer': 'Must be an integer',
    'float': 'Must be a number',
    'range': 'Value must be between {min_value} and {max_value}',
    'length': 'Length must be between {min_length} and {max_length} characters',
    'pattern': 'Invalid format',
    'email': 'Invalid email address',
    'date_format': 'Invalid date format (use {format})',
    'date_range': 'Date must be between {min_date} and {max_date}',
    'cross_field': 'Invalid value compared to {other_field}'
}

# Default patterns for common validations
DEFAULT_PATTERNS = {
    'username': r'^[a-zA-Z0-9_]+$',
    'password': r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$',
    'email': r'^[^@]+@[^@]+\.[^@]+$',
    'phone': {
        'FR': r'^\+33\d{9}$|^0\d{9}$',
        'US': r'^\+1\d{10}$|^\d{10}$'
    }
}

# Default configuration for field types
DEFAULT_CONFIG: Dict[str, Dict[str, Any]] = {
    'text': {
        'min_length': 0,
        'max_length': 255
    },
    'password': {
        'min_length': 8,
        'pattern': DEFAULT_PATTERNS['password']
    },
    'email': {
        'pattern': DEFAULT_PATTERNS['email'],
        'validation': [{'type': 'email'}]
    },
    'number': {
        'validation': [{'type': 'float'}]
    },
    'integer': {
        'validation': [{'type': 'integer'}]
    },
    'date': {
        'format': '%Y-%m-%d',
        'validation': [{'type': 'date_format'}]
    }
}

def get_default_message(rule_type: str, **kwargs) -> str:
    """Get default message for a validation rule with formatted parameters"""
    message = DEFAULT_MESSAGES.get(rule_type, 'Validation failed')
    return message.format(**kwargs) if kwargs else message

def get_default_config(field_type: str) -> Dict[str, Any]:
    """Get default configuration for a field type"""
    return DEFAULT_CONFIG.get(field_type, {})
