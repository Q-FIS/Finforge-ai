"""End-to-End Scratch-First Classical ML Pipeline Example in FinForge AI.

Demonstrates a first-principles Unsupervised Clustering pipeline:
1. Scratch Feature Scaler (Z-Score normalization without scikit-learn)
2. Scratch K-Means (Lloyd's algorithm: iterative centroids & Euclidean distance)
3. Scratch Cluster Profiler (computes cluster centers and sample distribution)

Zero external ML libraries (pure Python + FinForge contracts).
"""

from __future__ import annotations

import math
from typing import Any

from finforge.component import BaseComponent
from finforge.manifest.models import ComponentManifest, ConfigDefinition, PortDefinition
from finforge.pipeline.builder import Pipeline
from finforge.registry import ComponentRegistry


# ==============================================================================
# 1. Scratch Feature Standardizer
# ==============================================================================
class ScratchStandardScalerComponent(BaseComponent):
    """Z-score standardization: (x - mean) / std."""

    def __init__(self) -> None:
        self._with_std: bool = True

    def setup(self, config: dict[str, Any]) -> None:
        self._with_std = config.get("with_std", True)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        data: list[list[float]] = inputs["features"]
        if not data or not data[0]:
            return {"scaled_features": []}

        n_samples = len(data)
        n_features = len(data[0])

        # Compute means
        means = [sum(data[i][j] for i in range(n_samples)) / n_samples for j in range(n_features)]

        # Compute standard deviations
        stds = []
        for j in range(n_features):
            variance = sum((data[i][j] - means[j]) ** 2 for i in range(n_samples)) / max(1, n_samples)
            std = math.sqrt(variance)
            stds.append(std if std > 1e-8 else 1.0)

        # Scale features
        scaled: list[list[float]] = []
        for row in data:
            if self._with_std:
                scaled_row = [(row[j] - means[j]) / stds[j] for j in range(n_features)]
            else:
                scaled_row = [row[j] - means[j] for j in range(n_features)]
            scaled.append(scaled_row)

        return {"scaled_features": scaled}

    def teardown(self) -> None:
        pass


# ==============================================================================
# 2. Scratch K-Means Clustering
# ==============================================================================
class ScratchKMeansComponent(BaseComponent):
    """K-Means clustering algorithm implemented from first principles."""

    def __init__(self) -> None:
        self._k: int = 2
        self._max_iter: int = 50

    def setup(self, config: dict[str, Any]) -> None:
        self._k = config.get("k", 2)
        self._max_iter = config.get("max_iter", 50)

    @staticmethod
    def _euclidean_sq(p1: list[float], p2: list[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(p1, p2))

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        points: list[list[float]] = inputs["features"]
        if not points:
            return {"labels": [], "centroids": []}

        k = min(self._k, len(points))
        dim = len(points[0])

        # Deterministic seed centroids: first k unique samples
        centroids = [list(points[i]) for i in range(k)]
        labels = [0] * len(points)

        for _ in range(self._max_iter):
            # Assignment step
            new_labels = []
            for pt in points:
                closest_idx = min(
                    range(k),
                    key=lambda idx: self._euclidean_sq(pt, centroids[idx]),
                )
                new_labels.append(closest_idx)

            if new_labels == labels:
                break
            labels = new_labels

            # Update step
            for idx in range(k):
                cluster_pts = [points[i] for i in range(len(points)) if labels[i] == idx]
                if cluster_pts:
                    centroids[idx] = [
                        sum(cp[d] for cp in cluster_pts) / len(cluster_pts)
                        for d in range(dim)
                    ]

        return {"labels": labels, "centroids": centroids}

    def teardown(self) -> None:
        pass


# ==============================================================================
# 3. Scratch Cluster Profiler
# ==============================================================================
class ScratchClusterProfilerComponent(BaseComponent):
    """Summarizes cluster allocations and distribution metrics."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        labels: list[int] = inputs["labels"]
        centroids: list[list[float]] = inputs["centroids"]

        counts: dict[str, int] = {}
        for lab in labels:
            key = f"cluster_{lab}"
            counts[key] = counts.get(key, 0) + 1

        summary = {
            "total_samples": len(labels),
            "num_clusters": len(centroids),
            "distribution": counts,
        }
        return {"cluster_profile": summary}

    def teardown(self) -> None:
        pass


def build_and_run_ml_pipeline() -> None:
    registry = ComponentRegistry()

    scaler_manifest = ComponentManifest(
        name="scratch-scaler",
        version="0.1.0",
        description="Scratch Z-Score standard scaler",
        category="classical-ml",
        entrypoint="examples.classical_ml_pipeline_example:ScratchStandardScalerComponent",
        inputs={"features": PortDefinition(type="array", description="2D feature matrix")},
        outputs={"scaled_features": PortDefinition(type="array", description="Scaled matrix")},
        config={"with_std": ConfigDefinition(type="boolean", default=True)},
    )
    registry.register(ScratchStandardScalerComponent, manifest=scaler_manifest)

    kmeans_manifest = ComponentManifest(
        name="scratch-kmeans",
        version="0.1.0",
        description="Scratch Lloyd's K-Means clusterer",
        category="classical-ml",
        entrypoint="examples.classical_ml_pipeline_example:ScratchKMeansComponent",
        inputs={"features": PortDefinition(type="array", description="Scaled matrix")},
        outputs={
            "labels": PortDefinition(type="array", description="Cluster assignments"),
            "centroids": PortDefinition(type="array", description="Centroid coordinates"),
        },
        config={"k": ConfigDefinition(type="integer", default=2)},
    )
    registry.register(ScratchKMeansComponent, manifest=kmeans_manifest)

    profiler_manifest = ComponentManifest(
        name="scratch-profiler",
        version="0.1.0",
        description="Cluster distribution profiler",
        category="evaluation",
        entrypoint="examples.classical_ml_pipeline_example:ScratchClusterProfilerComponent",
        inputs={
            "labels": PortDefinition(type="array", description="Cluster labels"),
            "centroids": PortDefinition(type="array", description="Cluster centroids"),
        },
        outputs={"cluster_profile": PortDefinition(type="object", description="Summary metrics")},
    )
    registry.register(ScratchClusterProfilerComponent, manifest=profiler_manifest)

    # Build Pipeline
    pipeline = Pipeline("scratch-financial-asset-clustering", registry=registry)
    pipeline.add("scaler", "scratch-scaler")
    pipeline.add("kmeans", "scratch-kmeans", config={"k": 2})
    pipeline.add("profiler", "scratch-profiler")

    pipeline.connect("scaler", "scaled_features", "kmeans", "features")
    pipeline.connect("kmeans", "labels", "profiler", "labels")
    pipeline.connect("kmeans", "centroids", "profiler", "centroids")

    pipeline.validate()
    print("[Pipeline Validation] Unsupervised ML DAG validated successfully.")

    # 4 synthetic financial assets: [Volatility %, P/E Ratio]
    financial_assets = [
        [12.5, 14.2],  # Low vol, Value
        [14.1, 15.0],  # Low vol, Value
        [38.4, 45.1],  # High vol, Growth
        [42.0, 52.3],  # High vol, Growth
    ]

    result = pipeline.run(inputs={"scaler": {"features": financial_assets}})
    print("\n--- ML Pipeline Execution Output ---")
    print(f"Status: {result.status.value}")
    print(f"Duration: {result.duration_ms:.2f}ms")
    profile = result.node_results["profiler"].outputs["cluster_profile"]
    print(f"Summary: {profile}")
    labels = result.node_results["kmeans"].outputs["labels"]
    print(f"Cluster Assignments: {labels}")


if __name__ == "__main__":
    build_and_run_ml_pipeline()
