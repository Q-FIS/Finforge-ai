"""End-to-end example of constructing a FinForge AI workflow via the Pipeline builder.

This script demonstrates:
  1. Setting up an explicit ComponentRegistry with demo components.
  2. Initializing a Pipeline builder instance.
  3. Adding workflow nodes (DataLoader, Preprocessor, KMeans, Evaluator).
  4. Connecting compatible component ports using directed edges.
  5. Inspecting pipeline summary metadata and structure.
  6. Validating the complete graph against architectural invariants.
  7. Computing the deterministic topological execution order.
"""

from typing import Any

from finforge import Pipeline
from finforge.component import BaseComponent
from finforge.exceptions import CycleDetectedError
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Demonstration Components (Metadata only; algorithms are not executed)
# ---------------------------------------------------------------------------


class DataLoader(BaseComponent):
    """Component that ingests raw numeric datasets."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"raw_data": [1.0, 2.0, 3.0]}


class Preprocessor(BaseComponent):
    """Component that cleans and standardizes numeric datasets."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"cleaned_data": inputs.get("data", [])}


class KMeans(BaseComponent):
    """Component that performs cluster assignment."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"clusters": [0, 1, 0]}


class Evaluator(BaseComponent):
    """Component that assesses clustering quality."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"silhouette_score": 0.88}


def build_demo_registry() -> ComponentRegistry:
    """Register component manifests in an explicit registry instance."""
    registry = ComponentRegistry()

    registry.register(
        component_class=DataLoader,
        manifest=ComponentManifest(
            name="data-loader",
            version="0.1.0",
            description="Loads raw numeric datasets.",
            category="data-processing",
            entrypoint="demo:DataLoader",
            inputs={},
            outputs={
                "raw_data": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                )
            },
        ),
    )

    registry.register(
        component_class=Preprocessor,
        manifest=ComponentManifest(
            name="data-preprocessor",
            version="0.1.0",
            description="Standardizes array inputs.",
            category="data-processing",
            entrypoint="demo:Preprocessor",
            inputs={
                "data": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                ),
                "feedback": PortDefinition(
                    type="array",
                    items=PortDefinition(type="number"),
                    required=False,
                ),
            },
            outputs={
                "cleaned_data": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                )
            },
        ),
    )

    registry.register(
        component_class=KMeans,
        manifest=ComponentManifest(
            name="custom-kmeans",
            version="0.1.0",
            description="Performs K-Means clustering.",
            category="machine-learning",
            entrypoint="demo:KMeans",
            inputs={
                "features": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                )
            },
            outputs={
                "clusters": PortDefinition(
                    type="array", items=PortDefinition(type="integer")
                )
            },
        ),
    )

    registry.register(
        component_class=Evaluator,
        manifest=ComponentManifest(
            name="evaluator",
            version="0.1.0",
            description="Computes clustering metrics.",
            category="evaluation",
            entrypoint="demo:Evaluator",
            inputs={
                "labels": PortDefinition(
                    type="array", items=PortDefinition(type="integer")
                )
            },
            outputs={"silhouette_score": PortDefinition(type="number")},
        ),
    )

    return registry


def main() -> None:
    print("=== FinForge AI: Python Pipeline Builder API Demo ===")

    # Step 1: Initialize explicit registry
    registry = build_demo_registry()
    print(f"\n1. Initialized registry with {len(registry)} components.")

    # Step 2: Construct Pipeline with explicit registry
    pipeline = Pipeline(
        name="customer-segmentation",
        registry=registry,
        description="End-to-end customer clustering workflow.",
    )
    print(f"2. Initialized pipeline: {pipeline}")

    # Step 3: Add nodes
    pipeline.add(
        node_id="loader",
        component_name="data-loader",
        config={"filepath": "customers.csv"},
    )
    pipeline.add(
        node_id="preprocessor",
        component_name="data-preprocessor",
        config={"scale": True},
    )
    pipeline.add(
        node_id="cluster",
        component_name="custom-kmeans",
        config={"k": 4},
    )
    pipeline.add(
        node_id="eval",
        component_name="evaluator",
    )
    print(f"3. Added {len(pipeline)} nodes: {[n.node_id for n in pipeline.list()]}")

    # Step 4: Connect component ports
    pipeline.connect(
        source_node="loader",
        source_port="raw_data",
        destination_node="preprocessor",
        destination_port="data",
    )
    pipeline.connect(
        source_node="preprocessor",
        source_port="cleaned_data",
        destination_node="cluster",
        destination_port="features",
    )
    pipeline.connect(
        source_node="cluster",
        source_port="clusters",
        destination_node="eval",
        destination_port="labels",
    )
    print(f"4. Established {len(pipeline.edges)} directed connections:")
    for edge in pipeline.edges:
        print(f"   - {edge}")

    # Step 5: Introspect pipeline summary
    summary = pipeline.summary()
    print("\n5. Pipeline Summary:")
    print(f"   - Name: {summary['name']}")
    print(f"   - Description: {summary['description']}")
    print(f"   - Components used: {summary['component_names']}")
    print(f"   - Nodes: {summary['nodes']}")
    print(f"   - Edges: {summary['edges']}")

    # Step 6: Validate pipeline structure
    pipeline.validate()
    print("\n6. Pipeline validation passed (all ports, types, and invariants valid).")

    # Step 7: Retrieve deterministic topological execution order
    order = pipeline.execution_order()
    print(f"7. Topological Execution Order: {' -> '.join(order)}")

    # Step 8: Verify cycle rejection
    print("\n8. Demonstrating cycle rejection on pipeline:")
    try:
        pipeline.connect("cluster", "clusters", "preprocessor", "feedback")
    except CycleDetectedError as err:
        print(f"   [SUCCESS] Cycle correctly rejected:\n     {err}")


if __name__ == "__main__":
    main()
