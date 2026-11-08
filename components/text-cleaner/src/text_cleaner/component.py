"""Implementation of TextCleanerComponent."""

from __future__ import annotations

import re
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


class TextCleanerComponent(BaseComponent):
    """Cleans text by normalizing whitespace and optionally lowercasing."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._lowercase: bool = False

    def setup(self, config: dict[str, Any]) -> None:
        """Configure the text cleaner."""
        lowercase = config.get("lowercase", False)

        if not isinstance(lowercase, bool):
            raise ComponentConfigurationError("'lowercase' must be a boolean.")

        self._lowercase = lowercase
        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Clean the provided text."""

        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )

        if "input_data" not in inputs:
            raise ComponentExecutionError("Missing required input port: 'input_data'.")

        raw_text = inputs["input_data"]

        if not isinstance(raw_text, str):
            raise ComponentExecutionError(
                f"Expected string input, got {type(raw_text).__name__}."
            )

        try:
            # Replace multiple whitespace characters with one space.
            cleaned = re.sub(r"\s+", " ", raw_text)

            # Remove leading and trailing whitespace.
            cleaned = cleaned.strip()

            # Optionally convert text to lowercase.
            if self._lowercase:
                cleaned = cleaned.lower()

            return {"output_data": cleaned}

        except Exception as err:
            raise ComponentExecutionError(f"Text cleaning failed: {err}") from err

    def teardown(self) -> None:
        """Reset component state."""
        self._is_configured = False
        self._lowercase = False
