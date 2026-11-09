"""Pipeline integration example for RiskCalculatorComponent."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and component src
project_root = Path(__file__).resolve().parents[3]
component_src = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(component_src))

from risk_calculator.component import RiskCalculatorComponent  # noqa: E402

from finforge.manifest import load_manifest  # noqa: E402
from finforge.pipeline import Pipeline  # noqa: E402
from finforge.registry import ComponentRegistry  # noqa: E402


def main() -> None:
    print("=== FinForge AI: Pipeline Integration Demonstration ===\n")

    # 1. Register component in the registry
    manifest_path = Path(__file__).resolve().parents[1] / "component.yaml"
    manifest = load_manifest(manifest_path)

    registry = ComponentRegistry()
    registry.register(RiskCalculatorComponent, manifest)
    print(f"1. Registered component '{manifest.name}' into registry.")

    # 2. Build pipeline
    pipeline = Pipeline(
        name="transaction-risk-pipeline",
        registry=registry,
        description="Evaluates transaction risks",
    )
    pipeline.add(
        node_id="risk_evaluator",
        component_name="risk-calculator",
        config={"threshold": 7500.0},
    )
    pipeline.validate()
    print("2. Constructed pipeline with node 'risk_evaluator' (threshold=$7,500).")

    # 3. Execute via the Pipeline run() method
    test_amounts = [3200.0, 12500.0]
    for amt in test_amounts:
        result = pipeline.run(
            inputs={"risk_evaluator": {"amount": amt}}
        )
        output = result.outputs["risk_evaluator"]
        print(f"3. Executed with amount=${amt:,.2f} --> Output: {output}")

    print("\n✓ Pipeline execution successful.")


if __name__ == "__main__":
    main()
