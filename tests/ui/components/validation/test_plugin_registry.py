"""Tests for validation plugin registry"""
import pytest
from ui.components.validation import create_rule, list_plugins
from ui.components.validation.plugin_registry import ValidationPluginRegistry

def test_plugin_discovery():
    """Test that plugins are auto-discovered"""
    plugins = list_plugins()
    assert len(plugins) > 0
    assert 'required' in plugins
    assert 'integer' in plugins
    assert 'float' in plugins
    assert 'email' in plugins

def test_create_rule():
    """Test rule creation"""
    # Required rule
    rule = create_rule('required', message="Field is required")
    assert rule is not None
    success, message = rule("")
    assert not success
    assert message == "Field is required"
    
    # Integer rule
    rule = create_rule('integer', message="Must be an integer")
    assert rule is not None
    success, message = rule("123")
    assert success
    success, message = rule("abc")
    assert not success
    assert message == "Must be an integer"
    
    # Range rule
    rule = create_rule('range', min_value=0, max_value=100)
    assert rule is not None
    success, message = rule("50")
    assert success
    success, message = rule("150")
    assert not success
    assert "less than" in message.lower()

def test_unknown_plugin():
    """Test handling of unknown plugin types"""
    rule = create_rule('nonexistent')
    assert rule is None

def test_plugin_registration():
    """Test manual plugin registration"""
    registry = ValidationPluginRegistry()
    
    # Create a test validation rule
    class TestValidation(ValidationRule):
        def __call__(self, value):
            return True, None
    
    # Register the plugin
    registry.register('test', TestValidation)
    assert 'test' in registry.list_plugins()
    
    # Create and use the rule
    rule = registry.create_rule('test')
    assert rule is not None
    success, message = rule("any value")
    assert success
