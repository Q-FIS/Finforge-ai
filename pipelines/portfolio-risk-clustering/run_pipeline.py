"""Execution script for 'portfolio-risk-clustering' pipeline."""

import sys
from pathlib import Path

# Add project root and local pipeline paths
pipeline_dir = Path(__file__).resolve().parent
local_comps = pipeline_dir / "components"

# Add local components src directories to sys.path
for comp_path in local_comps.glob("*/src"):
    if comp_path.is_dir() and str(comp_path) not in sys.path:
        sys.path.insert(0, str(comp_path))

from finforge import Pipeline, ComponentRegistry


def main() -> None:
    print("=== FinForge AI: Running Pipeline 'portfolio-risk-clustering' ===")

    # 1. Discover local components inside this pipeline
    registry = ComponentRegistry()
    search_paths = [local_comps]

    # Also check workspace root components if present
    workspace_comps = pipeline_dir.parents[1] / "components"
    if workspace_comps.exists():
        search_paths.append(workspace_comps)

    registry.discover(search_paths=search_paths)
    print(f"✓ Discovered {len(registry)} components in registry.")

    # 2. Load pipeline definition
    yaml_path = pipeline_dir / "pipeline.yaml"
    pipeline = Pipeline.load(yaml_path, registry=registry)
    pipeline.validate()

    print(f"✓ Loaded pipeline '{pipeline.name}' successfully.")
    print(f"  Execution order: {pipeline.execution_order()}")

    # 3. Execute pipeline
    if not pipeline.nodes:
        print("\nPipeline has no nodes yet. Add components using:")
        print(f"  finforge create <component-name> --pipeline {pipeline_dir}")
        return

    result = pipeline.run()
    print("\n--- Pipeline Execution Complete ---")
    print(f"Status: {result.status}")
    if result.execution_errors:
        print(f"Errors: {result.execution_errors}")
    print(f"Outputs: {result.outputs}")


if __name__ == "__main__":
    main()
