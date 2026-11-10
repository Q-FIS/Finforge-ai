"""Unit and integration tests for custom-kmeans scratch component."""

from __future__ import annotations

import pytest

from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)
from my_kmeans.component import KMeansComponent


def test_kmeans_lifecycle() -> None:
    comp = KMeansComponent()
    assert not comp._is_configured

    # Cannot run before setup
    with pytest.raises(ComponentLifecycleError):
        comp.run({"data": [[1.0, 2.0]]}, {})

    comp.setup({"n_clusters": 2, "max_iter": 50, "tol": 0.001})
    assert comp._is_configured

    result = comp.run(
        {
            "data": [
                [0.0, 0.0],
                [0.1, 0.1],
                [10.0, 10.0],
                [10.1, 10.1],
            ]
        },
        {},
    )
    assert "labels" in result
    assert "centroids" in result
    assert len(result["labels"]) == 4
    # Points 0 and 1 should share a cluster; points 2 and 3 should share another
    assert result["labels"][0] == result["labels"][1]
    assert result["labels"][2] == result["labels"][3]
    assert result["labels"][0] != result["labels"][2]
    assert len(result["centroids"]) == 2

    comp.teardown()
    assert not comp._is_configured


def test_invalid_config() -> None:
    comp = KMeansComponent()
    with pytest.raises(ComponentConfigurationError):
        comp.setup({"n_clusters": 0})

    with pytest.raises(ComponentConfigurationError):
        comp.setup({"n_clusters": -1})

    with pytest.raises(ComponentConfigurationError):
        comp.setup({"max_iter": "bad"})

    with pytest.raises(ComponentConfigurationError):
        comp.setup({"tol": -0.5})


def test_invalid_inputs() -> None:
    comp = KMeansComponent()
    comp.setup({})

    with pytest.raises(ComponentExecutionError):
        comp.run({}, {})

    with pytest.raises(ComponentExecutionError):
        comp.run({"data": "not a list"}, {})

    with pytest.raises(ComponentExecutionError):
        comp.run({"data": [[1.0, 2.0], [1.0]]}, {})  # Inconsistent dimensions


def test_empty_dataset() -> None:
    comp = KMeansComponent()
    comp.setup({})
    res = comp.run({"data": []}, {})
    assert res == {"labels": [], "centroids": []}
