"""Unit tests for TextCleanerComponent."""

import pytest
from text_cleaner.component import TextCleanerComponent

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


def test_component_inheritance() -> None:
    """Verify component inherits from BaseComponent."""
    component = TextCleanerComponent()
    assert isinstance(component, BaseComponent)


def test_component_lifecycle_execution() -> None:
    """Verify setup, run, and teardown lifecycle."""
    component = TextCleanerComponent()

    # run() before setup() raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run({"input_data": "Hello FinForge"}, context={})

    # setup() with valid configuration
    component.setup({"lowercase": True})

    # run() returns expected deterministic output
    inputs = {"input_data": "  Hello     FinForge   AI!  "}

    output = component.run(inputs, context={"run_id": "test-1"})

    assert "output_data" in output
    assert output["output_data"] == "hello finforge ai!"

    # teardown() cleans up state safely
    component.teardown()

    # run() after teardown raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run(inputs, context={})


def test_invalid_configuration_rejected() -> None:
    """Verify invalid setup parameters raise ComponentConfigurationError."""
    component = TextCleanerComponent()

    with pytest.raises(ComponentConfigurationError):
        component.setup({"lowercase": "yes"})


def test_invalid_input_rejected() -> None:
    """Verify missing or invalid inputs raise ComponentExecutionError."""
    component = TextCleanerComponent()
    component.setup({})

    # Missing input port
    with pytest.raises(ComponentExecutionError):
        component.run({}, context={})

    # Invalid input type
    with pytest.raises(ComponentExecutionError):
        component.run({"input_data": ["Hello", "FinForge"]}, context={})


def test_whitespace_normalization() -> None:
    """Verify multiple spaces, tabs, and newlines are normalized."""
    component = TextCleanerComponent()
    component.setup({"lowercase": False})

    output = component.run(
        {"input_data": "  Hello     FinForge \n AI\tFramework  "},
        context={},
    )

    assert output["output_data"] == "Hello FinForge AI Framework"

    component.teardown()


def test_empty_string() -> None:
    """Verify empty strings are handled correctly."""
    component = TextCleanerComponent()
    component.setup({})

    output = component.run(
        {"input_data": ""},
        context={},
    )

    assert output["output_data"] == ""

    component.teardown()


def test_lowercase_disabled() -> None:
    """Verify original letter casing is preserved when lowercase is disabled."""
    component = TextCleanerComponent()
    component.setup({"lowercase": False})

    output = component.run(
        {"input_data": "Hello FINFORGE AI"},
        context={},
    )

    assert output["output_data"] == "Hello FINFORGE AI"

    component.teardown()


def test_lowercase_enabled() -> None:
    """Verify text is converted to lowercase when enabled."""
    component = TextCleanerComponent()
    component.setup({"lowercase": True})

    output = component.run(
        {"input_data": "Hello FINFORGE AI"},
        context={},
    )

    assert output["output_data"] == "hello finforge ai"

    component.teardown()


def test_unicode_text() -> None:
    """Verify Unicode text is preserved during cleaning."""
    component = TextCleanerComponent()
    component.setup({})

    output = component.run(
        {"input_data": "  नमस्ते   दुनिया  Café  "},
        context={},
    )

    assert output["output_data"] == "नमस्ते दुनिया Café"

    component.teardown()
