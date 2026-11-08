"""Unit tests for ExampleComponent demonstration implementation."""

import pytest

from finforge.example import ExampleComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


def test_example_component_initial_state() -> None:
    """Verify default initial state of ExampleComponent."""
    component = ExampleComponent()
    assert component.is_setup is False
    assert repr(component) == "<ExampleComponent>"


def test_example_component_setup_default() -> None:
    """Verify setup() with empty config defaults to uppercase and empty prefix."""
    component = ExampleComponent()
    component.setup({})
    assert component.is_setup is True


def test_example_component_setup_custom() -> None:
    """Verify setup() with valid custom parameters."""
    component = ExampleComponent()
    component.setup({"mode": "lowercase", "prefix": "out_"})
    assert component.is_setup is True


def test_example_component_setup_invalid_type() -> None:
    """Verify setup() raises ComponentConfigurationError if config is not a dict."""
    component = ExampleComponent()
    with pytest.raises(ComponentConfigurationError) as excinfo:
        component.setup("not a dict")  # type: ignore[arg-type]
    assert "Configuration must be a dictionary" in str(excinfo.value)


def test_example_component_setup_invalid_mode() -> None:
    """Verify setup() raises ComponentConfigurationError on invalid mode."""
    component = ExampleComponent()
    with pytest.raises(ComponentConfigurationError) as excinfo:
        component.setup({"mode": "unsupported_mode"})
    assert "Invalid mode 'unsupported_mode'" in str(excinfo.value)
    assert "Supported modes are" in str(excinfo.value)


def test_example_component_setup_invalid_prefix() -> None:
    """Verify setup() raises ComponentConfigurationError if prefix is not a string."""
    component = ExampleComponent()
    with pytest.raises(ComponentConfigurationError) as excinfo:
        component.setup({"prefix": 123})
    assert "Prefix must be a string" in str(excinfo.value)


def test_example_component_run_before_setup_raises_lifecycle_error() -> None:
    """Verify run() raises ComponentLifecycleError if invoked before setup()."""
    component = ExampleComponent()
    with pytest.raises(ComponentLifecycleError) as excinfo:
        component.run({"text": "hello"}, {})
    assert "must be configured via setup() before calling run()" in str(excinfo.value)


@pytest.mark.parametrize(
    ("mode", "prefix", "input_text", "expected_result", "expected_len"),
    [
        ("uppercase", "TAG: ", "hello world", "TAG: HELLO WORLD", 16),
        ("lowercase", "", "HeLLo WoRLD", "hello world", 11),
        ("reverse", "REV_", "Python", "REV_nohtyP", 10),
    ],
)
def test_example_component_run_modes(
    mode: str,
    prefix: str,
    input_text: str,
    expected_result: str,
    expected_len: int,
) -> None:
    """Verify deterministic transformation across modes with context propagation."""
    component = ExampleComponent()
    component.setup({"mode": mode, "prefix": prefix})

    outputs = component.run({"text": input_text}, {"execution_id": "exec-42"})

    assert outputs["result"] == expected_result
    assert outputs["length"] == expected_len
    assert outputs["mode"] == mode
    assert outputs["execution_id"] == "exec-42"


def test_example_component_run_without_execution_id() -> None:
    """Verify run() works when context does not contain execution_id."""
    component = ExampleComponent()
    component.setup({})
    outputs = component.run({"text": "test"}, {})
    assert outputs["result"] == "TEST"
    assert outputs["execution_id"] is None


def test_example_component_run_invalid_inputs_type() -> None:
    """Verify run() raises ComponentExecutionError when inputs is not a dict."""
    component = ExampleComponent()
    component.setup({})
    with pytest.raises(ComponentExecutionError) as excinfo:
        component.run(["not", "a", "dict"], {})  # type: ignore[arg-type]
    assert "Inputs must be a dictionary" in str(excinfo.value)


def test_example_component_run_missing_text_key() -> None:
    """Verify run() raises ComponentExecutionError when 'text' key is missing."""
    component = ExampleComponent()
    component.setup({})
    with pytest.raises(ComponentExecutionError) as excinfo:
        component.run({"data": "some value"}, {})
    assert "Missing required input key: 'text'" in str(excinfo.value)


def test_example_component_run_invalid_text_type() -> None:
    """Verify run() raises ComponentExecutionError when 'text' is not a string."""
    component = ExampleComponent()
    component.setup({})
    with pytest.raises(ComponentExecutionError) as excinfo:
        component.run({"text": 999}, {})
    assert "Input 'text' must be a string" in str(excinfo.value)


def test_example_component_run_invalid_context_type() -> None:
    """Verify run() raises ComponentExecutionError when context is not a dict."""
    component = ExampleComponent()
    component.setup({})
    with pytest.raises(ComponentExecutionError) as excinfo:
        component.run({"text": "valid"}, "not a dict")  # type: ignore[arg-type]
    assert "Context must be a dictionary" in str(excinfo.value)


def test_example_component_teardown_and_reinitialization() -> None:
    """Verify teardown resets internal state, is idempotent, and allows re-setup."""
    component = ExampleComponent()
    component.setup({"mode": "reverse", "prefix": "PRE:"})
    assert component.is_setup is True

    # Teardown once
    component.teardown()
    assert component.is_setup is False

    # Calling run after teardown raises lifecycle error
    with pytest.raises(ComponentLifecycleError):
        component.run({"text": "test"}, {})

    # Teardown again (idempotent)
    component.teardown()
    assert component.is_setup is False

    # Can be re-setup and run cleanly
    component.setup({"mode": "uppercase"})
    assert component.is_setup is True
    out = component.run({"text": "again"}, {})
    assert out["result"] == "AGAIN"
