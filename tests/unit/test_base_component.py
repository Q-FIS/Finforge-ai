"""Unit tests for the BaseComponent interface and lifecycle contract."""

from typing import Any

import pytest

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentError,
    ComponentExecutionError,
    ComponentLifecycleError,
    FinForgeError,
)


class DummyValidComponent(BaseComponent):
    """Minimal valid component implementing all abstract methods."""

    def __init__(self) -> None:
        self.received_config: dict[str, Any] | None = None
        self.received_inputs: dict[str, Any] | None = None
        self.received_context: dict[str, Any] | None = None

    def setup(self, config: dict[str, Any]) -> None:
        self.received_config = config

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        self.received_inputs = inputs
        self.received_context = context
        return {"echo": inputs.get("value"), "status": "processed"}


class DummyCustomTeardownComponent(BaseComponent):
    """Component overriding teardown."""

    def __init__(self) -> None:
        self.teardown_called: bool = False

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {}

    def teardown(self) -> None:
        self.teardown_called = True


class DummyErrorComponent(BaseComponent):
    """Component that raises errors to test propagation."""

    def setup(self, config: dict[str, Any]) -> None:
        if config.get("fail_setup"):
            raise ComponentConfigurationError("Simulated setup failure")

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if inputs.get("fail_run"):
            raise ComponentExecutionError("Simulated run failure")
        return {}

    def teardown(self) -> None:
        raise ComponentLifecycleError("Simulated teardown failure")


def test_base_component_cannot_be_instantiated_directly() -> None:
    """1. BaseComponent cannot be instantiated directly as it has abstract methods."""
    with pytest.raises(TypeError) as excinfo:
        BaseComponent()  # type: ignore[abstract]
    assert "Can't instantiate abstract class BaseComponent" in str(excinfo.value)


def test_valid_custom_component_can_be_instantiated() -> None:
    """2. A valid custom component can be instantiated."""
    component = DummyValidComponent()
    assert isinstance(component, BaseComponent)
    assert repr(component) == "<DummyValidComponent>"


def test_required_abstract_methods_must_be_implemented() -> None:
    """3. Subclasses missing setup() or run() cannot be instantiated."""

    # Missing both
    class IncompleteBoth(BaseComponent):
        pass

    with pytest.raises(TypeError) as excinfo:
        IncompleteBoth()  # type: ignore[abstract]
    assert "run" in str(excinfo.value)
    assert "setup" in str(excinfo.value)

    # Missing run
    class IncompleteRun(BaseComponent):
        def setup(self, config: dict[str, Any]) -> None:
            pass

    with pytest.raises(TypeError) as excinfo:
        IncompleteRun()  # type: ignore[abstract]
    assert "run" in str(excinfo.value)

    # Missing setup
    class IncompleteSetup(BaseComponent):
        def run(
            self,
            inputs: dict[str, Any],
            context: dict[str, Any],
        ) -> dict[str, Any]:
            return {}

    with pytest.raises(TypeError) as excinfo:
        IncompleteSetup()  # type: ignore[abstract]
    assert "setup" in str(excinfo.value)


def test_setup_receives_configuration() -> None:
    """4. setup() receives configuration dictionary."""
    component = DummyValidComponent()
    config = {"param_a": 42, "param_b": "value"}
    component.setup(config)
    assert component.received_config == config


def test_run_receives_inputs_and_context() -> None:
    """5. run() receives inputs and context dictionaries."""
    component = DummyValidComponent()
    component.setup({"learning_rate": 0.01})

    inputs = {"value": 100}
    context = {"user_id": "test_user", "step": 1}
    component.run(inputs, context)

    assert component.received_inputs == inputs
    assert component.received_context == context


def test_run_returns_expected_output_dictionary() -> None:
    """6. run() returns the expected output dictionary."""
    component = DummyValidComponent()
    component.setup({})
    result = component.run({"value": "finforge"}, {"trace_id": "abc-123"})

    assert isinstance(result, dict)
    assert result == {"echo": "finforge", "status": "processed"}


def test_teardown_can_be_overridden() -> None:
    """7. teardown() can be overridden by a subclass."""
    component = DummyCustomTeardownComponent()
    assert component.teardown_called is False
    component.teardown()
    assert component.teardown_called is True


def test_default_teardown_does_not_fail() -> None:
    """8. Default teardown() implementation is a safe no-op returning None."""
    component = DummyValidComponent()
    # Calling teardown() should succeed without error
    result = component.teardown()
    assert result is None


def test_component_methods_propagate_errors() -> None:
    """9. Component methods propagate errors rather than silently swallowing them."""
    component = DummyErrorComponent()

    # setup error propagation
    with pytest.raises(ComponentConfigurationError) as exc_setup:
        component.setup({"fail_setup": True})
    assert "Simulated setup failure" in str(exc_setup.value)

    # run error propagation
    with pytest.raises(ComponentExecutionError) as exc_run:
        component.run({"fail_run": True}, {})
    assert "Simulated run failure" in str(exc_run.value)

    # teardown error propagation
    with pytest.raises(ComponentLifecycleError) as exc_teardown:
        component.teardown()
    assert "Simulated teardown failure" in str(exc_teardown.value)


def test_exception_hierarchy() -> None:
    """Verify custom exceptions inherit from FinForgeError and Exception."""
    assert issubclass(ComponentError, FinForgeError)
    assert issubclass(ComponentConfigurationError, ComponentError)
    assert issubclass(ComponentExecutionError, ComponentError)
    assert issubclass(ComponentLifecycleError, ComponentError)
    assert issubclass(FinForgeError, Exception)
