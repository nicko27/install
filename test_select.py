import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger
logger = get_logger('main')
logger.info('Starting application')

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
            
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Label
from textual.containers import Container
from ui.components.fields.select_field import SelectField

class TestApp(App):
    """A test application for the SelectField."""
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
            # Create a SelectField with empty initial options
            yield Label("Test Select Field with Empty Options:")
            yield Label("Select Printer Model", classes="field-label")
            yield Label("Select a printer model", classes="field-description")
            select_field = SelectField(
                plugin_id="test",
                plugin_path="add_printer",
                field_id="printer_model",
                field_config={
                    "label": "Select Printer Model",
                    "description": "Select a printer model",
                    "required": True,
                    "allow_blank": False,
                    "dynamic_options": {
                        "script": "get_printer_models.py",
                        "function": "get_printer_models",
                        "label_key": "description",
                        "value_key": "value"
                    }
                }
            )
            yield select_field
            
            # Add a button to test interaction
            yield Button("Test Button", id="test-button")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.debug("App mounted")
        # Log the select field information
        select_field = self.query_one(SelectField)
        select_widget = select_field.query_one(f"#select_{select_field.field_id}")
        logger.info(f"Select widget current value: {select_widget.value}")
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        logger.debug(f"Button pressed: {event.button.id}")
        # Get value from select field
        select_field = self.query_one(SelectField)
        value = select_field.get_value()
        logger.info(f"Selected value: {value}")

if __name__ == "__main__":
    app = TestApp()
    app.run()
