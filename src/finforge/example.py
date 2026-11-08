"""Demonstration component implementation for FinForge AI.

This module provides `ExampleComponent`, a reference implementation of `BaseComponent`
that illustrates configuration validation, lifecycle enforcement, context consumption,
and safe teardown using standard Python.
"""

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

_VALID_MODES = frozenset({"uppercase", "lowercase", "reverse"})


class ExampleComponent(BaseComponent):
    """Reference component performing deterministic text transformation.

    This component demonstrates the FinForge AI component contract:
      - Validates configuration in `setup()` (supports modes: 'uppercase',
        'lowercase', 'reverse', and an optional 'prefix').
      - Enforces lifecycle state (raises `ComponentLifecycleError` if `run()`
        is invoked before `setup()`).
      - Validates inputs and incorporates runtime context in `run()`.
      - Provides an idempotent `teardown()` that releases state.

    Input Contract:
      - "text" (str): The input string to transform.

    Output Contract:
      - "result" (str): The transformed text with prefix applied.
      - "length" (int): The character length of the transformed text.
      - "mode" (str): The transformation mode applied.
      - "execution_id" (str | None): Propagated from context if provided.
    """

    def __init__(self) -> None:
        """Initialize an unconfigured ExampleComponent."""
        self._is_setup: bool = False
        self._mode: str = "uppercase"
        self._prefix: str = ""

    @property
    def is_setup(self) -> bool:
        """Return True if setup() has been executed, False otherwise."""
        return self._is_setup

    def setup(self, config: dict[str, Any]) -> None:
        """Configure the component with transformation mode and prefix.

        Args:
            config: Configuration dictionary. Supported keys:
                - "mode" (str, optional): Transformation mode ('uppercase',
                  'lowercase', 'reverse'). Defaults to 'uppercase'.
                - "prefix" (str, optional): String prefix prepended to the result.
                  Defaults to "".

        Raises:
            ComponentConfigurationError: If config is not a dict or 'mode' is invalid.
        """
        if not isinstance(config, dict):
            raise ComponentConfigurationError("Configuration must be a dictionary.")

        mode = config.get("mode", "uppercase")
        if not isinstance(mode, str) or mode not in _VALID_MODES:
            valid_list = ", ".join(sorted(_VALID_MODES))
            raise ComponentConfigurationError(
                f"Invalid mode '{mode}'. Supported modes are: {valid_list}."
            )

        prefix = config.get("prefix", "")
        if not isinstance(prefix, str):
            raise ComponentConfigurationError(
                f"Prefix must be a string, got {type(prefix).__name__}."
            )

        self._mode = mode
        self._prefix = prefix
        self._is_setup = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Transform input text according to configured mode and prefix.

        Args:
            inputs: Dictionary containing input parameters. Must contain "text" (str).
            context: Dictionary containing runtime context. May contain "execution_id".

        Returns:
            Dictionary containing "result", "length", "mode", and "execution_id".

        Raises:
            ComponentLifecycleError: If run() is called before setup().
            ComponentExecutionError: If inputs is not a dict, missing "text",
                or "text" is not a string.
        """
        if not self._is_setup:
            raise ComponentLifecycleError(
                "ExampleComponent must be configured via setup() before calling run()."
            )

        if not isinstance(inputs, dict):
            raise ComponentExecutionError("Inputs must be a dictionary.")

        if "text" not in inputs:
            raise ComponentExecutionError("Missing required input key: 'text'.")

        text = inputs["text"]
        if not isinstance(text, str):
            raise ComponentExecutionError(
                f"Input 'text' must be a string, got {type(text).__name__}."
            )

        if not isinstance(context, dict):
            raise ComponentExecutionError("Context must be a dictionary.")

        # Apply deterministic transformation
        if self._mode == "uppercase":
            transformed = text.upper()
        elif self._mode == "lowercase":
            transformed = text.lower()
        elif self._mode == "reverse":
            transformed = text[::-1]
        else:  # pragma: no cover - defensive branch
            raise ComponentExecutionError(f"Unexpected mode: {self._mode}")

        result_text = f"{self._prefix}{transformed}"

        return {
            "result": result_text,
            "length": len(result_text),
            "mode": self._mode,
            "execution_id": context.get("execution_id"),
        }

    def teardown(self) -> None:
        """Reset internal component state and release resources.

        This method is idempotent and safe to call multiple times.
        """
        self._is_setup = False
        self._mode = "uppercase"
        self._prefix = ""
