"""Unit tests for RiskCalculatorComponent."""

import pytest
from risk_calculator.component import RiskCalculatorComponent

from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


def test_risk_calculator_lifecycle() -> None:
    calculator = RiskCalculatorComponent()

    # Must fail if run() is invoked before setup()
    with pytest.raises(ComponentLifecycleError):
        calculator.run({"amount": 100.0}, context={})

    # Setup with custom threshold
    calculator.setup({"threshold": 1000.0})

    # Normal execution
    low_result = calculator.run({"amount": 500.0}, context={})
    assert low_result == {"risk_level": "LOW"}

    high_result = calculator.run({"amount": 1500.0}, context={})
    assert high_result == {"risk_level": "HIGH"}

    # Teardown
    calculator.teardown()
    with pytest.raises(ComponentLifecycleError):
        calculator.run({"amount": 500.0}, context={})


def test_default_threshold() -> None:
    calculator = RiskCalculatorComponent()
    calculator.setup({})  # Uses default threshold (10000.0)

    assert calculator.run({"amount": 9999.0}, context={}) == {"risk_level": "LOW"}
    assert calculator.run({"amount": 10000.0}, context={}) == {"risk_level": "HIGH"}


def test_invalid_configuration() -> None:
    calculator = RiskCalculatorComponent()
    with pytest.raises(ComponentConfigurationError):
        calculator.setup({"threshold": "not-a-number"})


def test_missing_input_amount() -> None:
    calculator = RiskCalculatorComponent()
    calculator.setup({})
    with pytest.raises(ComponentExecutionError):
        calculator.run({}, context={})


def test_invalid_input_type() -> None:
    calculator = RiskCalculatorComponent()
    calculator.setup({})
    with pytest.raises(ComponentExecutionError):
        calculator.run({"amount": "invalid-amount"}, context={})
