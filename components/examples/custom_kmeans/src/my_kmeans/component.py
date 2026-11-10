"""K-Means clustering algorithm implemented from scratch with Lloyd's iteration."""

from __future__ import annotations

import math
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)


class KMeansComponent(BaseComponent):
    """K-Means clustering algorithm implemented from scratch with Lloyd's iteration."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._n_clusters: int = 3
        self._max_iter: int = 300
        self._tol: float = 0.0001

    def setup(self, config: dict[str, Any]) -> None:
        """Configure clustering hyperparameters.

        Args:
            config: Mapping containing 'n_clusters', 'max_iter', and 'tol'.

        Raises:
            ComponentConfigurationError: If any parameter is invalid.
        """
        raw_k = config.get("n_clusters", 3)
        if not isinstance(raw_k, int) or isinstance(raw_k, bool) or raw_k <= 0:
            raise ComponentConfigurationError(
                f"Invalid 'n_clusters': expected positive integer, got {raw_k!r}."
            )

        raw_max_iter = config.get("max_iter", 300)
        if (
            not isinstance(raw_max_iter, int)
            or isinstance(raw_max_iter, bool)
            or raw_max_iter <= 0
        ):
            raise ComponentConfigurationError(
                f"Invalid 'max_iter': expected positive integer, got {raw_max_iter!r}."
            )

        raw_tol = config.get("tol", 0.0001)
        if (
            not isinstance(raw_tol, (int, float))
            or isinstance(raw_tol, bool)
            or raw_tol < 0
        ):
            raise ComponentConfigurationError(
                f"Invalid 'tol': expected non-negative float/number, got {raw_tol!r}."
            )

        self._n_clusters = int(raw_k)
        self._max_iter = int(raw_max_iter)
        self._tol = float(raw_tol)
        self._is_configured = True

    @staticmethod
    def _dist_sq(p1: list[float], p2: list[float]) -> float:
        """Squared Euclidean distance between two vectors."""
        return sum((a - b) ** 2 for a, b in zip(p1, p2))

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute Lloyd's iterative clustering on input dataset.

        Args:
            inputs: Dictionary containing 'data' as list of feature vectors.
            context: Runtime execution context metadata.

        Returns:
            Dictionary containing 'labels' and 'centroids'.

        Raises:
            ComponentLifecycleError: If executed before setup().
            ComponentExecutionError: If data is missing, malformed, or invalid.
        """
        if not self._is_configured:
            raise ComponentLifecycleError(
                "KMeansComponent must be configured via setup() before run()."
            )

        if "data" not in inputs:
            raise ComponentExecutionError("Missing required input port: 'data'.")

        raw_data = inputs["data"]
        if not isinstance(raw_data, list):
            raise ComponentExecutionError(
                f"Expected 'data' to be a list, got {type(raw_data).__name__}."
            )

        if not raw_data:
            return {"labels": [], "centroids": []}

        # Validate rows and dimensionality
        data: list[list[float]] = []
        for idx, row in enumerate(raw_data):
            if not isinstance(row, (list, tuple)):
                raise ComponentExecutionError(
                    f"Row {idx} in 'data' must be an array/list, got {type(row).__name__}."
                )
            try:
                converted_row = [float(x) for x in row]
            except (ValueError, TypeError) as exc:
                raise ComponentExecutionError(
                    f"Non-numeric value in row {idx}: {exc}"
                ) from exc
            data.append(converted_row)

        n_samples = len(data)
        n_features = len(data[0])

        for idx, row in enumerate(data):
            if len(row) != n_features:
                raise ComponentExecutionError(
                    f"Inconsistent feature dimension at row {idx}: "
                    f"expected {n_features}, got {len(row)}."
                )

        k = min(self._n_clusters, n_samples)
        if k <= 0 or n_features == 0:
            return {"labels": [0] * n_samples, "centroids": []}

        # Deterministic seed initialization: pick first k unique points
        centroids: list[list[float]] = []
        for pt in data:
            if pt not in centroids:
                centroids.append(list(pt))
            if len(centroids) == k:
                break

        # Fallback if fewer unique points than k
        while len(centroids) < k:
            centroids.append(list(data[len(centroids) % n_samples]))

        labels: list[int] = [0] * n_samples

        # Lloyd's iterative alternating optimization
        for _ in range(self._max_iter):
            # Assignment step
            new_labels: list[int] = []
            for pt in data:
                best_dist = float("inf")
                best_idx = 0
                for c_idx, c in enumerate(centroids):
                    d = self._dist_sq(pt, c)
                    if d < best_dist:
                        best_dist = d
                        best_idx = c_idx
                new_labels.append(best_idx)

            labels = new_labels

            # Update step
            new_centroids: list[list[float]] = []
            max_centroid_shift = 0.0

            for c_idx in range(k):
                cluster_pts = [
                    data[i] for i, lbl in enumerate(labels) if lbl == c_idx
                ]
                if cluster_pts:
                    updated_c = [
                        sum(p[j] for p in cluster_pts) / len(cluster_pts)
                        for j in range(n_features)
                    ]
                else:
                    updated_c = list(centroids[c_idx])

                shift = math.sqrt(self._dist_sq(centroids[c_idx], updated_c))
                if shift > max_centroid_shift:
                    max_centroid_shift = shift

                new_centroids.append(updated_c)

            centroids = new_centroids

            if max_centroid_shift <= self._tol:
                break

        return {"labels": labels, "centroids": centroids}

    def teardown(self) -> None:
        """Reset component state. Safe and idempotent."""
        self._is_configured = False
