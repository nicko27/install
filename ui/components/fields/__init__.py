"""Field components for plugin configuration

This module provides all the field components for building configuration UIs.
Each component is automatically discovered and registered with the ComponentRegistry.

Example:
    from ui.components.fields import TextField, NumberField
    
    text_field = TextField(field_id='name', field_config={
        'required': True,
        'min_length': 3,
        'messages': {'required': 'Name is required'}
    })
"""

from .text_field import TextField
from .number_field import NumberField
from .date_field import DateField
from .select_field import SelectField
from .checkbox_field import CheckboxField
from .checkbox_group_field import CheckboxGroupField
from .radio_group_field import RadioGroupField
from .file_field import FileField
from .directory_field import DirectoryField
from .ip_field import IPField
from .password_field import PasswordField
from .textarea_field import TextAreaField

__all__ = [
    'TextField',
    'NumberField', 
    'DateField',
    'SelectField',
    'CheckboxField',
    'CheckboxGroupField',
    'RadioGroupField',
    'FileField',
    'DirectoryField',
    'IPField',
    'PasswordField',
    'TextAreaField'
]
