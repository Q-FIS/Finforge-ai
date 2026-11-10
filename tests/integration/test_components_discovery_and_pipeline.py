"""Integration tests for discovered workspace components and composite pipelines."""

from __future__ import annotations

from pathlib import Path

from finforge.pipeline.builder import Pipeline
from finforge.registry import ComponentRegistry
from finforge.runtime.models import ExecutionStatus
from finforge.testing.runner import run_component_tests


def test_discover_workspace_components() -> None:
    """Verify registry.discover finds all workspace components without errors."""
    registry = ComponentRegistry()
    registry.discover(search_paths=[Path("components")])

    expected_components = [
        "hello",
        "text-cleaner",
        "risk-calculator",
        "risk_management",
        "tfidf-vectorizer",
        "custom-kmeans",
        "risk-tagger",
        "sentiment-scorer",
    ]
    for name in expected_components:
        assert name in registry, f"Expected component '{name}' to be discovered."


def test_all_components_pass_framework_validation() -> None:
    """Run framework validation on all discovered components."""
    comp_dirs = [
        Path("components/hello"),
        Path("components/text-cleaner"),
        Path("components/risk-calculator"),
        Path("components/risk-management"),
        Path("components/tfidf-vectorizer"),
        Path("components/examples/custom_kmeans"),
        Path("components/pipelines/financial-risk-analysis/components/risk-tagger"),
        Path("components/pipelines/financial-risk-analysis/components/sentiment-scorer"),
        Path("components/pipelines/financial-risk-analysis/components/text-cleaner"),
    ]

    for cdir in comp_dirs:
        assert cdir.is_dir(), f"Directory not found: {cdir}"
        result = run_component_tests(cdir)
        assert result.is_success is True, (
            f"Component in '{cdir}' failed validation: {result.all_errors}"
        )


def test_composite_kmeans_clustering_pipeline() -> None:
    """Verify building and running pipeline with discovered custom-kmeans."""
    registry = ComponentRegistry()
    registry.discover(search_paths=[Path("components/examples/custom_kmeans")])

    pipe = Pipeline(name="kmeans-test-pipeline", registry=registry)
    pipe.add("clusterer", "custom-kmeans", config={"n_clusters": 2, "max_iter": 100})

    pipe.validate()
    res = pipe.run(
        inputs={
            "clusterer": {
                "data": [
                    [1.0, 1.0],
                    [1.2, 0.9],
                    [9.0, 9.0],
                    [9.1, 8.8],
                ]
            }
        }
    )

    assert res.success is True
    assert res.status == ExecutionStatus.SUCCEEDED
    labels = res.get_output("clusterer", "labels")
    centroids = res.get_output("clusterer", "centroids")
    assert len(labels) == 4
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]
    assert len(centroids) == 2


def test_financial_risk_analysis_pipeline_run() -> None:
    """Verify loading and executing financial-risk-analysis pipeline end-to-end."""
    pipe_file = Path("components/pipelines/financial-risk-analysis/pipeline.yaml")
    assert pipe_file.is_file()

    registry = ComponentRegistry()
    registry.discover(
        search_paths=[
            Path("components/pipelines/financial-risk-analysis/components"),
            Path("components"),
        ]
    )

    pipeline = Pipeline.load(pipe_file, registry=registry)
    pipeline.validate()
    assert pipeline.execution_order() == [
        "text_cleaner",
        "sentiment_scorer",
        "risk_tagger",
    ]

    res = pipeline.run()
    assert res.success is True
    assert res.status == ExecutionStatus.SUCCEEDED
    assert "cleaned_texts" in res.get_output("text_cleaner")
    assert "sentiment_results" in res.get_output("sentiment_scorer")
    assert "risk_assessment" in res.get_output("risk_tagger")
