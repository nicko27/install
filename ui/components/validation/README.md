# Validation System

The validation system provides a flexible, plugin-based approach to field validation in the UI components.

## Usage

```python
from ui.components.validation import create_rule

# Create a validation rule
rule = create_rule('required', message="This field is required")

# Validate a value
success, message = rule(value)
```

## Available Plugins

- `required`: Validates that a field is not empty
- `integer`: Validates that a value is an integer
- `float`: Validates that a value is a float
- `range`: Validates that a number is within a range
- `length`: Validates text length
- `pattern`: Validates that text matches a pattern
- `email`: Validates email addresses
- `date_format`: Validates date format
- `date_range`: Validates date range
- `cross_field`: Validates a field against another field

## Creating a Plugin

1. Create a new file in `plugins/` directory
2. Define a class that inherits from `ValidationRule`
3. Implement the `__call__` method

Example:

```python
from ..base import ValidationRule

class CustomValidation(ValidationRule):
    def __init__(self, custom_param: str, message: Optional[str] = None):
        super().__init__(message)
        self.custom_param = custom_param
        
    def __call__(self, value: Any) -> tuple[bool, Optional[str]]:
        if some_condition:
            return True, None
        return False, self.message or "Validation failed"
```

The plugin will be automatically discovered and registered with a name derived from the class name (e.g., `CustomValidation` -> `custom`).

## Field Configuration

Validation rules can be specified in the field configuration:

```python
field_config = {
    'required': True,
    'min_length': 3,
    'max_length': 50,
    'pattern': r'^[a-z]+$',
    'validation': [
        {
            'type': 'email',
            'message': 'Invalid email'
        },
        {
            'type': 'pattern',
            'pattern': r'^[^@]+@[^@]+\.[^@]+$',
            'message': 'Invalid email format'
        }
    ]
}
```

## Cross-Field Validation

For validation that depends on other fields:

```python
field_config = {
    'validation': [
        {
            'type': 'cross_field',
            'other_field': 'password',
            'compare_func': 'equals',
            'message': 'Passwords must match'
        }
    ]
}
```

## Error Messages

Each validation rule can have a custom error message:

```python
rule = create_rule('required', message="Please fill in this field")
```

Default messages are provided but can be overridden in the field configuration:

```python
field_config = {
    'required': True,
    'messages': {
        'required': 'This field cannot be empty',
        'length': 'Text must be between {min} and {max} characters',
        'pattern': 'Invalid format'
    }
}
```
