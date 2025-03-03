#!/usr/bin/env python3
import sys
import os
import glob

# Configure logging first
from ui.logging import get_logger
logger = get_logger('main')
logger.info('Starting test application')

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
from textual.widgets import Header, Footer, Button, Label, Select, Input
from textual.containers import Container, ScrollableContainer
from ui.components.fields.select_field import SelectField
from ui.components.fields.text_field import TextField

class TestMultiFieldsApp(App):
    """Test application for multiple fields"""
    CSS = """
    Screen {
        align: center middle;
    }
    
    #main-container {
        width: 100%;
        height: 100%;
        border: solid green;
        padding: 1;
    }
    
    #fields-container {
        width: 100%;
        height: auto;
        border: solid blue;
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
    
    .field-description {
        color: grey;
    }
    
    .field-input-container {
        width: 100%;
        border: solid purple;
    }
    """
    
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        
        # Main container 
        with Container(id="main-container"):
            yield Label("Test Multiple Fields", classes="title")
            
            # Container for fields
            with ScrollableContainer(id="fields-container"):
                # First field - TextField
                with Container(classes="field-container"):
                    with Container(classes="field-header"):
                        yield Label("Text Field", classes="field-label")
                        yield Label("*", classes="required-star")
                    
                    yield Label("Enter some text", classes="field-description")
                    
                    with Container(classes="field-input-container"):
                        text_field = TextField(
                            plugin_id="test",
                            plugin_path="test",
                            field_id="text_input",
                            field_config={
                                "label": "Text Field",
                                "description": "Enter some text",
                                "required": True,
                                "placeholder": "Text here..."
                            }
                        )
                        yield text_field
                
                # Second field - SelectField  
                with Container(classes="field-container"):
                    with Container(classes="field-header"):
                        yield Label("Select Field", classes="field-label")
                        yield Label("*", classes="required-star")
                    
                    yield Label("Select an option", classes="field-description")
                    
                    with Container(classes="field-input-container"):
                        select_field = SelectField(
                            plugin_id="test",
                            plugin_path="add_printer",
                            field_id="printer_model",
                            field_config={
                                "label": "Select Field",
                                "description": "Select an option",
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
        # Adding extra logging to see what widgets are actually mounted
        logger.info("--- WIDGET TREE ---")
        self._log_widget_tree(self, 0)
        logger.info("--- END WIDGET TREE ---")
    
    def _log_widget_tree(self, widget, level):
        """Log the widget tree recursively to help diagnose the problem."""
        indent = "  " * level
        logger.info(f"{indent}Widget: {widget.__class__.__name__} (ID: {widget.id or 'None'})")
        
        # For containers, log their children
        if hasattr(widget, 'children'):
            for child in widget.children:
                self._log_widget_tree(child, level + 1)
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        logger.debug(f"Button pressed: {event.button.id}")
        
        # Find all fields and log their values
        for field_type in [TextField, SelectField]:
            for field in self.query(field_type):
                value = field.get_value()
                logger.info(f"Field {field.field_id}: {value}")

if __name__ == "__main__":
    app = TestMultiFieldsApp()
    app.run()
