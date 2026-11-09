"""Risk Calculator Component implementation."""

from __future__ import annotations

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


class RiskCalculatorComponent(BaseComponent):
    """Calculates risk level based on transaction amount."""

    def __init__(self) -> None:
        self._is_ready: bool = False
        self._threshold: float = 10000.0

    def setup(self, config: dict[str, Any]) -> None:
        """Stage 1: Load and validate settings before execution."""
        threshold = config.get("threshold", 10000.0)

        # Validate that threshold is a numeric value
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ComponentConfigurationError("Threshold must be a numeric value.")

        self._threshold = float(threshold)
        self._is_ready = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Stage 2: Process the inputs and return outputs."""
        if not self._is_ready:
            raise ComponentLifecycleError("Call setup() before run().")

        if "amount" not in inputs:
            raise ComponentExecutionError("Missing required input: 'amount'.")

        amount = inputs["amount"]
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ComponentExecutionError("Input 'amount' must be a numeric value.")

        risk_level = "HIGH" if amount >= self._threshold else "LOW"

        return {"risk_level": risk_level}

    def teardown(self) -> None:
        """Stage 3: Clean up any resources."""
        self._is_ready = False
