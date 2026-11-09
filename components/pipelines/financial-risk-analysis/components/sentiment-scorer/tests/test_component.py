"""Unit tests for SentimentScorerComponent."""

import pytest
from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

from sentiment_scorer.component import SentimentScorerComponent


def test_component_inheritance() -> None:
    """Verify component inherits from BaseComponent."""
    component = SentimentScorerComponent()
    assert isinstance(component, BaseComponent)


def test_component_lifecycle_execution() -> None:
    """Verify setup, run, and teardown lifecycle."""
    component = SentimentScorerComponent()

    # run() before setup() raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run({"texts": ["Positive record earnings."]}, context={})

    # setup() with valid configuration
    component.setup({"sentiment_threshold": 0.1, "confidence_scaling": 1.0})

    sample_texts = [
        "Company reported record profit and robust revenue growth.",
        "Severe debt default, bankruptcy risk, and covenant breach observed.",
        "The board will hold its annual regular shareholder meeting next month.",
    ]

    output = component.run({"texts": sample_texts}, context={"run_id": "test-1"})
    assert "sentiment_results" in output
    assert "sentiment_summary" in output

    results = output["sentiment_results"]
    assert len(results) == 3
    assert results[0]["sentiment_label"] == "POSITIVE"
    assert results[1]["sentiment_label"] == "NEGATIVE"
    assert results[2]["sentiment_label"] == "NEUTRAL"

    summary = output["sentiment_summary"]
    assert summary["total_items"] == 3
    assert summary["positive_count"] == 1
    assert summary["negative_count"] == 1
    assert summary["neutral_count"] == 1

    # teardown() cleans up state safely
    component.teardown()


def test_invalid_configuration_rejected() -> None:
    """Verify invalid setup parameters raise ComponentConfigurationError."""
    component = SentimentScorerComponent()
    with pytest.raises(ComponentConfigurationError):
        component.setup({"sentiment_threshold": "not-a-number"})


def test_invalid_input_rejected() -> None:
    """Verify missing or invalid inputs raise ComponentExecutionError."""
    component = SentimentScorerComponent()
    component.setup({})

    # Missing input port
    with pytest.raises(ComponentExecutionError):
        component.run({}, context={})

    # Invalid input type
    with pytest.raises(ComponentExecutionError):
        component.run({"texts": "not-a-list"}, context={})

    # Non-string element in list
    with pytest.raises(ComponentExecutionError):
        component.run({"texts": [123]}, context={})
