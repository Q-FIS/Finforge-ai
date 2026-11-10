# Custom K-Means Clustering Component

A scratch-first, pure Python implementation of Lloyd's K-Means clustering algorithm for FinForge AI.

## Overview
- **Category**: `machine-learning`
- **Algorithm**: Lloyd's alternating iterative clustering with Euclidean distance
- **Dependencies**: None (pure Python standard library)

## Ports
- **Inputs**:
  - `data` (array): Input feature matrix of shape `(n_samples, n_features)`.
- **Outputs**:
  - `labels` (array): Cluster assignments for each sample.
  - `centroids` (array): Final coordinates of cluster centroids.

## Configuration
- `n_clusters` (int, default: 3): Number of clusters to form.
- `max_iter` (int, default: 300): Maximum iterations for optimization.
- `tol` (float, default: 0.0001): Frobenius norm convergence threshold.
