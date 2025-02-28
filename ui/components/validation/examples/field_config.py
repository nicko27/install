"""Example of field configuration with validation"""
from typing import Dict, Any

def get_registration_form() -> Dict[str, Any]:
    """Example registration form configuration"""
    return {
        'username': {
            'type': 'text',
            'required': True,
            'min_length': 3,
            'max_length': 20,
            'pattern': r'^[a-zA-Z0-9_]+$',
            'messages': {
                'required': 'Username is required',
                'length': 'Username must be between 3 and 20 characters',
                'pattern': 'Username can only contain letters, numbers and underscores'
            }
        },
        'email': {
            'type': 'text',
            'required': True,
            'validation': [
                {
                    'type': 'email',
                    'message': 'Invalid email address'
                }
            ]
        },
        'password': {
            'type': 'password',
            'required': True,
            'min_length': 8,
            'validation': [
                {
                    'type': 'pattern',
                    'pattern': r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$',
                    'message': 'Password must contain at least one letter and one number'
                }
            ]
        },
        'confirm_password': {
            'type': 'password',
            'required': True,
            'validation': [
                {
                    'type': 'cross_field',
                    'other_field': 'password',
                    'compare_func': 'equals',
                    'message': 'Passwords must match'
                }
            ]
        },
        'birth_date': {
            'type': 'date',
            'required': True,
            'validation': [
                {
                    'type': 'date_range',
                    'max_date': '2007-01-01',  # Must be at least 18 years old
                    'message': 'You must be at least 18 years old'
                }
            ]
        },
        'phone': {
            'type': 'text',
            'validation': [
                {
                    'type': 'phone',
                    'country_code': 'FR',
                    'message': 'Invalid phone number'
                }
            ]
        }
    }
