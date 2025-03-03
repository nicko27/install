#!/usr/bin/env python3
import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger
logger = get_logger('test_plugin_config')
logger.info('Starting test plugin config application')

# Get the absolute path to the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Look for directories containing Python packages
    for subdir in glob.glob(os.path.join(pkg_dir, '*')):
        if os.path.isdir(subdir) and (
            subdir.endswith('.dist-info') or 
            os.path.exists(os.path.join(subdir, '__init__.py')) or
            subdir.endswith('.data')
        ):
            # Add the parent directory to the search path
            parent_dir = os.path.dirname(subdir)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                logger.debug(f"Added {parent_dir} to sys.path")
        
        # Also add the main package directory to the path
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)
            logger.debug(f"Added {pkg_dir} to sys.path")
            
from textual.app import App
from textual.widgets import Button
from ui.config import PluginConfig

class TestPluginConfigApp(App):
    """Test application to show plugin configuration"""
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "show_config":
            logger.info("Showing config for add_printer plugin")
            plugin_config = PluginConfig([("add_printer", 0)])
            self.push_screen(plugin_config)
        elif event.button.id == "quit":
            logger.info("Quitting application")
            self.exit()

    async def on_mount(self) -> None:
        """Handle app mounting - log widget tree to help diagnose issues"""
        
        # Create a simple button to show the plugin config
        button = Button("Show Printer Config", id="show_config", variant="primary")
        await self.mount(button)
        
        quit_button = Button("Quit", id="quit", variant="error")
        await self.mount(quit_button)
        
        # Log the widget tree
        logger.info("--- Initial Widget Tree ---")
        self._log_widget_tree(self, 0)
        logger.info("--- End Initial Widget Tree ---")
    
    def _log_widget_tree(self, widget, level):
        """Log the widget tree recursively"""
        indent = "  " * level
        logger.info(f"{indent}Widget: {widget.__class__.__name__} (ID: {widget.id or 'None'})")
        
        # For containers, log their children
        if hasattr(widget, 'children'):
            for child in widget.children:
                self._log_widget_tree(child, level + 1)
                
if __name__ == "__main__":
    app = TestPluginConfigApp()
    app.run()
