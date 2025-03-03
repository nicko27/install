#!/usr/bin/env python3
import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger
logger = get_logger('test_config_simple')
logger.info('Starting test configuration application (simplified)')

# Get the absolute path to the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
        logger.debug(f"Added {pkg_dir} to sys.path")

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Label, Select, Input
from textual.containers import Container, ScrollableContainer, Horizontal, VerticalScroll, Vertical
from ruamel.yaml import YAML

class SimpleConfig(App):
    """Simple version of the configuration app using direct widgets instead of field classes"""
    
    CSS = """
    Screen {
        align: center middle;
    }
    
    #config-container {
        width: 80%;
        height: 80%;
        border: solid green;
        padding: 1;
    }
    
    .field-container {
        width: 100%;
        height: auto;
        border: solid red;
        padding: 1;
        margin-bottom: 1;
    }
    
    .field-header {
        width: 100%;
        border: solid yellow;
    }
    
    .field-label {
        color: white;
        text-style: bold;
    }
    
    .field-description {
        color: grey;
    }
    
    .field-input-container {
        width: 100%;
        border: solid purple;
    }
    
    Select, Input {
        width: 100%;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with Container(id="config-container"):
            yield Label("Simple Configuration Test", classes="title")
            
            plugin_dir = os.path.join(os.path.dirname(__file__), 'plugins', 'add_printer')
            config_file = os.path.join(plugin_dir, 'settings.yml')
            
            # Load plugin settings
            yaml = YAML()
            with open(config_file, 'r') as f:
                config = yaml.load(f)
            
            # Get configuration fields
            config_fields_dict = config.get('config_fields', {})
            
            # Create each field directly with standard widgets
            for field_id, field_config in config_fields_dict.items():
                field_type = field_config.get('type', 'text')
                logger.info(f"Creating field: {field_id} (type: {field_type})")
                
                with Container(classes="field-container"):
                    with Container(classes="field-header"):
                        yield Label(field_config.get('label', field_id), classes="field-label")
                        if field_config.get('required', False):
                            yield Label("*", classes="required-star")
                    
                    if 'description' in field_config:
                        yield Label(field_config['description'], classes="field-description")
                    
                    with Container(classes="field-input-container"):
                        if field_type == 'text':
                            yield Input(placeholder=field_config.get('placeholder', ''), id=f"input_{field_id}")
                        elif field_type == 'select':
                            # Hard-code some options for testing
                            options = [
                                ("Option 1", "option1"),
                                ("Option 2", "option2"),
                                ("Option 3", "option3")
                            ]
                            yield Select(options=options, id=f"select_{field_id}")
                
        yield Footer()
    
    def on_mount(self) -> None:
        """Handle app mounting - log widget tree to help diagnose issues"""
        logger.info("App mounted")
        logger.info("--- Widget Tree ---")
        self._log_widget_tree(self, 0)
        logger.info("--- End Widget Tree ---")
    
    def _log_widget_tree(self, widget, level):
        """Log the widget tree recursively"""
        indent = "  " * level
        logger.info(f"{indent}Widget: {widget.__class__.__name__} (ID: {widget.id or 'None'})")
        
        # For containers, log their children
        if hasattr(widget, 'children'):
            for child in widget.children:
                self._log_widget_tree(child, level + 1)

if __name__ == "__main__":
    app = SimpleConfig()
    app.run()
