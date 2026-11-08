"""End-to-end example of executing a FinForge AI workflow with the synchronous runtime.

This script demonstrates:
  1. Registering deterministic scratch-built components:
     DataLoader -> Preprocessor -> KMeans -> Evaluator.
  2. Assembling the pipeline using the Pipeline builder API.
  3. Supplying pipeline-level external inputs.
  4. Executing the workflow synchronously via `pipeline.run()`.
  5. Inspecting structured execution diagnostics and outputs.
  6. Demonstrating clear error reporting and cleanup on execution failure.
"""

from typing import Any

from finforge import Pipeline
from finforge.component import BaseComponent
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Deterministic Scratch-Built Components (No heavy ML dependencies)
# ---------------------------------------------------------------------------


class DataLoader(BaseComponent):
    """Component that ingests raw numeric data points from external input."""

    def setup(self, config: dict[str, Any]) -> None:
        self.default_source = config.get("default_source", "in_memory")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        source = inputs.get("source", self.default_source)
        # Produce a simple deterministic 2D feature matrix
        raw_features = [
            [1.0, 2.0],
            [1.5, 1.8],
            [5.0, 8.0],
            [8.0, 8.0],
            [1.0, 0.6],
            [9.0, 11.0],
        ]
        nid = context["node_id"]
        print(f"  [{nid}] Loaded {len(raw_features)} samples from '{source}'.")
        return {"raw_data": raw_features}

    def teardown(self) -> None:
        pass


class Preprocessor(BaseComponent):
    """Component that scales and centers numerical features."""

    def setup(self, config: dict[str, Any]) -> None:
        self.scale_factor = float(config.get("scale_factor", 1.0))

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raw_data = inputs["data"]
        # Multiply by scale factor
        scaled = [[val * self.scale_factor for val in row] for row in raw_data]
        nid = context["node_id"]
        print(f"  [{nid}] Scaled {len(scaled)} rows by factor {self.scale_factor}.")
        return {"cleaned_data": scaled}

    def teardown(self) -> None:
        pass


class KMeans(BaseComponent):
    """Scratch-built 1D centroid assigner based on simple coordinate partitioning."""

    def setup(self, config: dict[str, Any]) -> None:
        self.k = int(config.get("k", 2))

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        features = inputs["features"]
        # Deterministic dummy partition: point with x > 4 gets cluster 1, else cluster 0
        clusters = [1 if row[0] > 4.0 else 0 for row in features]
        nid = context["node_id"]
        print(f"  [{nid}] Partitioned {len(features)} points into {self.k} clusters.")
        return {"clusters": clusters}

    def teardown(self) -> None:
        pass


class Evaluator(BaseComponent):
    """Evaluates cluster balance."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        clusters = inputs["labels"]
        count_0 = sum(1 for c in clusters if c == 0)
        count_1 = sum(1 for c in clusters if c == 1)
        ratio = count_0 / max(count_1, 1)
        print(f"  [{context['node_id']}] Cluster balance ratio: {ratio:.2f}.")
        return {"balance_ratio": float(ratio)}

    def teardown(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Setup Registry & Workflow
# ---------------------------------------------------------------------------


def create_demo_registry() -> ComponentRegistry:
    """Register component manifests."""
    registry = ComponentRegistry()

    # 1. DataLoader
    registry.register(
        component_class=DataLoader,
        manifest=ComponentManifest(
            name="data-loader",
            version="0.1.0",
            description="Loads raw numeric features.",
            category="data-processing",
            entrypoint="demo:DataLoader",
            inputs={"source": PortDefinition(type="string", required=False)},
            outputs={
                "raw_data": PortDefinition(
                    type="array", items=PortDefinition(type="array")
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
            description="Scales numeric feature matrices.",
            category="data-processing",
            entrypoint="demo:Preprocessor",
            inputs={
                "data": PortDefinition(type="array", items=PortDefinition(type="array"))
            },
            outputs={
                "cleaned_data": PortDefinition(
                    type="array", items=PortDefinition(type="array")
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
            description="Partitions features into clusters.",
            category="machine-learning",
            entrypoint="demo:KMeans",
            inputs={
                "features": PortDefinition(
                    type="array", items=PortDefinition(type="array")
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
            description="Computes cluster balance ratio.",
            category="evaluation",
            entrypoint="demo:Evaluator",
            inputs={
                "labels": PortDefinition(
                    type="array", items=PortDefinition(type="integer")
                )
            },
            outputs={"balance_ratio": PortDefinition(type="number")},
        ),
    )

    return registry


def main() -> None:
    print("=== FinForge AI: Local Synchronous Runtime Execution Demo ===")

    registry = create_demo_registry()
    pipeline = Pipeline(
        name="customer-clustering-pipeline",
        registry=registry,
        description="End-to-end customer segmentation workflow.",
    )

    # Add workflow nodes
    pipeline.add("loader", "data-loader", config={"default_source": "dataset_v1.csv"})
    pipeline.add("prep", "preprocessor", config={"scale_factor": 2.0})
    pipeline.add("clusterer", "kmeans", config={"k": 2})
    pipeline.add("eval", "evaluator")

    # Connect ports
    pipeline.connect("loader", "raw_data", "prep", "data")
    pipeline.connect("prep", "cleaned_data", "clusterer", "features")
    pipeline.connect("clusterer", "clusters", "eval", "labels")

    print(f"\n1. Assembled pipeline '{pipeline.name}' with {len(pipeline)} nodes.")
    print(f"   Execution order: {' -> '.join(pipeline.execution_order())}")

    # 2. Execute pipeline synchronously
    print("\n2. Executing pipeline...")
    result = pipeline.run(
        inputs={"loader": {"source": "production_stream.csv"}},
        context={"environment": "local_demo"},
    )

    # 3. Inspect results
    print(f"\n3. Execution finished with status: {result.status.value.upper()}")
    print(f"   Success: {result.success}")
    print(f"   Total duration: {result.duration_ms:.2f}ms")
    print(f"   Nodes executed: {len(result.node_results)}")

    print("\n4. Node Results Breakdown:")
    for node_id, node_res in result.node_results.items():
        st = node_res.status.value
        dur = node_res.duration_ms
        print(f"   - Node '{node_id}': status={st}, duration={dur:.2f}ms")

    print("\n5. Final Pipeline Outputs:")
    for node_id, node_out in result.outputs.items():
        print(f"   - {node_id}: {node_out}")

    print(f"\n   Evaluator balance ratio: {result.get_output('eval', 'balance_ratio')}")


if __name__ == "__main__":
    main()
