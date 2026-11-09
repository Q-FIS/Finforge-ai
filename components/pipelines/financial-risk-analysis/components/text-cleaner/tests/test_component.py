"""Unit tests for TextCleanerComponent."""

import pytest
from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

from text_cleaner.component import TextCleanerComponent


def test_component_inheritance() -> None:
    """Verify component inherits from BaseComponent."""
    component = TextCleanerComponent()
    assert isinstance(component, BaseComponent)


def test_component_lifecycle_execution() -> None:
    """Verify setup, run, and teardown lifecycle with custom inputs."""
    component = TextCleanerComponent()

    # run() before setup() raises ComponentLifecycleError
    with pytest.raises(ComponentLifecycleError):
        component.run({"texts": ["Hello World"]}, context={})

    # setup() with valid configuration
    component.setup({"lowercase": True, "strip_html": True, "remove_disclaimers": True})

    # run() cleans HTML tags, normalizes whitespace, and lowercases
    sample = ["  <p>Q3 Revenue <b>Grew</b>   15%.</p> &amp; profit expanded.  "]
    output = component.run({"texts": sample}, context={"run_id": "test-1"})
    assert "cleaned_texts" in output
    assert len(output["cleaned_texts"]) == 1
    assert output["cleaned_texts"][0] == "q3 revenue grew 15%. profit expanded."

    # teardown() cleans up state safely
    component.teardown()


def test_default_sample_texts_when_no_input() -> None:
    """Verify default texts are provided when texts input is omitted."""
    component = TextCleanerComponent()
    component.setup({})
    output = component.run({}, context={})
    assert "cleaned_texts" in output
    assert len(output["cleaned_texts"]) >= 3
    component.teardown()


def test_invalid_configuration_rejected() -> None:
    """Verify invalid setup parameters raise ComponentConfigurationError."""
    component = TextCleanerComponent()
    with pytest.raises(ComponentConfigurationError):
        component.setup({"lowercase": "not-a-bool"})


def test_invalid_input_rejected() -> None:
    """Verify invalid input types raise ComponentExecutionError."""
    component = TextCleanerComponent()
    component.setup({})

    with pytest.raises(ComponentExecutionError):
        component.run({"texts": "not-a-list"}, context={})

    with pytest.raises(ComponentExecutionError):
        component.run({"texts": [123, 456]}, context={})
