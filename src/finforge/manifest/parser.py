"""YAML manifest parsing and validation engine for FinForge AI.

This module loads, parses, and validates `component.yaml` files, converting
declarative specifications into strongly typed `ComponentManifest` objects.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from finforge.exceptions import (
    ManifestNotFoundError,
    ManifestParseError,
    ManifestValidationError,
)
from finforge.manifest.models import ComponentManifest


def parse_manifest(content: str, source: str | None = None) -> ComponentManifest:
    """Parse and validate a component manifest from a YAML string.

    Args:
        content: The YAML string content to parse.
        source: Optional label identifying the source for error reporting.

    Returns:
        A validated `ComponentManifest` instance.

    Raises:
        ManifestParseError: If the YAML is empty, malformed, or not a mapping.
        ManifestValidationError: If the manifest fails schema validation.
    """
    source_label = source or "<string>"

    if not content or not content.strip():
        raise ManifestParseError(f"Manifest at '{source_label}' is empty.")

    try:
        data: Any = yaml.safe_load(content)
    except yaml.YAMLError as err:
        raise ManifestParseError(
            f"Malformed YAML in manifest at '{source_label}': {err}"
        ) from err

    if data is None:
        raise ManifestParseError(f"Manifest at '{source_label}' is empty.")

    if not isinstance(data, dict):
        raise ManifestParseError(
            f"Manifest at '{source_label}' must be a YAML mapping "
            f"(key-value dictionary), got {type(data).__name__}."
        )

    try:
        return ComponentManifest.model_validate(data)
    except ValidationError as err:
        error_messages: list[str] = []
        for error in err.errors():
            loc = " -> ".join(str(elem) for elem in error["loc"])
            msg = error["msg"]
            error_messages.append(f"  - [{loc}]: {msg}")
        formatted_errors = "\n".join(error_messages)
        raise ManifestValidationError(
            f"Validation failed for manifest at '{source_label}':\n{formatted_errors}"
        ) from err


def load_manifest(path: str | Path) -> ComponentManifest:
    """Load, parse, and validate a component manifest from a file.

    Args:
        path: Path to the `component.yaml` file.

    Returns:
        A validated `ComponentManifest` instance.

    Raises:
        ManifestNotFoundError: If the specified file does not exist.
        ManifestParseError: If reading fails or the YAML is empty/malformed.
        ManifestValidationError: If the manifest content fails schema validation.
    """
    manifest_path = Path(path)

    if not manifest_path.is_file():
        raise ManifestNotFoundError(f"Manifest file not found: {manifest_path}")

    try:
        content = manifest_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as err:
        raise ManifestParseError(
            f"Failed to read manifest at '{manifest_path}': invalid UTF-8 encoding."
        ) from err
    except OSError as err:
        raise ManifestParseError(
            f"Failed to read manifest file at '{manifest_path}': {err}"
        ) from err

    return parse_manifest(content, source=str(manifest_path))
