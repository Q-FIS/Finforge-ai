"""Comprehensive unit tests for component manifest parsing and validation."""

from pathlib import Path

import pytest

from finforge.exceptions import (
    ManifestNotFoundError,
    ManifestParseError,
    ManifestValidationError,
)
from finforge.manifest import ComponentManifest, load_manifest, parse_manifest

VALID_MANIFEST_YAML = """
name: custom-kmeans
version: "0.1.0"
description: K-Means clustering implemented from scratch

api_version: "1"
category: machine-learning

entrypoint: my_kmeans.component:KMeansComponent

inputs:
  data:
    type: array
    required: true

outputs:
  labels:
    type: array

config:
  n_clusters:
    type: integer
    default: 3

dependencies:
  - numpy>=2.0
"""


def test_valid_manifest_loads_successfully() -> None:
    """1. Valid manifest loads and parses into ComponentManifest object."""
    manifest = parse_manifest(VALID_MANIFEST_YAML)
    assert isinstance(manifest, ComponentManifest)
    assert manifest.name == "custom-kmeans"
    assert manifest.version == "0.1.0"
    assert manifest.description == "K-Means clustering implemented from scratch"
    assert manifest.api_version == "1"
    assert manifest.category == "machine-learning"
    assert manifest.entrypoint == "my_kmeans.component:KMeansComponent"
    assert "data" in manifest.inputs
    assert manifest.inputs["data"].type == "array"
    assert manifest.inputs["data"].required is True
    assert "labels" in manifest.outputs
    assert manifest.outputs["labels"].type == "array"
    assert "n_clusters" in manifest.config
    assert manifest.config["n_clusters"].type == "integer"
    assert manifest.config["n_clusters"].default == 3
    assert manifest.dependencies == ["numpy>=2.0"]


@pytest.mark.parametrize(
    "missing_field",
    ["name", "version", "description", "category", "entrypoint"],
)
def test_missing_required_fields_are_rejected(missing_field: str) -> None:
    """2. Missing required metadata fields are rejected with ManifestValidationError."""
    lines = [
        line
        for line in VALID_MANIFEST_YAML.splitlines()
        if not line.startswith(f"{missing_field}:")
    ]
    incomplete_yaml = "\n".join(lines)
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(incomplete_yaml)
    assert missing_field in str(excinfo.value)


def test_empty_yaml_is_rejected() -> None:
    """3. Empty YAML is rejected with ManifestParseError."""
    with pytest.raises(ManifestParseError) as exc_empty:
        parse_manifest("")
    assert "is empty" in str(exc_empty.value)

    with pytest.raises(ManifestParseError) as exc_whitespace:
        parse_manifest("   \n   \t  \n  ")
    assert "is empty" in str(exc_whitespace.value)


def test_malformed_yaml_is_rejected() -> None:
    """4. Malformed YAML syntax is rejected with ManifestParseError."""
    bad_yaml = """
    name: test
    version: 0.1.0
      indented_incorrectly: true
    """
    with pytest.raises(ManifestParseError) as excinfo:
        parse_manifest(bad_yaml)
    assert "Malformed YAML" in str(excinfo.value)


@pytest.mark.parametrize(
    "non_mapping_content",
    [
        "- item1\n- item2\n- item3",
        "just a single string",
        "12345",
        "true",
    ],
)
def test_non_mapping_yaml_is_rejected(non_mapping_content: str) -> None:
    """5. Non-mapping YAML documents are rejected with ManifestParseError."""
    with pytest.raises(ManifestParseError) as excinfo:
        parse_manifest(non_mapping_content)
    assert "must be a YAML mapping" in str(excinfo.value)


@pytest.mark.parametrize(
    "bad_name",
    [
        "Custom-KMeans",  # uppercase
        "custom kmeans",  # space
        "-custom-kmeans",  # leading dash
        "custom-kmeans-",  # trailing dash
        "_custom",  # leading underscore
        "custom@name",  # special character
        "",  # empty
    ],
)
def test_invalid_component_names_are_rejected(bad_name: str) -> None:
    """6. Invalid component names are rejected."""
    yaml_content = VALID_MANIFEST_YAML.replace(
        "name: custom-kmeans", f"name: '{bad_name}'"
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(yaml_content)
    assert "name" in str(excinfo.value)


@pytest.mark.parametrize(
    "bad_version",
    [
        "not_a_version",
        "abc.xyz",
        "1.0.0-invalid!!",
        "-1.0",
        "",
    ],
)
def test_invalid_version_strings_are_rejected(bad_version: str) -> None:
    """7. Invalid version strings are rejected."""
    yaml_content = VALID_MANIFEST_YAML.replace(
        'version: "0.1.0"', f"version: '{bad_version}'"
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(yaml_content)
    assert "version" in str(excinfo.value)


@pytest.mark.parametrize(
    "bad_entrypoint",
    [
        "no_colon_entrypoint",
        ":MissingModule",
        "missing_class:",
        "invalid-module.name:Class",
        "module:123InvalidClass",
        "mod ule:Class",
        "module:Class:extra",
    ],
)
def test_invalid_entrypoints_are_rejected(bad_entrypoint: str) -> None:
    """8. Invalid entrypoints are rejected."""
    yaml_content = VALID_MANIFEST_YAML.replace(
        "entrypoint: my_kmeans.component:KMeansComponent",
        f"entrypoint: '{bad_entrypoint}'",
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(yaml_content)
    assert "entrypoint" in str(excinfo.value)


def test_unsupported_port_types_are_rejected() -> None:
    """9. Unsupported port types are rejected."""
    bad_yaml = VALID_MANIFEST_YAML.replace("type: array", "type: quantum_state")
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_yaml)
    assert "Unsupported port type 'quantum_state'" in str(excinfo.value)


def test_invalid_configuration_definitions_are_rejected() -> None:
    """10. Invalid configuration definitions are rejected."""
    # Bad config type
    bad_type = VALID_MANIFEST_YAML.replace("type: integer", "type: imaginary_number")
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_type)
    assert "Unsupported config type 'imaginary_number'" in str(excinfo.value)

    # Incompatible default value (default string for integer type)
    bad_default = VALID_MANIFEST_YAML.replace("default: 3", "default: 'three'")
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_default)
    assert "not an integer for config type 'integer'" in str(excinfo.value)


def test_invalid_dependencies_are_rejected() -> None:
    """11. Invalid dependencies are rejected."""
    bad_dep_yaml = VALID_MANIFEST_YAML.replace("- numpy>=2.0", "- '>>numpy'")
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_dep_yaml)
    assert "Invalid dependency specification" in str(excinfo.value)


def test_unknown_fields_are_rejected() -> None:
    """12. Unknown fields at top level or nested definitions are rejected."""
    # Unknown top-level field
    bad_top_level = VALID_MANIFEST_YAML + "\nextra_field: unexpected_value\n"
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_top_level)
    assert "extra_field" in str(excinfo.value)

    # Unknown field inside port definition
    bad_port = VALID_MANIFEST_YAML.replace(
        "type: array\n    required: true",
        "type: array\n    required: true\n    magic_property: true",
    )
    with pytest.raises(ManifestValidationError) as excinfo:
        parse_manifest(bad_port)
    assert "magic_property" in str(excinfo.value)


def test_missing_manifest_file_produces_not_found_error(tmp_path: Path) -> None:
    """13. Missing manifest file produces ManifestNotFoundError."""
    non_existent = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ManifestNotFoundError) as excinfo:
        load_manifest(non_existent)
    assert "Manifest file not found" in str(excinfo.value)


def test_parsing_does_not_import_or_execute_entrypoint() -> None:
    """14. Parsing does not import or execute the component entrypoint."""
    # Point entrypoint to completely non-existent modules or malicious paths
    yaml_with_fake_module = VALID_MANIFEST_YAML.replace(
        "entrypoint: my_kmeans.component:KMeansComponent",
        "entrypoint: completely_fake_module_123.deep.path:FakeComponent",
    )
    # Must succeed without attempting to import
    manifest = parse_manifest(yaml_with_fake_module)
    assert manifest.entrypoint == "completely_fake_module_123.deep.path:FakeComponent"


def test_valid_input_output_definitions_preserved() -> None:
    """15. Valid input/output definitions are preserved correctly."""
    manifest = parse_manifest(VALID_MANIFEST_YAML)
    assert manifest.inputs["data"].type == "array"
    assert manifest.inputs["data"].required is True
    assert manifest.outputs["labels"].type == "array"
    assert manifest.outputs["labels"].required is True  # default


def test_valid_defaults_and_dependencies_preserved() -> None:
    """16. Valid defaults and dependencies are preserved correctly."""
    manifest = parse_manifest(VALID_MANIFEST_YAML)
    assert manifest.config["n_clusters"].default == 3
    assert manifest.dependencies == ["numpy>=2.0"]


def test_load_manifest_from_file(tmp_path: Path) -> None:
    """Verify load_manifest works with actual file paths."""
    file_path = tmp_path / "component.yaml"
    file_path.write_text(VALID_MANIFEST_YAML, encoding="utf-8")
    manifest = load_manifest(file_path)
    assert manifest.name == "custom-kmeans"


def test_load_manifest_invalid_encoding(tmp_path: Path) -> None:
    """Verify load_manifest raises ManifestParseError on non-UTF-8 bytes."""
    bad_file = tmp_path / "bad_encoding.yaml"
    bad_file.write_bytes(b"\x80\x81\x82 invalid non-utf8 bytes")
    with pytest.raises(ManifestParseError) as excinfo:
        load_manifest(bad_file)
    assert "invalid UTF-8 encoding" in str(excinfo.value)


def test_example_kmeans_manifest_loads_cleanly() -> None:
    """Verify example manifest at components/examples/custom_kmeans loads cleanly."""
    example_path = Path("components/examples/custom_kmeans/component.yaml")
    assert example_path.is_file()
    manifest = load_manifest(example_path)
    assert manifest.name == "custom-kmeans"
    assert manifest.category == "machine-learning"
    assert "data" in manifest.inputs
    assert "labels" in manifest.outputs
    assert "centroids" in manifest.outputs
    assert manifest.config["n_clusters"].default == 3
    assert manifest.config["max_iter"].default == 300
    assert manifest.config["tol"].default == 0.0001
    assert manifest.dependencies == ["numpy>=2.0.0"]
