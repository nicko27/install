"""Registry for validation plugins"""
import importlib.util
import inspect
import os
from typing import Dict, Type, Optional, List
from .base import ValidationRule
from ...logging import get_logger

logger = get_logger('validation')

class ValidationPluginRegistry:
    """Registry for validation plugins with auto-discovery"""
    
    _instance = None
    _plugins: Dict[str, Type[ValidationRule]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only discover plugins if they haven't been discovered yet
        if not self._plugins:
            logger.debug('Initializing validation plugin registry')
            self._discover_plugins()
            logger.info(f'Found {len(self._plugins)} validation plugins')
    
    @classmethod
    def register(cls, plugin_type: str, plugin_class: Type[ValidationRule]) -> None:
        """Register a validation plugin"""
        logger.debug(f"Registering validation plugin {plugin_class.__name__!r} as {plugin_type!r}")
        cls._plugins[plugin_type] = plugin_class
    
    @classmethod
    def get(cls, plugin_type: str) -> Optional[Type[ValidationRule]]:
        """Get validation plugin by type"""
        return cls._plugins.get(plugin_type)
    
    def _discover_plugins(self) -> None:
        """Auto-discover validation plugins"""
        # Get the plugins directory path
        plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        logger.debug(f"Searching for plugins in {plugins_dir}")
        
        if not os.path.exists(plugins_dir):
            logger.error(f"Plugin directory not found: {plugins_dir}")
            return
        
        # List all files in the directory
        try:
            files = os.listdir(plugins_dir)
            logger.debug(f"Found {len(files)} files in plugin directory")
            
            # Scan all Python files in the plugins directory
            for filename in files:
                if filename.endswith('.py') and not filename.startswith('__'):
                    module_path = os.path.join(plugins_dir, filename)
                    try:
                        # Import the module
                        spec = importlib.util.spec_from_file_location(
                            f"ui.components.validation.plugins.{filename[:-3]}",
                            module_path
                        )
                        if not spec or not spec.loader:
                            logger.error(f"Failed to create module spec for {filename}")
                            continue
                            
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Find validation rule classes
                        for name, obj in inspect.getmembers(module):
                            if (inspect.isclass(obj) and 
                                issubclass(obj, ValidationRule) and 
                                obj != ValidationRule):
                                # Register the plugin using its type name
                                plugin_type = name.lower().replace('validation', '')
                                self.register(plugin_type, obj)
                                
                    except Exception as e:
                        logger.error(f"Failed to load plugin {filename}: {e}")
        except Exception as e:
            logger.error(f"Failed to list plugin directory: {e}")
    
    def create_rule(self, plugin_type: str, **kwargs) -> Optional[ValidationRule]:
        """Create a validation rule instance"""
        logger.debug(f"Creating validation rule for type {plugin_type!r}")
        plugin_class = self.get(plugin_type)
        if plugin_class:
            return plugin_class(**kwargs)
        logger.error(f"Plugin type not found: {plugin_type}")
        return None
    
    def list_plugins(self) -> Dict[str, str]:
        """List available validation plugins"""
        plugins = {name: plugin.__doc__ or '' 
                for name, plugin in self._plugins.items()}
        logger.info(f"Found {len(plugins)} validation plugins")
        for name in plugins:
            logger.debug(f"Found plugin {self._plugins[name].__name__!r} as {name!r}")
        return plugins

def register_plugin(plugin_type: str, plugin_class: Type[ValidationRule]) -> None:
    """Register a validation plugin"""
    ValidationPluginRegistry.register(plugin_type, plugin_class)
