"""Component name normalization and Python identifier derivation utilities."""

from __future__ import annotations

import keyword
import re

from finforge.exceptions import InvalidIdentifierError

_COMPONENT_NAME_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def normalize_component_name(name: str) -> str:
    """Validate and normalize a component slug name.

    Args:
        name: Raw component name string (e.g. 'custom-kmeans', 'my_rag_agent').

    Returns:
        A trimmed, lowercase component slug name.

    Raises:
        InvalidIdentifierError: If the name contains path separators, parent
            directory references, or does not conform to component naming rules.
    """
    if not isinstance(name, str):
        raise InvalidIdentifierError(
            f"Component name must be a string, got {type(name).__name__}."
        )

    trimmed = name.strip()
    if not trimmed:
        raise InvalidIdentifierError("Component name cannot be empty.")

    if "/" in trimmed or "\\" in trimmed or ".." in trimmed:
        raise InvalidIdentifierError(
            f"Invalid component name '{name}': contains path separators or "
            "parent traversal indicators."
        )

    lowered = trimmed.lower()
    if not _COMPONENT_NAME_REGEX.match(lowered):
        raise InvalidIdentifierError(
            f"Invalid component name '{name}'. Must be lowercase alphanumeric "
            "characters separated by single hyphens or underscores (e.g. 'my-kmeans')."
        )

    return lowered


def to_package_name(name: str) -> str:
    """Derive a valid Python package name from a component name.

    Args:
        name: Component name or raw identifier.

    Returns:
        A valid Python package name (lowercase, underscores).

    Raises:
        InvalidIdentifierError: If a valid Python identifier cannot be derived.
    """
    if not isinstance(name, str):
        raise InvalidIdentifierError(
            f"Component name must be a string, got {type(name).__name__}."
        )

    # Replace hyphens and whitespace with underscores
    pkg = re.sub(r"[- \t]+", "_", name.strip().lower())
    pkg = re.sub(r"_+", "_", pkg).strip("_")

    if not pkg:
        raise InvalidIdentifierError(
            f"Cannot derive a valid Python package name from '{name}'."
        )

    if not pkg.isidentifier() or keyword.iskeyword(pkg):
        raise InvalidIdentifierError(
            f"Derived package name '{pkg}' from '{name}' is not a valid Python "
            "identifier or is a reserved keyword."
        )

    return pkg


def to_class_name(name: str, suffix: str = "Component") -> str:
    """Derive a valid PascalCase Python class name from a component name.

    Args:
        name: Component name or raw identifier.
        suffix: Optional class suffix (default: 'Component').

    Returns:
        A valid PascalCase Python class name.

    Raises:
        InvalidIdentifierError: If a valid Python class name cannot be derived.
    """
    if not isinstance(name, str):
        raise InvalidIdentifierError(
            f"Component name must be a string, got {type(name).__name__}."
        )

    words = [part for part in re.split(r"[-_ \t]+", name.strip()) if part]
    if not words:
        raise InvalidIdentifierError(
            f"Cannot derive a valid Python class name from '{name}'."
        )

    # Capitalize first letter of each segment while preserving internal casing
    class_name = "".join(word[0].upper() + word[1:] for word in words)

    if suffix and not class_name.endswith(suffix):
        class_name = f"{class_name}{suffix}"

    if not class_name.isidentifier() or keyword.iskeyword(class_name):
        raise InvalidIdentifierError(
            f"Derived class name '{class_name}' from '{name}' is not a valid "
            "Python identifier or is a reserved keyword."
        )

    return class_name
