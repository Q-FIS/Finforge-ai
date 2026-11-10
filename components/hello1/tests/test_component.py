"""Unit tests for Hello1Component."""

import pytest
from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

from hello1.component import Hello1Component


def test_component_inheritance() -> None:
    """Verify component inherits from BaseComponent."""
    component = Hello1Component()
    assert isinstance(component, BaseComponent)


def test_component_lifecycle_execution() -> None:
    """Verify setup, run, and teardown lifecycle."""
    component = Hello1Component()

    # run() before setup() raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run({"input_data": [1, 2, 3]}, context={})

    # setup() with valid configuration
    component.setup({"scale_factor": 2.5})

    # run() returns expected deterministic output
    output = component.run({"input_data": [2.0, 4.0]}, context={"run_id": "test-1"})
    assert "output_data" in output
    assert output["output_data"] == [5.0, 10.0]

    # teardown() cleans up state safely
    component.teardown()


def test_invalid_configuration_rejected() -> None:
    """Verify invalid setup parameters raise ComponentConfigurationError."""
    component = Hello1Component()
    with pytest.raises(ComponentConfigurationError):
        component.setup({"scale_factor": "not-a-number"})


def test_invalid_input_rejected() -> None:
    """Verify missing or invalid inputs raise ComponentExecutionError."""
    component = Hello1Component()
    component.setup({})

    # Missing input port
    with pytest.raises(ComponentExecutionError):
        component.run({}, context={})

    # Invalid input type
    with pytest.raises(ComponentExecutionError):
        component.run({"input_data": "not-a-list"}, context={})
