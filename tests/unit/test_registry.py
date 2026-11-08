"""Unit tests for the FinForge AI in-memory ComponentRegistry."""

from typing import Any

import pytest

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentNotFoundError,
    ComponentRegistrationError,
    DuplicateComponentError,
)
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.registry import ComponentRegistry


class MockComponentA(BaseComponent):
    """Test component A tracking method calls to verify non-execution."""

    init_called = False
    setup_called = False
    run_called = False

    def __init__(self) -> None:
        MockComponentA.init_called = True

    def setup(self, config: dict[str, Any]) -> None:
        MockComponentA.setup_called = True

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        MockComponentA.run_called = True
        return {}


class MockComponentB(BaseComponent):
    """Test component B for multi-registration tests."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {}


def make_manifest(
    name: str = "mock-component-a",
    entrypoint: str = "test_module:MockComponentA",
    category: str = "machine-learning",
) -> ComponentManifest:
    """Helper to create a valid ComponentManifest."""
    return ComponentManifest(
        name=name,
        version="0.1.0",
        description=f"Manifest for {name}",
        api_version="1",
        category=category,
        entrypoint=entrypoint,
        inputs={"data": PortDefinition(type="array")},
        outputs={"labels": PortDefinition(type="array")},
    )


@pytest.fixture
def registry() -> ComponentRegistry:
    """Fixture providing a fresh in-memory registry instance."""
    return ComponentRegistry()


def test_register_valid_component(registry: ComponentRegistry) -> None:
    """1. Register a valid component and verify registry size."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)
    assert len(registry) == 1
    assert "mock-component-a" in registry


def test_retrieve_registered_component(registry: ComponentRegistry) -> None:
    """2. Retrieve a registered component class by name."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)
    retrieved_cls = registry.get("mock-component-a")
    assert retrieved_cls is MockComponentA


def test_retrieve_manifest(registry: ComponentRegistry) -> None:
    """3. Retrieve the associated manifest for a registered component."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)
    retrieved_manifest = registry.get_manifest("mock-component-a")
    assert retrieved_manifest.name == "mock-component-a"
    assert retrieved_manifest.category == "machine-learning"


def test_list_registered_components(registry: ComponentRegistry) -> None:
    """4. List registered components in sorted order with optional filtering."""
    manifest_a = make_manifest(
        name="alpha-comp",
        entrypoint="mod:MockComponentA",
        category="rag",
    )
    manifest_b = make_manifest(
        name="beta-comp",
        entrypoint="mod:MockComponentB",
        category="machine-learning",
    )
    registry.register(MockComponentA, manifest_a)
    registry.register(MockComponentB, manifest_b)

    # Deterministic alphabetical ordering
    assert registry.list_components() == ["alpha-comp", "beta-comp"]

    # Filtered by category
    assert registry.list_components(category="rag") == ["alpha-comp"]
    assert registry.list_components(category="machine-learning") == ["beta-comp"]
    assert registry.list_components(category="deep-learning") == []


def test_check_component_existence(registry: ComponentRegistry) -> None:
    """5. Check component existence via contains() and the 'in' operator."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)

    assert registry.contains("mock-component-a") is True
    assert "mock-component-a" in registry
    assert registry.contains("non-existent") is False
    assert "non-existent" not in registry
    assert (123 in registry) is False  # Non-string containment


def test_unregister_component(registry: ComponentRegistry) -> None:
    """6. Unregister a component and verify it is removed from the registry."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)
    assert "mock-component-a" in registry

    registry.unregister("mock-component-a")
    assert len(registry) == 0
    assert "mock-component-a" not in registry


def test_duplicate_registration_rejected(registry: ComponentRegistry) -> None:
    """7. Duplicate registrations rejected by default; allowed with overwrite=True."""
    manifest = make_manifest()
    registry.register(MockComponentA, manifest)

    with pytest.raises(DuplicateComponentError) as excinfo:
        registry.register(MockComponentA, manifest)
    assert "already registered" in str(excinfo.value)
    assert "overwrite=True" in str(excinfo.value)

    # Overwrite explicitly allowed
    registry.register(MockComponentA, manifest, overwrite=True)
    assert len(registry) == 1


def test_invalid_class_rejected(registry: ComponentRegistry) -> None:
    """8. Invalid component classes (instances, strings, functions) are rejected."""
    manifest = make_manifest()

    # Pass an instance instead of a class
    with pytest.raises(ComponentRegistrationError) as exc_inst:
        registry.register(MockComponentA(), manifest)  # type: ignore[arg-type]
    assert "Expected component_class to be a class" in str(exc_inst.value)

    # Pass a string
    with pytest.raises(ComponentRegistrationError) as exc_str:
        registry.register("NotAClass", manifest)  # type: ignore[arg-type]
    assert "Expected component_class to be a class" in str(exc_str.value)


def test_non_base_component_class_rejected(registry: ComponentRegistry) -> None:
    """9. Classes that do not inherit from BaseComponent are rejected."""

    class PlainPythonClass:
        pass

    manifest = make_manifest(
        entrypoint="test:PlainPythonClass",
    )
    with pytest.raises(ComponentRegistrationError) as excinfo:
        registry.register(PlainPythonClass, manifest)  # type: ignore[arg-type]
    assert "must inherit from BaseComponent" in str(excinfo.value)

    # Direct BaseComponent class is also rejected
    manifest_base = make_manifest(entrypoint="base:BaseComponent")
    with pytest.raises(ComponentRegistrationError) as exc_base:
        registry.register(BaseComponent, manifest_base)
    assert "Cannot register abstract BaseComponent directly" in str(exc_base.value)


def test_invalid_manifest_rejected(registry: ComponentRegistry) -> None:
    """10. Invalid manifest types (dict, string, None) are rejected."""
    with pytest.raises(ComponentRegistrationError) as excinfo:
        registry.register(MockComponentA, {"name": "invalid"})  # type: ignore[arg-type]
    assert "Manifest must be an instance of ComponentManifest" in str(excinfo.value)


def test_component_manifest_mismatch_rejected(registry: ComponentRegistry) -> None:
    """11. Mismatch between component class name and manifest entrypoint is rejected."""
    # Manifest entrypoint specifies DifferentClass, but we pass MockComponentA
    mismatch_manifest = make_manifest(entrypoint="mod:DifferentClass")
    with pytest.raises(ComponentRegistrationError) as exc_class:
        registry.register(MockComponentA, mismatch_manifest)
    assert "does not match entrypoint class 'DifferentClass'" in str(exc_class.value)

    # Explicit name argument mismatch
    valid_manifest = make_manifest(name="my-comp")
    with pytest.raises(ComponentRegistrationError) as exc_name:
        registry.register(MockComponentA, valid_manifest, name="other-name")
    assert "does not match manifest name" in str(exc_name.value)


def test_unknown_component_retrieval_raises_error(
    registry: ComponentRegistry,
) -> None:
    """12. Retrieving an unregistered component raises ComponentNotFoundError."""
    with pytest.raises(ComponentNotFoundError) as exc_get:
        registry.get("non-existent")
    assert "Component 'non-existent' is not registered" in str(exc_get.value)

    with pytest.raises(ComponentNotFoundError) as exc_man:
        registry.get_manifest("non-existent")
    assert "Component 'non-existent' is not registered" in str(exc_man.value)

    with pytest.raises(ComponentNotFoundError) as exc_entry:
        registry.get_entry("non-existent")
    assert "Component 'non-existent' is not registered" in str(exc_entry.value)


def test_unknown_component_removal_raises_error(
    registry: ComponentRegistry,
) -> None:
    """13. Removing an unregistered component raises ComponentNotFoundError."""
    with pytest.raises(ComponentNotFoundError) as excinfo:
        registry.unregister("non-existent")
    assert "Cannot unregister: component 'non-existent' is not registered" in str(
        excinfo.value
    )


def test_registering_does_not_instantiate_or_execute(
    registry: ComponentRegistry,
) -> None:
    """14, 15, 16. Registering does NOT instantiate class or execute setup()/run()."""
    MockComponentA.init_called = False
    MockComponentA.setup_called = False
    MockComponentA.run_called = False

    manifest = make_manifest()
    registry.register(MockComponentA, manifest)

    assert MockComponentA.init_called is False
    assert MockComponentA.setup_called is False
    assert MockComponentA.run_called is False


def test_internal_registry_data_cannot_be_mutated(
    registry: ComponentRegistry,
) -> None:
    """17. Returned manifests and lists do not allow mutating internal state."""
    manifest = make_manifest(name="immutable-test")
    registry.register(MockComponentA, manifest)

    # Mutating returned manifest does not mutate stored manifest
    fetched_manifest = registry.get_manifest("immutable-test")
    fetched_manifest.description = "MUTATED"

    stored_manifest = registry.get_manifest("immutable-test")
    assert stored_manifest.description == "Manifest for immutable-test"

    # Mutating list does not affect registry
    comp_list = registry.list_components()
    comp_list.append("rogue_element")
    assert registry.list_components() == ["immutable-test"]


def test_removing_one_registration_does_not_affect_others(
    registry: ComponentRegistry,
) -> None:
    """18. Removing one component leaves all other registrations completely intact."""
    manifest_a = make_manifest(name="comp-a", entrypoint="mod:MockComponentA")
    manifest_b = make_manifest(name="comp-b", entrypoint="mod:MockComponentB")

    registry.register(MockComponentA, manifest_a)
    registry.register(MockComponentB, manifest_b)
    assert len(registry) == 2

    registry.unregister("comp-a")
    assert len(registry) == 1
    assert "comp-a" not in registry
    assert "comp-b" in registry
    assert registry.get("comp-b") is MockComponentB


def test_registry_get_entry_and_list_manifests(
    registry: ComponentRegistry,
) -> None:
    """Test get_entry, list_manifests with category filtering, and clear."""
    manifest_a = make_manifest(
        name="comp-a", entrypoint="mod:MockComponentA", category="rag"
    )
    manifest_b = make_manifest(
        name="comp-b", entrypoint="mod:MockComponentB", category="machine-learning"
    )

    registry.register(MockComponentA, manifest_a)
    registry.register(MockComponentB, manifest_b)

    # get_entry
    entry_a = registry.get_entry("comp-a")
    assert entry_a.name == "comp-a"
    assert entry_a.component_class is MockComponentA
    assert entry_a.manifest.name == "comp-a"

    # list_manifests
    all_manifests = registry.list_manifests()
    assert len(all_manifests) == 2
    assert [m.name for m in all_manifests] == ["comp-a", "comp-b"]

    rag_manifests = registry.list_manifests(category="rag")
    assert len(rag_manifests) == 1
    assert rag_manifests[0].name == "comp-a"

    # repr and non-string in
    assert repr(registry) == "<ComponentRegistry registered=2>"
    assert (123 in registry) is False

    # clear
    registry.clear()
    assert len(registry) == 0
    assert repr(registry) == "<ComponentRegistry registered=0>"
