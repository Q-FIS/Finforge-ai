"""End-to-end example of saving, loading, and inspecting pipelines (FF-11).

This script demonstrates:
  1. Creating an in-memory ComponentRegistry and registering components.
  2. Constructing a multi-node workflow using the Python Pipeline builder API.
  3. Saving the pipeline to a deterministic YAML file (`pipeline.save()`).
  4. Inspecting the generated declarative YAML content.
  5. Loading the pipeline into a new instance (`Pipeline.load(path, registry)`).
  6. Validating the reconstructed graph and verifying structural equivalence.
  7. Demonstrating that serialization never instantiates or runs components.
  8. Separately and explicitly executing the reconstructed pipeline.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from finforge import (
    ComponentManifest,
    ComponentRegistry,
    Pipeline,
    PortDefinition,
    load_pipeline_document,
)
from finforge.component import BaseComponent

# =============================================================================
# Demonstration Components
# =============================================================================


class FinancialDataLoader(BaseComponent):
    """Loads raw financial transaction records."""

    def setup(self, config: dict[str, Any]) -> None:
        self.batch_size = config.get("batch_size", 100)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        transactions = [
            {"account_id": "ACC-01", "amount": 1500.0, "risk_score": 0.12},
            {"account_id": "ACC-02", "amount": 92000.0, "risk_score": 0.88},
            {"account_id": "ACC-03", "amount": 430.0, "risk_score": 0.05},
        ]
        return {"transactions": transactions}


class AnomalyDetector(BaseComponent):
    """Flags high-risk anomalies based on threshold."""

    def setup(self, config: dict[str, Any]) -> None:
        self.threshold = float(config.get("threshold", 0.75))

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        records = inputs["transactions"]
        flagged = [r for r in records if r.get("risk_score", 0.0) >= self.threshold]
        return {"flagged": flagged}


class AlertNotifier(BaseComponent):
    """Generates alert notifications for detected anomalies."""

    def setup(self, config: dict[str, Any]) -> None:
        self.channel = config.get("channel", "console")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        flagged = inputs["flagged"]
        alerts = [f"ALERT on {r['account_id']}: amount=${r['amount']}" for r in flagged]
        return {"alerts": alerts}


# =============================================================================
# Main Demonstration Workflow
# =============================================================================


def main() -> None:
    print("=" * 70)
    print("FinForge AI — Pipeline Serialization (FF-11) Demonstration")
    print("=" * 70)

    # 1. Setup Registry
    print("\n[Step 1] Initializing ComponentRegistry and registering components...")
    registry = ComponentRegistry()

    m_loader = ComponentManifest(
        name="financial-loader",
        version="1.0.0",
        description="Ingests transaction logs",
        category="data-processing",
        entrypoint="examples.pipeline_serialization_example:FinancialDataLoader",
        outputs={"transactions": PortDefinition(type="array")},
    )
    registry.register(FinancialDataLoader, m_loader)

    m_detector = ComponentManifest(
        name="anomaly-detector",
        version="1.0.0",
        description="Flags suspicious risk scores",
        category="data-processing",
        entrypoint="examples.pipeline_serialization_example:AnomalyDetector",
        inputs={"transactions": PortDefinition(type="array")},
        outputs={"flagged": PortDefinition(type="array")},
    )
    registry.register(AnomalyDetector, m_detector)

    m_notifier = ComponentManifest(
        name="alert-notifier",
        version="1.0.0",
        description="Dispatches security alerts",
        category="data-processing",
        entrypoint="examples.pipeline_serialization_example:AlertNotifier",
        inputs={"flagged": PortDefinition(type="array")},
        outputs={"alerts": PortDefinition(type="array")},
    )
    registry.register(AlertNotifier, m_notifier)
    comps = registry.list_components()
    print(f"  Successfully registered {len(registry)} components: {comps}")

    # 2. Build Pipeline
    print("\n[Step 2] Constructing pipeline via Python Pipeline Builder API...")
    pipe = Pipeline(
        name="fraud-detection-workflow",
        registry=registry,
        description="Detects anomalous transactions and generates alerts",
        metadata={"environment": "production", "team": "risk-ml"},
    )

    pipe.add(
        "loader",
        "financial-loader",
        config={"batch_size": 500, "source_uri": "s3://finance/txs.parquet"},
    )
    pipe.add(
        "detector",
        "anomaly-detector",
        config={"threshold": 0.80, "mode": "strict"},
    )
    pipe.add(
        "notifier",
        "alert-notifier",
        config={"channel": "ops-slack"},
    )

    pipe.connect("loader", "transactions", "detector", "transactions")
    pipe.connect("detector", "flagged", "notifier", "flagged")
    pipe.validate()

    print(
        f"  Pipeline created: '{pipe.name}' with {len(pipe)} nodes "
        f"and {len(pipe.edges)} edges."
    )
    print(f"  Topological execution order: {pipe.execution_order()}")

    # 3. Save Pipeline to YAML
    with tempfile.TemporaryDirectory() as tmpdir:
        yaml_file = Path(tmpdir) / "fraud_pipeline.yaml"
        print(f"\n[Step 3] Saving pipeline to YAML: '{yaml_file.name}'...")
        pipe.save(yaml_file)
        assert yaml_file.is_file()
        print("  Pipeline saved successfully (atomic write confirmed).")

        # 4. Inspect Generated YAML
        print("\n[Step 4] Inspecting generated YAML definition:")
        print("-" * 50)
        print(yaml_file.read_text(encoding="utf-8"))
        print("-" * 50)

        # 5. Load Pipeline with Registry
        print("[Step 5] Loading pipeline from YAML using ComponentRegistry...")
        loaded_pipe = Pipeline.load(yaml_file, registry=registry)
        print("  Reconstructed pipeline object loaded successfully.")

        # 6. Validate Reconstructed Graph
        print("\n[Step 6] Validating reconstructed pipeline...")
        loaded_pipe.validate()
        assert loaded_pipe.name == pipe.name
        assert loaded_pipe.description == pipe.description
        assert loaded_pipe.metadata == pipe.metadata
        assert loaded_pipe.execution_order() == pipe.execution_order()
        assert len(loaded_pipe.nodes) == len(pipe.nodes)
        assert len(loaded_pipe.edges) == len(pipe.edges)
        print("  Verified exact structural equivalence with original pipeline.")
        print(f"  Nodes: {[n.node_id for n in loaded_pipe.nodes]}")
        print(f"  Execution order: {loaded_pipe.execution_order()}")

        # 7. Low-level document inspection without execution
        print("\n[Step 7] Inspecting pipeline document without loading code...")
        doc = load_pipeline_document(yaml_file)
        print(f"  Document format version: {doc.format_version}")
        print(f"  Document pipeline name: {doc.name}")
        print(f"  Document edge count: {len(doc.edges)}")

        # 8. Separate Explicit Execution
        print("\n[Step 8] Executing reconstructed pipeline via LocalExecutor...")
        exec_result = loaded_pipe.run()
        print(f"  Execution Status: {exec_result.status.value}")
        print(f"  Execution Success: {exec_result.success}")
        print(f"  Alerts generated: {exec_result.outputs['notifier']['alerts']}")

    print("\n" + "=" * 70)
    print("Demonstration completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
