"""Registry for auto-discovering field components"""
import importlib.util
import inspect
import logging
import os
from typing import Dict, Type, Optional, List
from .base_field import BaseField

from ...logging import get_logger
logger = get_logger('components')

class ComponentRegistry:
    """Registry for field components with auto-discovery"""
    
    _instance = None
    _components: Dict[str, Type[BaseField]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._discover_components()
        return cls._instance
    
    @classmethod
    def register(cls, field_type: str, component_class: Type[BaseField]) -> None:
        """Register a component class for a field type"""
        logger.info(f"Registering component {component_class.__name__} for field type '{field_type}'")
        cls._components[field_type] = component_class
        logger.info(f"Current registry: {[k for k in cls._components.keys()]}")
    
    @classmethod
    def get(cls, field_type: str) -> Optional[Type[BaseField]]:
        """Get component class for a field type"""
        component = cls._components.get(field_type)
        if component:
            logger.info(f"Found component {component.__name__} for field type '{field_type}'")
        else:
            logger.warning(f"No component found for field type '{field_type}'. Available types: {[k for k in cls._components.keys()]}")
        return component
    
    def _discover_components(self) -> None:
        """Auto-discover components in the fields directory"""
        # Get the fields directory path
        fields_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'fields')
        logger.info(f"Looking for components in: {fields_dir}")
        if not os.path.exists(fields_dir):
            logger.warning(f"Fields directory not found: {fields_dir}")
            return
        
        # Scan all Python files in the fields directory
        for filename in os.listdir(fields_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_path = os.path.join(fields_dir, filename)
                logger.info(f"Found field module: {filename}")
                try:
                    # Import the module
                    module_name = f"ui.components.fields.{filename[:-3]}"
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    if not spec or not spec.loader:
                        logger.error(f"Could not load module: {module_path}")
                        continue
                    
                    logger.info(f"Loading module: {module_name}")
                    
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find field classes in module
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BaseField) and 
                            obj != BaseField):
                            # Convert class name to field type
                            # Example: TextField -> text, IPField -> ip
                            field_type = self._class_to_field_type(name)
                            logger.info(f"Found field class: {name} -> {field_type}")
                            self.register(field_type, obj)
                            
                except Exception as e:
                    logger.error(f"Error loading field module {filename}: {e}")
    
    def _class_to_field_type(self, class_name: str) -> str:
        """Convert a class name to a field type
        Example: TextField -> text, IPField -> ip
        """
        # Remove 'Field' suffix if present
        if class_name.endswith('Field'):
            class_name = class_name[:-5]
        
        # Convert camelCase to snake_case
        field_type = ''
        for i, char in enumerate(class_name):
            if i > 0 and char.isupper() and \
               (class_name[i-1].islower() or \
               (i+1 < len(class_name) and class_name[i+1].islower())):
                field_type += '_'
            field_type += char.lower()
        
        return field_type
    
    @classmethod
    def create_field(cls, field_type: str, *args, **kwargs) -> Optional[BaseField]:
        """Create a field instance of the specified type"""
        component_class = cls.get(field_type)
        if component_class:
            return component_class(*args, **kwargs)
        logger.error(f"Unknown field type: {field_type}")
        return None
    
    @classmethod
    def discover(cls) -> None:
        """Discover all available components"""
        if cls._instance is None:
            cls._instance = cls()
        else:
            cls._instance._discover_components()

    @classmethod
    def list_components(cls) -> Dict[str, str]:
        """List all registered components"""
        return {field_type: component_class.__name__ 
                for field_type, component_class in cls._components.items()}
