"""In-memory component registry for FinForge AI.

This module provides `ComponentRegistry`, which maintains an in-memory mapping
between component names, component classes, and their validated manifests.
"""

from dataclasses import dataclass
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentNotFoundError,
    ComponentRegistrationError,
    DuplicateComponentError,
)
from finforge.manifest.models import ComponentManifest


@dataclass(frozen=True)
class RegistryEntry:
    """Immutable entry storing a registered component class and its manifest."""

    name: str
    component_class: type[BaseComponent]
    manifest: ComponentManifest


class ComponentRegistry:
    """In-memory registry for FinForge AI components.

    The registry maps unique component names to their uninstantiated Python classes
    and validated `ComponentManifest` metadata. Components are registered as
    classes and never automatically instantiated or executed during registration.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory ComponentRegistry."""
        self._entries: dict[str, RegistryEntry] = {}

    def register(
        self,
        component_class: type[BaseComponent],
        manifest: ComponentManifest,
        name: str | None = None,
        overwrite: bool = False,
    ) -> None:
        """Register a component class with its associated validated manifest.

        Args:
            component_class: Class inheriting from `BaseComponent` (not an instance).
            manifest: A validated `ComponentManifest` instance.
            name: Optional explicit name override; must match manifest if given.
            overwrite: If True, replace existing registration with the same name.
                Defaults to False.

        Raises:
            ComponentRegistrationError: If `component_class` is not a valid subclass
                of `BaseComponent`, `manifest` is invalid, or class name mismatches
                the manifest entrypoint.
            DuplicateComponentError: If a component with the same name is already
                registered and `overwrite=False`.
        """
        # 1. Validate component class type
        if not isinstance(component_class, type):
            raise ComponentRegistrationError(
                f"Expected component_class to be a class, got instance of "
                f"'{type(component_class).__name__}'."
            )

        if not issubclass(component_class, BaseComponent):
            raise ComponentRegistrationError(
                f"Component class '{component_class.__name__}' must inherit from "
                f"BaseComponent."
            )

        if component_class is BaseComponent:
            raise ComponentRegistrationError(
                "Cannot register abstract BaseComponent directly."
            )

        # 2. Validate manifest type
        if not isinstance(manifest, ComponentManifest):
            raise ComponentRegistrationError(
                f"Manifest must be an instance of ComponentManifest, got "
                f"'{type(manifest).__name__}'."
            )

        # 3. Validate name association
        comp_name = manifest.name
        if name is not None and name != comp_name:
            raise ComponentRegistrationError(
                f"Explicit registration name '{name}' does not match "
                f"manifest name '{comp_name}'."
            )

        # 4. Validate component class and manifest entrypoint match
        expected_class_name = manifest.entrypoint.split(":")[-1].strip()
        if component_class.__name__ != expected_class_name:
            raise ComponentRegistrationError(
                f"Component class '{component_class.__name__}' does not match "
                f"entrypoint class '{expected_class_name}' declared in manifest "
                f"'{comp_name}'."
            )

        # 5. Check duplicate registration
        if comp_name in self._entries and not overwrite:
            raise DuplicateComponentError(
                f"Component '{comp_name}' is already registered. "
                f"Use overwrite=True to replace existing registration."
            )

        # 6. Store deep copy of manifest to prevent external mutation
        self._entries[comp_name] = RegistryEntry(
            name=comp_name,
            component_class=component_class,
            manifest=manifest.model_copy(deep=True),
        )

    def get(self, name: str) -> type[BaseComponent]:
        """Retrieve a registered component class by name.

        Args:
            name: The unique name of the component.

        Returns:
            The uninstantiated component class inheriting from `BaseComponent`.

        Raises:
            ComponentNotFoundError: If no component with the given name is registered.
        """
        if name not in self._entries:
            raise ComponentNotFoundError(f"Component '{name}' is not registered.")
        return self._entries[name].component_class

    def get_manifest(self, name: str) -> ComponentManifest:
        """Retrieve the validated manifest for a registered component.

        Args:
            name: The unique name of the component.

        Returns:
            A deep copy of the registered `ComponentManifest`.

        Raises:
            ComponentNotFoundError: If no component with the given name is registered.
        """
        if name not in self._entries:
            raise ComponentNotFoundError(f"Component '{name}' is not registered.")
        return self._entries[name].manifest.model_copy(deep=True)

    def get_entry(self, name: str) -> RegistryEntry:
        """Retrieve the full registry entry (class and manifest) for a component.

        Args:
            name: The unique name of the component.

        Returns:
            A `RegistryEntry` containing component name, class, and copied manifest.

        Raises:
            ComponentNotFoundError: If no component with the given name is registered.
        """
        if name not in self._entries:
            raise ComponentNotFoundError(f"Component '{name}' is not registered.")
        entry = self._entries[name]
        return RegistryEntry(
            name=entry.name,
            component_class=entry.component_class,
            manifest=entry.manifest.model_copy(deep=True),
        )

    def list_components(self, category: str | None = None) -> list[str]:
        """List registered component names in deterministic sorted order.

        Args:
            category: Optional category filter (e.g. 'machine-learning', 'rag').

        Returns:
            A sorted list of component name strings.
        """
        matching = [
            name
            for name, entry in self._entries.items()
            if category is None or entry.manifest.category == category
        ]
        return sorted(matching)

    def list_manifests(self, category: str | None = None) -> list[ComponentManifest]:
        """List manifests of registered components in deterministic sorted order.

        Args:
            category: Optional category filter.

        Returns:
            A sorted list of `ComponentManifest` deep copies.
        """
        matching = [
            entry.manifest.model_copy(deep=True)
            for name, entry in sorted(self._entries.items())
            if category is None or entry.manifest.category == category
        ]
        return matching

    def contains(self, name: str) -> bool:
        """Check whether a component is registered by name.

        Args:
            name: The component name to check.

        Returns:
            True if registered, False otherwise.
        """
        return name in self._entries

    def __contains__(self, name: Any) -> bool:
        """Support `name in registry` syntax."""
        if not isinstance(name, str):
            return False
        return self.contains(name)

    def unregister(self, name: str) -> None:
        """Remove a component and its associated manifest from the registry.

        Args:
            name: The component name to remove.

        Raises:
            ComponentNotFoundError: If the component is not currently registered.
        """
        if name not in self._entries:
            raise ComponentNotFoundError(
                f"Cannot unregister: component '{name}' is not registered."
            )
        del self._entries[name]

    def clear(self) -> None:
        """Remove all registered components."""
        self._entries.clear()

    def __len__(self) -> int:
        """Return the number of currently registered components."""
        return len(self._entries)

    def __repr__(self) -> str:
        """Return a string representation of the registry state."""
        return f"<ComponentRegistry registered={len(self._entries)}>"
