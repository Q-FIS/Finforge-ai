"""Integration tests for end-to-end FinForge AI pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from finforge.component import BaseComponent
from finforge.manifest.models import ComponentManifest, ConfigDefinition, PortDefinition
from finforge.pipeline.builder import Pipeline
from finforge.registry import ComponentRegistry
from finforge.runtime.models import ExecutionStatus


class DataIngestComponent(BaseComponent):
    """Generates synthetic financial data records."""

    def __init__(self) -> None:
        self._batch_size: int = 10

    def setup(self, config: dict[str, Any]) -> None:
        self._batch_size = config.get("batch_size", 10)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        records = [
            {"id": f"tx_{i}", "amount": float(i * 1000), "category": "retail"}
            for i in range(1, self._batch_size + 1)
        ]
        return {"records": records}


class RiskFilterComponent(BaseComponent):
    """Filters records above a dollar threshold."""

    def __init__(self) -> None:
        self._threshold: float = 5000.0

    def setup(self, config: dict[str, Any]) -> None:
        self._threshold = float(config.get("threshold", 5000.0))

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        records = inputs["records"]
        flagged = [r for r in records if r["amount"] >= self._threshold]
        normal = [r for r in records if r["amount"] < self._threshold]
        return {"flagged": flagged, "normal": normal}


class SummaryReportComponent(BaseComponent):
    """Aggregates flagged records into summary telemetry."""

    def __init__(self) -> None:
        self._prefix: str = "FLAGGED"

    def setup(self, config: dict[str, Any]) -> None:
        self._prefix = config.get("prefix", "FLAGGED")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        flagged = inputs["flagged"]
        total_risk_exposure = sum(r["amount"] for r in flagged)
        return {
            "summary": {
                "count": len(flagged),
                "total_exposure": total_risk_exposure,
                "status": f"{self._prefix}_{len(flagged)}",
            }
        }


@pytest.fixture
def test_registry() -> ComponentRegistry:
    """Fixture providing a registry populated with three test components."""
    registry = ComponentRegistry()

    m1 = ComponentManifest(
        name="data-ingest",
        version="0.1.0",
        description="Ingests financial data",
        api_version="1",
        category="data-processing",
        entrypoint="test:DataIngestComponent",
        outputs={"records": PortDefinition(type="array", description="Data records")},
        config={"batch_size": ConfigDefinition(type="integer", default=10)},
    )
    m2 = ComponentManifest(
        name="risk-filter",
        version="0.1.0",
        description="Filters risky records",
        api_version="1",
        category="data-processing",
        entrypoint="test:RiskFilterComponent",
        inputs={
            "records": PortDefinition(type="array", description="Records to filter")
        },
        outputs={
            "flagged": PortDefinition(type="array", description="Flagged records"),
            "normal": PortDefinition(type="array", description="Normal records"),
        },
        config={"threshold": ConfigDefinition(type="float", default=5000.0)},
    )
    m3 = ComponentManifest(
        name="summary-report",
        version="0.1.0",
        description="Summarizes risk",
        api_version="1",
        category="evaluation",
        entrypoint="test:SummaryReportComponent",
        inputs={
            "flagged": PortDefinition(type="array", description="Flagged records")
        },
        outputs={
            "summary": PortDefinition(type="object", description="Summary metrics")
        },
        config={"prefix": ConfigDefinition(type="string", default="FLAGGED")},
    )

    registry.register(DataIngestComponent, m1)
    registry.register(RiskFilterComponent, m2)
    registry.register(SummaryReportComponent, m3)
    return registry


def test_end_to_end_pipeline_execution(test_registry: ComponentRegistry) -> None:
    """Validate full pipeline build, execution, and outputs."""
    pipe = Pipeline(name="risk-audit-flow", registry=test_registry)
    pipe.add("ingest", "data-ingest", config={"batch_size": 8})
    pipe.add("filter", "risk-filter", config={"threshold": 4000.0})
    pipe.add("report", "summary-report", config={"prefix": "AUDIT"})

    pipe.connect("ingest", "records", "filter", "records")
    pipe.connect("filter", "flagged", "report", "flagged")

    pipe.validate()
    order = pipe.execution_order()
    assert order == ["ingest", "filter", "report"]

    result = pipe.run()
    assert result.success is True
    assert result.status == ExecutionStatus.SUCCEEDED
    assert len(result.node_results) == 3

    # Check node outputs
    ingest_out = result.get_output("ingest", "records")
    assert len(ingest_out) == 8

    flagged_out = result.get_output("filter", "flagged")
    # amounts are 1000..8000; flagged >= 4000 yields 5 items
    assert len(flagged_out) == 5

    report_out = result.get_output("report", "summary")
    assert report_out["count"] == 5
    assert report_out["total_exposure"] == 30000.0
    assert report_out["status"] == "AUDIT_5"


def test_pipeline_serialization_and_reexecution(
    test_registry: ComponentRegistry,
    tmp_path: Path,
) -> None:
    """Validate pipeline save to YAML, reload with registry, and execution."""
    pipe = Pipeline(name="serializable-flow", registry=test_registry)
    pipe.add("ingest", "data-ingest", config={"batch_size": 4})
    pipe.add("filter", "risk-filter", config={"threshold": 2500.0})
    pipe.connect("ingest", "records", "filter", "records")

    yaml_file = tmp_path / "saved_pipeline.yaml"
    pipe.save(yaml_file)
    assert yaml_file.is_file()

    # Load back
    loaded_pipe = Pipeline.load(yaml_file, registry=test_registry)
    loaded_pipe.validate()
    assert loaded_pipe.name == "serializable-flow"
    assert loaded_pipe.execution_order() == ["ingest", "filter"]

    res = loaded_pipe.run()
    assert res.success is True
    assert len(res.get_output("filter", "flagged")) == 2
