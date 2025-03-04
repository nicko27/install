from ruamel.yaml import YAML
import os
from .logging import get_logger

logger = get_logger('config_manager')

class ConfigManager:
    """Manager for both plugin and global configurations"""

    def __init__(self):
        self.global_configs = {}  # {config_id: {config_data}}
        self.plugin_configs = {}  # {plugin_id: {config_data}}
        self.yaml = YAML()

    def load_global_config(self, config_id, config_path):
        """Load a global configuration from a YAML file."""
        try:
            with open(config_path, 'r') as f:
                config = self.yaml.load(f)
                self.global_configs[config_id] = config
                logger.debug(f"Global config '{config_id}' loaded: {config}")
                return config
        except Exception as e:
            logger.error(f"Error loading config '{config_id}': {e}")
            return None

    def load_plugin_config(self, plugin_id, settings_path):
        """Load a plugin configuration."""
        try:
            with open(settings_path, 'r') as f:
                config = self.yaml.load(f)
                self.plugin_configs[plugin_id] = config
                logger.debug(f"Plugin config '{plugin_id}' loaded")
                return config
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_id}': {e}")
            return None

    def get_fields(self, config_id, is_global=False):
        """Get fields from a configuration."""
        source = self.global_configs if is_global else self.plugin_configs
        config = source.get(config_id, {})

        # Global configs use 'fields', plugins use 'config_fields'
        field_key = 'fields' if is_global else 'config_fields'
        return config.get(field_key, {})

    def supports_remote_execution(self, plugin_id):
        """Check if a plugin supports remote execution."""
        config = self.plugin_configs.get(plugin_id, {})
        return config.get('remote_execution', False)