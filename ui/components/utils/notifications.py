"""Notification system for field validation and errors"""
from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Static
from textual.notifications import Notification as TextualNotification

class ValidationNotification:
    """Helper class for showing validation notifications"""
    
    @staticmethod
    def error(message: str, field_id: Optional[str] = None, timeout: float = 5.0):
        """Show error notification"""
        title = f"Validation Error: {field_id}" if field_id else "Validation Error"
        TextualNotification(title=title, message=message, severity="error", timeout=timeout)
    
    @staticmethod
    def warning(message: str, field_id: Optional[str] = None, timeout: float = 5.0):
        """Show warning notification"""
        title = f"Warning: {field_id}" if field_id else "Warning"
        TextualNotification(title=title, message=message, severity="warning", timeout=timeout)
    
    @staticmethod
    def info(message: str, field_id: Optional[str] = None, timeout: float = 5.0):
        """Show info notification"""
        title = f"Info: {field_id}" if field_id else "Info"
        TextualNotification(title=title, message=message, severity="information", timeout=timeout)

class FieldError(Static):
    """Widget to display field-level error messages"""
    
    DEFAULT_CSS = """
    FieldError {
        color: red;
        padding: 1;
        margin-left: 1;
        display: none;
    }
    
    FieldError.visible {
        display: block;
    }
    """
    
    def __init__(self, field_id: str):
        super().__init__("")
        self.field_id = field_id
    
    def show_error(self, message: str):
        """Show error message"""
        self.update(message)
        self.add_class("visible")
    
    def clear(self):
        """Clear error message"""
        self.update("")
        self.remove_class("visible")

class ValidationMessage(Message):
    """Message for validation events"""
    
    def __init__(self, field_id: str, success: bool, message: Optional[str] = None):
        super().__init__()
        self.field_id = field_id
        self.success = success
        self.message = message

class DependencyMessage(Message):
    """Message for dependency updates"""
    
    def __init__(self, source_field: str, target_field: str, value: any):
        super().__init__()
        self.source_field = source_field
        self.target_field = target_field
        self.value = value
