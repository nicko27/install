"""Tests for required validation plugin"""
import pytest
from ui.components.validation.plugins.required import RequiredValidation

def test_required_validation():
    """Test required validation"""
    rule = RequiredValidation()
    
    # Test empty values
    assert not rule("")[0]
    assert not rule(None)[0]
    assert not rule("   ")[0]
    
    # Test valid values
    assert rule("test")[0]
    assert rule("0")[0]
    assert rule(" x ")[0]
    
    # Test custom message
    rule = RequiredValidation(message="Custom message")
    success, message = rule("")
    assert not success
    assert message == "Custom message"
