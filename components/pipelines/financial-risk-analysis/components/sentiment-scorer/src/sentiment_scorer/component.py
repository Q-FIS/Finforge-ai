"""Implementation of SentimentScorerComponent for financial domain text."""

from __future__ import annotations

import re
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

POSITIVE_TERMS: frozenset[str] = frozenset(
    {
        "surge",
        "surged",
        "surges",
        "gain",
        "gained",
        "gains",
        "profit",
        "profitable",
        "profitability",
        "growth",
        "grew",
        "outperform",
        "outperformed",
        "dividend",
        "dividends",
        "expansion",
        "expanded",
        "beat",
        "beats",
        "strong",
        "record",
        "exceed",
        "exceeded",
        "bullish",
        "upside",
        "tailwind",
        "tailwinds",
        "recovery",
        "robust",
        "rebound",
        "rally",
    }
)

NEGATIVE_TERMS: frozenset[str] = frozenset(
    {
        "loss",
        "losses",
        "decline",
        "declined",
        "declines",
        "default",
        "defaulted",
        "defaults",
        "bankruptcy",
        "downturn",
        "impairment",
        "litigation",
        "slump",
        "deficit",
        "downgrade",
        "downgraded",
        "downgrades",
        "insolvency",
        "insolvent",
        "layoffs",
        "headwind",
        "headwinds",
        "breach",
        "breaches",
        "covenant",
        "restructuring",
        "penalty",
        "penalties",
        "fraud",
        "bearish",
        "subpoena",
    }
)

UNCERTAINTY_TERMS: frozenset[str] = frozenset(
    {
        "uncertain",
        "uncertainty",
        "volatility",
        "volatile",
        "unforeseen",
        "fluctuate",
        "fluctuations",
        "pending",
        "speculative",
        "contingent",
        "investigation",
        "investigations",
        "cautious",
        "risk",
        "risks",
    }
)


class SentimentScorerComponent(BaseComponent):
    """Financial sentiment scoring using financial domain lexicon analysis."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._sentiment_threshold: float = 0.1
        self._confidence_scaling: float = 1.0

    def setup(self, config: dict[str, Any]) -> None:
        """Configure financial sentiment scoring thresholds.

        Args:
            config: Configuration dictionary matching component.yaml config schema.

        Raises:
            ComponentConfigurationError: If configuration values are invalid.
        """
        raw_threshold = config.get("sentiment_threshold", 0.1)
        if not isinstance(raw_threshold, (int, float)):
            raise ComponentConfigurationError(
                f"Invalid 'sentiment_threshold': expected numeric, got {type(raw_threshold).__name__}"
            )
        self._sentiment_threshold = float(raw_threshold)

        raw_scaling = config.get("confidence_scaling", 1.0)
        if not isinstance(raw_scaling, (int, float)):
            raise ComponentConfigurationError(
                f"Invalid 'confidence_scaling': expected numeric, got {type(raw_scaling).__name__}"
            )
        self._confidence_scaling = float(raw_scaling)

        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute financial sentiment metrics on input texts.

        Args:
            inputs: Dictionary containing 'texts' (list of strings).
            context: Runtime execution context metadata.

        Returns:
            Dictionary containing 'sentiment_results' and 'sentiment_summary'.

        Raises:
            ComponentLifecycleError: If called before setup().
            ComponentExecutionError: If inputs are invalid or processing fails.
        """
        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )

        if "texts" not in inputs:
            raise ComponentExecutionError("Missing required input port: 'texts'.")

        texts = inputs["texts"]
        if not isinstance(texts, list):
            raise ComponentExecutionError(
                f"Expected 'texts' to be a list, got {type(texts).__name__}."
            )

        results: list[dict[str, Any]] = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        compound_sum = 0.0

        for idx, item in enumerate(texts):
            if not isinstance(item, str):
                raise ComponentExecutionError(
                    f"Item at index {idx} in 'texts' must be a string, got {type(item).__name__}."
                )

            tokens = re.findall(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)*\b", item.lower())
            token_count = max(len(tokens), 1)

            pos_hits = sum(1 for token in tokens if token in POSITIVE_TERMS)
            neg_hits = sum(1 for token in tokens if token in NEGATIVE_TERMS)
            unc_hits = sum(1 for token in tokens if token in UNCERTAINTY_TERMS)

            total_hits = pos_hits + neg_hits
            if total_hits > 0:
                compound = (pos_hits - neg_hits) / total_hits
            else:
                compound = 0.0

            pos_score = min(pos_hits / token_count, 1.0)
            neg_score = min(neg_hits / token_count, 1.0)
            unc_score = min(unc_hits / token_count, 1.0)

            if compound > self._sentiment_threshold:
                label = "POSITIVE"
                positive_count += 1
            elif compound < -self._sentiment_threshold:
                label = "NEGATIVE"
                negative_count += 1
            else:
                label = "NEUTRAL"
                neutral_count += 1

            compound_sum += compound

            results.append(
                {
                    "text": item,
                    "compound_score": round(float(compound), 4),
                    "sentiment_label": label,
                    "positive_score": round(float(pos_score), 4),
                    "negative_score": round(float(neg_score), 4),
                    "uncertainty_score": round(float(unc_score), 4),
                }
            )

        num_texts = len(texts)
        mean_compound = compound_sum / max(num_texts, 1)

        if mean_compound > self._sentiment_threshold:
            overall_sentiment = "BULLISH"
        elif mean_compound < -self._sentiment_threshold:
            overall_sentiment = "BEARISH"
        else:
            overall_sentiment = "NEUTRAL"

        summary = {
            "total_items": num_texts,
            "mean_compound_score": round(float(mean_compound), 4),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "overall_sentiment": overall_sentiment,
        }

        return {
            "sentiment_results": results,
            "sentiment_summary": summary,
        }

    def teardown(self) -> None:
        """Clean up component state."""
        self._is_configured = False
