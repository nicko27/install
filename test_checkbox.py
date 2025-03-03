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
import logging
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Container

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("checkbox_test")

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the CheckboxGroupField
from ui.components.fields.checkbox_group_field import CheckboxGroupField

class TestApp(App):
    """A test application for the CheckboxGroupField."""
    
    CSS = """
    #test-container {
        width: 100%;
        height: 100%;
        padding: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        
        with Container(id="test-container"):
            # Create a CheckboxGroupField with dynamic options from get_users.py
            checkbox_field = CheckboxGroupField(
                plugin_id="test",
                plugin_path="/path/to/plugin",
                field_id="users",
                field_config={
                    "label": "Select Users",
                    "description": "Select one or more users",
                    "dynamic_options": {
                        "script": "./utils/get_users.py",
                        "function": "get_users"
                    }
                }
            )
            yield checkbox_field
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.debug("App mounted")

if __name__ == "__main__":
    app = TestApp()
    app.run()
