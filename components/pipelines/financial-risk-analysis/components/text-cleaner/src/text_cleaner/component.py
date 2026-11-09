"""Implementation of TextCleanerComponent for financial text processing."""

from __future__ import annotations

import re
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

DEFAULT_FINANCIAL_TEXTS = [
    (
        "Quarterly revenue surged by 28% YoY to $4.2B, driven by robust cloud adoption "
        "and record enterprise net margins."
    ),
    (
        "Credit rating downgraded to B- amid severe liquidity constraints, debt covenants breach, "
        "and looming bond maturity wall."
    ),
    (
        "The firm received an SEC subpoena initiating an enforcement investigation regarding "
        "consumer compliance practices and internal accounting controls."
    ),
    (
        "Supply chain disruptions and persistent inflationary labor headwinds may temper operating margins "
        "across European manufacturing divisions."
    ),
    (
        "Aggressive central bank rate hikes and severe yield curve inversion trigger heightened "
        "equity volatility and market asset repricing."
    ),
]


class TextCleanerComponent(BaseComponent):
    """Cleans and normalizes financial news, reports, and regulatory filings."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._lowercase: bool = False
        self._strip_html: bool = True
        self._remove_disclaimers: bool = True

    def setup(self, config: dict[str, Any]) -> None:
        """Configure text cleaning parameters.

        Args:
            config: Configuration dictionary matching component.yaml config schema.

        Raises:
            ComponentConfigurationError: If any config parameter is invalid.
        """
        lowercase = config.get("lowercase", False)
        if not isinstance(lowercase, bool):
            raise ComponentConfigurationError(
                f"Invalid 'lowercase': expected boolean, got {type(lowercase).__name__}"
            )
        self._lowercase = lowercase

        strip_html = config.get("strip_html", True)
        if not isinstance(strip_html, bool):
            raise ComponentConfigurationError(
                f"Invalid 'strip_html': expected boolean, got {type(strip_html).__name__}"
            )
        self._strip_html = strip_html

        remove_disclaimers = config.get("remove_disclaimers", True)
        if not isinstance(remove_disclaimers, bool):
            raise ComponentConfigurationError(
                f"Invalid 'remove_disclaimers': expected boolean, got {type(remove_disclaimers).__name__}"
            )
        self._remove_disclaimers = remove_disclaimers

        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize raw financial texts.

        Args:
            inputs: Input dictionary optionally containing 'texts'.
            context: Runtime execution context metadata.

        Returns:
            Dictionary containing 'cleaned_texts'.

        Raises:
            ComponentLifecycleError: If called before setup().
            ComponentExecutionError: If inputs are invalid or cleaning fails.
        """
        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )

        raw_texts = inputs.get("texts")
        if raw_texts is None:
            raw_texts = list(DEFAULT_FINANCIAL_TEXTS)

        if not isinstance(raw_texts, list):
            raise ComponentExecutionError(
                f"Expected 'texts' to be a list, got {type(raw_texts).__name__}."
            )

        cleaned_list: list[str] = []
        for idx, item in enumerate(raw_texts):
            if not isinstance(item, str):
                raise ComponentExecutionError(
                    f"Item at index {idx} in 'texts' must be a string, got {type(item).__name__}."
                )

            text = item

            # Strip HTML tags
            if self._strip_html:
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)

            # Strip boilerplate legal disclaimers if present
            if self._remove_disclaimers:
                text = re.sub(
                    r"(?i)\bthis (press release|document|filing) contains forward-looking statements.*",
                    "",
                    text,
                )

            # Normalize whitespace and punctuation spacing
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"\s+([.,;:!?])", r"\1", text)

            if self._lowercase:
                text = text.lower()

            if text:
                cleaned_list.append(text)

        return {"cleaned_texts": cleaned_list}

    def teardown(self) -> None:
        """Clean up component state."""
        self._is_configured = False
