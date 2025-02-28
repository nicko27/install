"""Utility functions for validation"""
from typing import Any, Dict, List, Optional, Union
from .base import ValidationRule
from . import registry
from .config import get_default_config, get_default_message
from .exceptions import ValidationConfigError

def create_validation_rules(field_config: Dict[str, Any]) -> List[ValidationRule]:
    """Create validation rules from field configuration"""
    rules = []
    # registry is imported from __init__.py
    
    # Get default config based on field type
    field_type = field_config.get('type', 'text')
    default_config = get_default_config(field_type)
    
    # Merge with provided config
    config = {**default_config, **field_config}
    
    # Required validation
    if config.get('required', False):
        message = config.get('messages', {}).get('required')
        rules.append(registry.create_rule('required', message=message))
    
    # Length validation
    if 'min_length' in config or 'max_length' in config:
        message = config.get('messages', {}).get('length')
        rules.append(registry.create_rule('length',
            min_length=config.get('min_length'),
            max_length=config.get('max_length'),
            message=message
        ))
    
    # Pattern validation
    if 'pattern' in config:
        message = config.get('messages', {}).get('pattern')
        rules.append(registry.create_rule('pattern',
            pattern=config['pattern'],
            message=message
        ))
    
    # Custom validation rules
    if 'validation' in config:
        for validation in config['validation']:
            if isinstance(validation, dict):
                rule_type = validation.get('type')
                if rule_type:
                    # Get message from validation config or default messages
                    message = validation.get('message')
                    if not message:
                        message = config.get('messages', {}).get(rule_type)
                    
                    # Create validation rule
                    kwargs = {k: v for k, v in validation.items() if k not in ('type', 'message')}
                    rule = registry.create_rule(rule_type, message=message, **kwargs)
                    if rule:
                        rules.append(rule)
                    
    return rules

def validate_field(value: Any, rules: List[ValidationRule], 
                  fields_by_id: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[str]]:
    """Validate a value against a list of rules"""
    for rule in rules:
        # Handle cross-field validation
        if hasattr(rule, 'other_field') and fields_by_id:
            success, message = rule(value, fields_by_id)
        else:
            success, message = rule(value)
            
        if not success:
            return False, message
    return True, None

def validate_form(form_data: Dict[str, Any], 
                 form_config: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Validate all fields in a form"""
    errors = {}
    
    # Create validation rules for each field
    field_rules = {
        field_id: create_validation_rules(field_config)
        for field_id, field_config in form_config.items()
    }
    
    # Validate each field
    for field_id, value in form_data.items():
        if field_id in field_rules:
            success, message = validate_field(
                value, 
                field_rules[field_id],
                fields_by_id=form_data
            )
            if not success:
                errors[field_id] = message
                
    return errors

def merge_validation_config(base_config: Dict[str, Any], 
                          override_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge validation configurations"""
    config = base_config.copy()
    
    # Merge simple values
    for key, value in override_config.items():
        if key not in ('messages', 'validation'):
            config[key] = value
            
    # Merge messages
    if 'messages' in override_config:
        config['messages'] = {
            **config.get('messages', {}),
            **override_config['messages']
        }
        
    # Merge validation rules
    if 'validation' in override_config:
        base_validation = config.get('validation', [])
        override_validation = override_config['validation']
        
        # Remove overridden rules
        override_types = {v['type'] for v in override_validation 
                         if isinstance(v, dict) and 'type' in v}
        base_validation = [v for v in base_validation
                         if not isinstance(v, dict) or
                         v.get('type') not in override_types]
        
        config['validation'] = base_validation + override_validation
        
    return config
