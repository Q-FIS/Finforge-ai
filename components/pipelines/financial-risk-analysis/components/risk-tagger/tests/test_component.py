"""Unit tests for RiskTaggerComponent."""

import pytest
from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

from risk_tagger.component import RiskTaggerComponent


def test_component_inheritance() -> None:
    """Verify component inherits from BaseComponent."""
    component = RiskTaggerComponent()
    assert isinstance(component, BaseComponent)


def test_component_lifecycle_execution() -> None:
    """Verify setup, run, and teardown lifecycle."""
    component = RiskTaggerComponent()

    # run() before setup() raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run({"sentiment_results": []}, context={})

    # setup() with valid configuration
    component.setup({"risk_threshold": 50.0, "strict_mode": False})

    sample_results = [
        {
            "text": "Credit rating downgraded to B- amid severe liquidity constraints and debt covenant breach.",
            "compound_score": -0.8,
            "uncertainty_score": 0.4,
        },
        {
            "text": "Quarterly revenue surged by 28% YoY with record profit margins.",
            "compound_score": 0.8,
            "uncertainty_score": 0.0,
        },
    ]

    output = component.run({"sentiment_results": sample_results}, context={"run_id": "test-1"})
    assert "tagged_items" in output
    assert "risk_assessment" in output

    items = output["tagged_items"]
    assert len(items) == 2
    assert "Credit Risk" in items[0]["categories"]
    assert items[0]["risk_score"] > items[1]["risk_score"]

    assessment = output["risk_assessment"]
    assert "composite_risk_score" in assessment
    assert "risk_level" in assessment
    assert assessment["total_evaluated_items"] == 2
    assert len(assessment["recommended_actions"]) > 0

    # teardown() cleans up state safely
    component.teardown()


def test_invalid_configuration_rejected() -> None:
    """Verify invalid setup parameters raise ComponentConfigurationError."""
    component = RiskTaggerComponent()
    with pytest.raises(ComponentConfigurationError):
        component.setup({"risk_threshold": "invalid"})

    with pytest.raises(ComponentConfigurationError):
        component.setup({"strict_mode": "not-a-bool"})


def test_invalid_input_rejected() -> None:
    """Verify missing or invalid inputs raise ComponentExecutionError."""
    component = RiskTaggerComponent()
    component.setup({})

    # Missing input port
    with pytest.raises(ComponentExecutionError):
        component.run({}, context={})

    # Invalid input type
    with pytest.raises(ComponentExecutionError):
        component.run({"sentiment_results": "not-a-list"}, context={})

    # Invalid item in list
    with pytest.raises(ComponentExecutionError):
        component.run({"sentiment_results": ["not-a-dict"]}, context={})
