"""Implementation of HelloComponent."""

from __future__ import annotations

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


class HelloComponent(BaseComponent):
    """A scratch-first hello component for FinForge AI."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._scale_factor: float = 1.0

    def setup(self, config: dict[str, Any]) -> None:
        """Configure the component before execution.

        Args:
            config: Configuration dictionary matching component.yaml config schema.

        Raises:
            ComponentConfigurationError: If configuration values are invalid.
        """
        raw_scale = config.get("scale_factor", 1.0)
        if not isinstance(raw_scale, (int, float)):
            raise ComponentConfigurationError(
                f"Invalid 'scale_factor': expected numeric, got {type(raw_scale).__name__}"
            )
        self._scale_factor = float(raw_scale)
        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the component logic on the provided inputs.

        Args:
            inputs: Input dictionary containing 'input_data'.
            context: Runtime execution context metadata.

        Returns:
            Output dictionary containing 'output_data'.

        Raises:
            ComponentLifecycleError: If called before setup().
            ComponentExecutionError: If inputs are invalid or processing fails.
        """
        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )

        if "input_data" not in inputs:
            raise ComponentExecutionError("Missing required input port: 'input_data'.")

        raw_data = inputs["input_data"]
        if not isinstance(raw_data, list):
            raise ComponentExecutionError(
                f"Expected 'input_data' to be a list, got {type(raw_data).__name__}."
            )

        # ------------------------------------------------------------------
        # TODO: Implement your custom algorithm or data processing logic here.
        # This default implementation demonstrates simple deterministic behavior.
        # ------------------------------------------------------------------
        try:
            processed = [float(x) * self._scale_factor for x in raw_data]
        except (TypeError, ValueError) as err:
            raise ComponentExecutionError(
                f"Failed to process input data: {err}"
            ) from err

        return {"output_data": processed}

    def teardown(self) -> None:
        """Clean up acquired resources. Safe and idempotent to call."""
        self._is_configured = False
