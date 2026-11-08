"""Demonstration of FinForge AI Component Registry operations.

This example illustrates:
  1. Defining a custom component inheriting from BaseComponent.
  2. Defining its validated ComponentManifest.
  3. Registering the component in an in-memory ComponentRegistry.
  4. Checking registration and retrieving the component class.
  5. Inspecting component metadata.
  6. Listing registered components with category filters.
  7. Unregistering the component cleanly.
"""

from typing import Any

from finforge.component import BaseComponent
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.registry import ComponentRegistry


class SimpleNormalizer(BaseComponent):
    """Reference normalizer component for registry demonstration."""

    def setup(self, config: dict[str, Any]) -> None:
        self.scale = config.get("scale", 1.0)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raw = inputs.get("data", [])
        return {"normalized": [x * self.scale for x in raw]}


def main() -> None:
    print("--- 1. Initialize In-Memory Registry ---")
    registry = ComponentRegistry()
    print(f"Initial registry state: {registry}")

    print("\n--- 2. Create Component Manifest ---")
    manifest = ComponentManifest(
        name="simple-normalizer",
        version="0.1.0",
        description="Scales array inputs by a configured factor.",
        api_version="1",
        category="data-processing",
        entrypoint="demo.components:SimpleNormalizer",
        inputs={
            "data": PortDefinition(type="array", items=PortDefinition(type="number"))
        },
        outputs={
            "normalized": PortDefinition(
                type="array", items=PortDefinition(type="number")
            )
        },
    )
    print(f"Manifest created: {manifest.name} (v{manifest.version})")

    print("\n--- 3. Register Component ---")
    registry.register(component_class=SimpleNormalizer, manifest=manifest)
    print(f"Component registered successfully. Total registered: {len(registry)}")

    print("\n--- 4. Verify Presence and Retrieve ---")
    assert "simple-normalizer" in registry
    assert registry.contains("simple-normalizer") is True

    retrieved_class = registry.get("simple-normalizer")
    print(f"Retrieved class: {retrieved_class.__name__}")
    assert retrieved_class is SimpleNormalizer

    retrieved_manifest = registry.get_manifest("simple-normalizer")
    print(f"Retrieved manifest category: {retrieved_manifest.category}")
    assert retrieved_manifest.name == "simple-normalizer"

    print("\n--- 5. List Components ---")
    all_components = registry.list_components()
    print(f"All components: {all_components}")

    data_proc_components = registry.list_components(category="data-processing")
    print(f"Filtered (category='data-processing'): {data_proc_components}")

    print("\n--- 6. Unregister Component ---")
    registry.unregister("simple-normalizer")
    print(f"Unregistered 'simple-normalizer'. Remaining: {len(registry)}")
    assert "simple-normalizer" not in registry
    print("✓ Registry demonstration completed successfully.")


if __name__ == "__main__":
    main()
