import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger
logger = get_logger('main')
logger.info('Starting application')

# Get the absolute path to the libs folder
# Assuming main.py is at the same level as the libs folder
libs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libs')

# Add all libs subdirectories to the search path
for pkg_dir in glob.glob(os.path.join(libs_dir, '*')):
    # Look for directories containing Python packages
    # Typically where .dist-info or .py files are stored
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
            
from ui.config import PluginConfig
from textual.app import App

class TestApp(App):
    def on_mount(self):
        # Créer une instance de PluginConfig avec le plugin home_copy
        plugin_screen = PluginConfig([("add_printer", 1)])
        self.push_screen(plugin_screen)

if __name__ == "__main__":
    app = TestApp()
    app.run()
