"""Example demonstrating FinForge AI Pipeline Graph (DAG) construction.

This script demonstrates:
  1. Defining dummy components and registering their manifests.
  2. Building a 4-step ML workflow graph:
     DataLoader -> Preprocessor -> KMeans -> Evaluator.
  3. Validating the pipeline graph structure and port compatibility.
  4. Demonstrating topological ordering (dependency resolution).
  5. Demonstrating automatic rejection of cycles and self-loops.
"""

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import CycleDetectedError
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.pipeline import PipelineGraph
from finforge.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Dummy Component Implementations (Metadata only; algorithms not executed)
# ---------------------------------------------------------------------------


class DataLoader(BaseComponent):
    """Component that loads raw numeric datasets."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"raw_data": [1.0, 2.0, 3.0]}


class Preprocessor(BaseComponent):
    """Component that cleans and normalizes numeric datasets."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"cleaned_data": inputs.get("data", [])}


class KMeans(BaseComponent):
    """Component that performs clustering on input features."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"clusters": [0, 1, 0]}


class Evaluator(BaseComponent):
    """Component that computes evaluation metrics on cluster assignments."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"silhouette_score": 0.85}


# ---------------------------------------------------------------------------
# Manifest Definitions
# ---------------------------------------------------------------------------


def create_demo_registry() -> ComponentRegistry:
    """Register demo component manifests in a fresh ComponentRegistry."""
    registry = ComponentRegistry()

    # 1. DataLoader
    registry.register(
        component_class=DataLoader,
        manifest=ComponentManifest(
            name="data-loader",
            version="0.1.0",
            description="Loads raw numeric data arrays.",
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

    # 2. Preprocessor
    registry.register(
        component_class=Preprocessor,
        manifest=ComponentManifest(
            name="preprocessor",
            version="0.1.0",
            description="Cleans and normalizes array inputs.",
            category="data-processing",
            entrypoint="demo:Preprocessor",
            inputs={
                "data": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                ),
                "extra": PortDefinition(
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

    # 3. KMeans
    registry.register(
        component_class=KMeans,
        manifest=ComponentManifest(
            name="kmeans",
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

    # 4. Evaluator
    registry.register(
        component_class=Evaluator,
        manifest=ComponentManifest(
            name="evaluator",
            version="0.1.0",
            description="Computes clustering evaluation metrics.",
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
    print("=== FinForge AI: Pipeline Graph DAG Architecture Demo ===")

    # Step 1: Initialize registry and pipeline graph
    registry = create_demo_registry()
    graph = PipelineGraph(registry=registry)
    print(f"\n1. Initialized PipelineGraph with {len(registry)} registered components.")

    # Step 2: Add nodes to graph
    graph.add_node(
        node_id="loader",
        component_name="data-loader",
        config={"source": "dataset.csv"},
    )
    graph.add_node(
        node_id="prep",
        component_name="preprocessor",
        config={"normalize": True},
    )
    graph.add_node(
        node_id="clusterer",
        component_name="kmeans",
        config={"k": 3},
    )
    graph.add_node(
        node_id="eval",
        component_name="evaluator",
    )
    print(f"2. Added {len(graph)} nodes: {[n.node_id for n in graph.list_nodes()]}")

    # Step 3: Connect compatible ports via directed edges
    graph.add_edge(
        source_node_id="loader",
        source_port="raw_data",
        destination_node_id="prep",
        destination_port="data",
    )
    graph.add_edge(
        source_node_id="prep",
        source_port="cleaned_data",
        destination_node_id="clusterer",
        destination_port="features",
    )
    graph.add_edge(
        source_node_id="clusterer",
        source_port="clusters",
        destination_node_id="eval",
        destination_port="labels",
    )
    print(f"3. Added {len(graph.list_edges())} directed edges:")
    for edge in graph.list_edges():
        print(f"   - {edge}")

    # Step 4: Validate DAG
    graph.validate()
    print("4. Graph validation passed successfully (all ports/types valid).")

    # Step 5: Compute deterministic topological execution order
    order = graph.execution_order()
    print(f"5. Topological Execution Order: {' -> '.join(order)}")

    # Step 6: Verify cycle rejection
    print("\n6. Demonstrating cycle rejection:")
    try:
        # Attempt to create cycle: clusterer -> prep (prep -> clusterer exists)
        graph.add_edge("clusterer", "clusters", "prep", "extra")
    except CycleDetectedError as err:
        print(f"   [SUCCESS] Cycle correctly rejected:\n     {err}")


if __name__ == "__main__":
    main()
