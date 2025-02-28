"""Plugin system for field validation and customization"""
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass
import importlib.util
import os
import logging
from ..validation.base import ValidationRule

from ...logging import get_logger
logger = get_logger('plugins')

@dataclass
class Plugin:
    """Base class for field plugins"""
    name: str
    description: str
    version: str
    author: str

class ValidationPlugin(Plugin):
    """Plugin for custom field validation"""
    def __init__(self, name: str, description: str, version: str, author: str,
                 validation_func: Callable[[Any], tuple[bool, Optional[str]]]):
        super().__init__(name, description, version, author)
        self.validation_func = validation_func
        
    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """Run validation function"""
        return self.validation_func(value)

class TransformPlugin(Plugin):
    """Plugin for value transformation"""
    def __init__(self, name: str, description: str, version: str, author: str,
                 transform_func: Callable[[Any], Any]):
        super().__init__(name, description, version, author)
        self.transform_func = transform_func
        
    def transform(self, value: Any) -> Any:
        """Transform value"""
        return self.transform_func(value)

class PluginManager:
    """Manages field plugins"""
    
    def __init__(self):
        self.validators: Dict[str, ValidationPlugin] = {}
        self.transformers: Dict[str, TransformPlugin] = {}
        
    def load_plugins(self, plugin_dir: str) -> None:
        """Load all plugins from directory"""
        if not os.path.exists(plugin_dir):
            logger.warning(f"Plugin directory not found: {plugin_dir}")
            return
            
        for filename in os.listdir(plugin_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    self._load_plugin(os.path.join(plugin_dir, filename))
                except Exception as e:
                    logger.error(f"Error loading plugin {filename}: {e}")
                    
    def _load_plugin(self, plugin_path: str) -> None:
        """Load single plugin from file"""
        try:
            # Import plugin module
            spec = importlib.util.spec_from_file_location("plugin", plugin_path)
            if not spec or not spec.loader:
                logger.error(f"Could not load plugin: {plugin_path}")
                return
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Register plugin
            if hasattr(module, 'register_plugin'):
                plugin = module.register_plugin()
                if isinstance(plugin, ValidationPlugin):
                    self.validators[plugin.name] = plugin
                elif isinstance(plugin, TransformPlugin):
                    self.transformers[plugin.name] = plugin
                logger.info(f"Loaded plugin: {plugin.name} v{plugin.version}")
            else:
                logger.warning(f"No register_plugin function in {plugin_path}")
                
        except Exception as e:
            logger.error(f"Error in plugin {plugin_path}: {e}")
            
    def get_validator(self, name: str) -> Optional[ValidationPlugin]:
        """Get validation plugin by name"""
        return self.validators.get(name)
        
    def get_transformer(self, name: str) -> Optional[TransformPlugin]:
        """Get transformer plugin by name"""
        return self.transformers.get(name)
        
# Example plugin template
"""
from typing import Any, Optional
from .plugin import ValidationPlugin, TransformPlugin

def validate_custom(value: Any) -> tuple[bool, Optional[str]]:
    # Custom validation logic
    return True, None

def transform_custom(value: Any) -> Any:
    # Custom transformation logic
    return value

def register_plugin() -> ValidationPlugin:
    return ValidationPlugin(
        name="custom_validator",
        description="Custom validation plugin",
        version="1.0",
        author="Your Name",
        validation_func=validate_custom
    )
"""
