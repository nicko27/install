"""Tests for number validation plugins"""
import pytest
from ui.components.validation.plugins.number import (
    IntegerValidation,
    FloatValidation,
    RangeValidation
)

def test_integer_validation():
    """Test integer validation"""
    rule = IntegerValidation()
    
    # Test valid integers
    assert rule("123")[0]
    assert rule("-456")[0]
    assert rule("0")[0]
    
    # Test invalid integers
    assert not rule("12.34")[0]
    assert not rule("abc")[0]
    assert not rule("12a")[0]
    
    # Test empty values (should pass)
    assert rule("")[0]
    assert rule(None)[0]

def test_float_validation():
    """Test float validation"""
    rule = FloatValidation()
    
    # Test valid floats
    assert rule("123.45")[0]
    assert rule("-67.89")[0]
    assert rule("0.0")[0]
    assert rule("123")[0]  # integers are valid floats
    
    # Test invalid floats
    assert not rule("abc")[0]
    assert not rule("12.34.56")[0]
    assert not rule("12a")[0]
    
    # Test empty values (should pass)
    assert rule("")[0]
    assert rule(None)[0]

def test_range_validation():
    """Test range validation"""
    rule = RangeValidation(min_value=0, max_value=100)
    
    # Test values within range
    assert rule("0")[0]
    assert rule("50")[0]
    assert rule("100")[0]
    assert rule("12.34")[0]
    
    # Test values outside range
    assert not rule("-1")[0]
    assert not rule("101")[0]
    assert not rule("-50.5")[0]
    assert not rule("150.5")[0]
    
    # Test invalid numbers
    assert not rule("abc")[0]
    
    # Test empty values (should pass)
    assert rule("")[0]
    assert rule(None)[0]
    
    # Test custom message
    rule = RangeValidation(min_value=0, max_value=100, message="Custom message")
    success, message = rule("150")
    assert not success
    assert message == "Custom message"
    
    # Test min_value only
    rule = RangeValidation(min_value=0)
    assert rule("50")[0]
    assert not rule("-1")[0]
    
    # Test max_value only
    rule = RangeValidation(max_value=100)
    assert rule("50")[0]
    assert not rule("101")[0]
