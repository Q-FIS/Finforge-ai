# Pipeline: portfolio-risk-clustering

> End-to-end financial portfolio risk clustering and assessment workflow

## Topology Diagram

```mermaid
flowchart LR
    loader["loader (portfolio-loader)"]
    clusterer["clusterer (custom-kmeans)"]
    risk_evaluator["risk_evaluator (risk-calculator)"]

    loader -->|"features -> data"| clusterer
    loader -->|"max_exposure -> amount"| risk_evaluator
```

## Nodes & Components

| Node ID | Component | Config Keys |
| :--- | :--- | :--- |
| `loader` | `portfolio-loader` | `volatility_scale` |
| `clusterer` | `custom-kmeans` | `n_clusters`, `max_iter` |
| `risk_evaluator` | `risk-calculator` | `threshold` |

## Port Connections

| Source | Destination |
| :--- | :--- |
| `loader.features` | `clusterer.data` |
| `loader.max_exposure` | `risk_evaluator.amount` |
