from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.datetime_utils import utcnow
from app.schemas.calculation import (
    CalculationBase,
    CalculationResponse,
    CalculationUpdate,
)


def test_calculation_base_valid():
    """Test creating a valid CalculationBase schema."""
    data = {
        "type": "addition",
        "inputs": [10.5, 3.0]
    }
    calc = CalculationBase(**data)
    assert calc.type == "addition"
    assert calc.inputs == [10.5, 3.0]

def test_calculation_base_missing_type():
    """Test CalculationBase fails if 'type' is missing."""
    data = {
        "inputs": [10.5, 3.0]
    }
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(**data)
    # Look for a substring that indicates a missing required field.
    assert "required" in str(exc_info.value).lower()

def test_calculation_base_missing_inputs():
    """Test CalculationBase fails if 'inputs' is missing."""
    data = {
        "type": "multiplication"
    }
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(**data)
    assert "required" in str(exc_info.value).lower()

def test_calculation_base_invalid_inputs():
    """Test CalculationBase fails if 'inputs' is not a list of floats."""
    data = {
        "type": "division",
        "inputs": "not-a-list"
    }
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(**data)
    error_message = str(exc_info.value)
    # Ensure that our custom error message is present (case-insensitive)
    assert "input should be a valid list" in error_message.lower(), error_message

def test_calculation_base_unsupported_type():
    """Test CalculationBase fails if an unsupported calculation type is provided."""
    data = {
        "type": "square_root",  # Unsupported type
        "inputs": [25, 5]
    }
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(**data)
    error_message = str(exc_info.value).lower()
    # Check that the error message indicates the value is not permitted.
    assert "one of" in error_message or "not a valid" in error_message

def test_calculation_base_requires_two_inputs():
    """Test CalculationBase rejects a single operand."""
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(type="addition", inputs=[25])
    assert "at least 2 items" in str(exc_info.value).lower()

def test_calculation_base_rejects_division_by_zero():
    """Test CalculationBase rejects a zero divisor."""
    with pytest.raises(ValidationError) as exc_info:
        CalculationBase(type="division", inputs=[10, 0])
    assert "cannot divide by zero" in str(exc_info.value).lower()

def test_calculation_update_valid():
    """Test a valid partial update with CalculationUpdate."""
    data = {
        "inputs": [42.0, 7.0]
    }
    calc_update = CalculationUpdate(**data)
    assert calc_update.inputs == [42.0, 7.0]

def test_calculation_update_no_fields():
    """Test that an empty update is allowed (i.e., no fields)."""
    calc_update = CalculationUpdate()
    assert calc_update.inputs is None

def test_calculation_response_valid():
    """Test creating a valid CalculationResponse schema."""
    data = {
        "id": uuid4(),
        "user_id": uuid4(),
        "type": "subtraction",
        "inputs": [20, 5],
        "result": 15.5,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    calc_response = CalculationResponse(**data)
    assert calc_response.id is not None
    assert calc_response.user_id is not None
    assert calc_response.type == "subtraction"
    assert calc_response.inputs == [20, 5]
    assert calc_response.result == 15.5
