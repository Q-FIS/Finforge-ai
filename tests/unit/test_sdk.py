"""Unit tests for FinForge Component SDK utilities and project scaffolding."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from finforge.component import BaseComponent
from finforge.exceptions import (
    DestinationExistsError,
    InvalidIdentifierError,
    ProjectGenerationError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from finforge.manifest import load_manifest
from finforge.sdk import (
    create_component_project,
    normalize_component_name,
    to_class_name,
    to_package_name,
)
from finforge.sdk.template import render_template_string


def test_valid_component_name_accepted() -> None:
    """1. Valid component names are accepted and normalized."""
    assert normalize_component_name("custom-kmeans") == "custom-kmeans"
    assert normalize_component_name("my_rag_agent") == "my_rag_agent"
    assert normalize_component_name("  simple-model  ") == "simple-model"
    assert normalize_component_name("text2vec") == "text2vec"


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "-leading-hyphen",
        "trailing-hyphen-",
        "_leading_underscore",
        "trailing_underscore_",
        "has spaces",
        "special@char",
        "has.dot",
        "../traversal",
        "/absolute/path",
        "has\\backslash",
    ],
)
def test_invalid_component_name_rejected(invalid_name: str) -> None:
    """2. Invalid component names are rejected with InvalidIdentifierError."""
    with pytest.raises(InvalidIdentifierError):
        normalize_component_name(invalid_name)


def test_package_name_normalization() -> None:
    """3. Component names are converted to valid Python package names."""
    assert to_package_name("custom-kmeans") == "custom_kmeans"
    assert to_package_name("my-rag-agent") == "my_rag_agent"
    assert to_package_name("simple_model") == "simple_model"

    # Digits at beginning are invalid Python identifiers
    with pytest.raises(InvalidIdentifierError):
        to_package_name("123-kmeans")

    # Python keywords are invalid
    with pytest.raises(InvalidIdentifierError):
        to_package_name("class")


def test_class_name_normalization() -> None:
    """4. Component names are converted to valid PascalCase class names."""
    assert to_class_name("custom-kmeans") == "CustomKmeansComponent"
    assert to_class_name("my_rag_agent") == "MyRagAgentComponent"
    assert to_class_name("text-processor-component") == "TextProcessorComponent"
    assert to_class_name("custom-kmeans", suffix="") == "CustomKmeans"

    # Python keywords or invalid identifiers rejected
    with pytest.raises(InvalidIdentifierError):
        to_class_name("123-invalid")


def test_template_variables_replaced_correctly() -> None:
    """5. Template variable substitution works as expected."""
    template = "Component: {{ component_name }}, Package: {{ package_name }}"
    context = {"component_name": "alpha", "package_name": "alpha_pkg"}
    result = render_template_string(template, context)
    assert result == "Component: alpha, Package: alpha_pkg"


def test_generated_project_has_expected_files(tmp_path: Path) -> None:
    """6. Generated project contains all required files and directories."""
    project_dir = create_component_project(
        name="test-component",
        destination=tmp_path,
        description="A test component.",
        category="data-processing",
        author="FinForge Tester",
    )

    expected_files = [
        project_dir / "component.yaml",
        project_dir / "pyproject.toml",
        project_dir / "README.md",
        project_dir / "src" / "test_component" / "__init__.py",
        project_dir / "src" / "test_component" / "component.py",
        project_dir / "tests" / "test_component.py",
        project_dir / "examples" / "basic_usage.py",
    ]

    for expected_path in expected_files:
        assert expected_path.is_file(), f"Missing file: {expected_path}"


def test_generated_component_imports_and_inherits(tmp_path: Path) -> None:
    """7 & 8. Generated component imports correctly and inherits BaseComponent."""
    project_dir = create_component_project(
        name="import-test",
        destination=tmp_path,
        category="machine-learning",
    )

    src_dir = str(project_dir / "src")
    sys.path.insert(0, src_dir)
    try:
        mod = importlib.import_module("import_test.component")
        cls = mod.ImportTestComponent
        assert issubclass(cls, BaseComponent)

        # Verify instance creation
        instance = cls()
        assert isinstance(instance, BaseComponent)
    finally:
        sys.path.remove(src_dir)
        sys.modules.pop("import_test.component", None)
        sys.modules.pop("import_test", None)


def test_generated_manifest_passes_parser(tmp_path: Path) -> None:
    """9. Generated component.yaml parses cleanly with FF-02 manifest parser."""
    project_dir = create_component_project(
        name="manifest-test",
        destination=tmp_path,
        category="rag",
        version="0.2.1",
        description="Manifest verification component.",
    )

    manifest_path = project_dir / "component.yaml"
    manifest = load_manifest(manifest_path)

    assert manifest.name == "manifest-test"
    assert manifest.category == "rag"
    assert manifest.version == "0.2.1"
    assert manifest.api_version == "1"
    assert manifest.entrypoint == "manifest_test.component:ManifestTestComponent"
    assert "input_data" in manifest.inputs
    assert "output_data" in manifest.outputs


def test_generated_component_tests_pass(tmp_path: Path) -> None:
    """10. Generated component test suite executes and passes cleanly."""
    project_dir = create_component_project(
        name="unit-tester",
        destination=tmp_path,
    )

    src_dir = str(project_dir / "src")
    sys.path.insert(0, src_dir)
    try:
        # Import the generated test module and execute its test functions
        import importlib.util

        test_file = project_dir / "tests" / "test_component.py"
        spec = importlib.util.spec_from_file_location(
            "generated_test_component", test_file
        )
        assert spec is not None and spec.loader is not None
        test_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_mod)

        # Run each test function
        test_mod.test_component_inheritance()
        test_mod.test_component_lifecycle_execution()
        test_mod.test_invalid_configuration_rejected()
        test_mod.test_invalid_input_rejected()
    finally:
        sys.path.remove(src_dir)
        sys.modules.pop("unit_tester.component", None)
        sys.modules.pop("unit_tester", None)
        sys.modules.pop("generated_test_component", None)


def test_existing_destination_is_not_overwritten(tmp_path: Path) -> None:
    """11 & 12. Existing destination is rejected and existing files are unchanged."""
    existing_dir = tmp_path / "collision-test"
    existing_dir.mkdir(parents=True)
    sentinel_file = existing_dir / "sentinel.txt"
    sentinel_file.write_text("DO_NOT_OVERWRITE", encoding="utf-8")

    with pytest.raises(DestinationExistsError) as excinfo:
        create_component_project(
            name="collision-test",
            destination=tmp_path,
        )

    assert "already exists" in str(excinfo.value)
    # File content must remain completely unchanged
    assert sentinel_file.read_text(encoding="utf-8") == "DO_NOT_OVERWRITE"


def test_path_traversal_attempts_are_rejected(tmp_path: Path) -> None:
    """13. Path traversal attempts are rejected safely."""
    # Slash or parent directory in name
    with pytest.raises(InvalidIdentifierError):
        create_component_project(
            name="../escaped",
            destination=tmp_path,
        )

    with pytest.raises(InvalidIdentifierError):
        create_component_project(
            name="sub/escaped",
            destination=tmp_path,
        )


def test_invalid_template_variables_rejected() -> None:
    """14. Missing template variables raise TemplateRenderError."""
    template = "Hello {{ missing_var }}"
    with pytest.raises(TemplateRenderError) as excinfo:
        render_template_string(template, {"known_var": "val"})
    assert "missing_var" in str(excinfo.value)


def test_generated_yaml_is_valid(tmp_path: Path) -> None:
    """15. Generated YAML manifest is well-formed YAML."""
    project_dir = create_component_project(
        name="yaml-validator",
        destination=tmp_path,
    )
    raw_yaml = (project_dir / "component.yaml").read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw_yaml)
    assert isinstance(parsed, dict)
    assert parsed["name"] == "yaml-validator"


def test_generated_toml_is_valid(tmp_path: Path) -> None:
    """16. Generated pyproject.toml is well-formed TOML."""
    project_dir = create_component_project(
        name="toml-validator",
        destination=tmp_path,
        author="Ada Lovelace",
    )
    raw_toml = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(raw_toml)
    assert isinstance(parsed, dict)
    assert parsed["project"]["name"] == "toml-validator"
    assert parsed["project"]["authors"][0]["name"] == "Ada Lovelace"


def test_generated_readme_details(tmp_path: Path) -> None:
    """17. Generated README contains accurate component information."""
    project_dir = create_component_project(
        name="readme-test",
        destination=tmp_path,
        description="Custom documentation test.",
        category="llm",
        author="Grace Hopper",
    )
    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert "# readme-test" in readme
    assert "Custom documentation test." in readme
    assert "Grace Hopper" in readme
    assert "`llm`" in readme
    assert "readme_test.component:ReadmeTestComponent" in readme


def test_template_generation_does_not_execute_component_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """18. Component generation does not instantiate or execute component methods."""

    # Monkeypatch BaseComponent setup and run to detect any execution
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Component lifecycle code was executed during scaffolding!"
        )

    monkeypatch.setattr(BaseComponent, "setup", boom)
    monkeypatch.setattr(BaseComponent, "run", boom)

    # Scaffolding must complete with zero execution
    project_dir = create_component_project(
        name="safe-scaffold",
        destination=tmp_path,
    )
    assert (project_dir / "component.yaml").is_file()


def test_invalid_category_and_version(tmp_path: Path) -> None:
    """Verify invalid category and version format are rejected."""
    with pytest.raises(ProjectGenerationError) as exc_cat:
        create_component_project(
            name="cat-test",
            destination=tmp_path,
            category="unsupported-cat",
        )
    assert "Unsupported category" in str(exc_cat.value)

    with pytest.raises(ProjectGenerationError) as exc_ver:
        create_component_project(
            name="ver-test",
            destination=tmp_path,
            version="invalid.version.format!!!",
        )
    assert "Invalid version format" in str(exc_ver.value)


def test_missing_template_dir(tmp_path: Path) -> None:
    """Verify non-existent template directory raises TemplateNotFoundError."""
    with pytest.raises(TemplateNotFoundError):
        create_component_project(
            name="tpl-test",
            destination=tmp_path,
            template_dir=tmp_path / "non_existent_template",
        )


def test_normalization_and_generator_type_validation(tmp_path: Path) -> None:
    """Verify non-string inputs to normalization and generator raise errors."""
    with pytest.raises(InvalidIdentifierError):
        normalize_component_name(123)  # type: ignore[arg-type]

    with pytest.raises(InvalidIdentifierError):
        to_package_name(None)  # type: ignore[arg-type]

    with pytest.raises(InvalidIdentifierError):
        to_package_name("___")

    with pytest.raises(InvalidIdentifierError):
        to_class_name(456)  # type: ignore[arg-type]

    with pytest.raises(InvalidIdentifierError):
        to_class_name("---")

    with pytest.raises(ProjectGenerationError):
        create_component_project(
            name="type-test",
            destination=tmp_path,
            package_name=123,  # type: ignore[arg-type]
        )

    with pytest.raises(ProjectGenerationError):
        create_component_project(
            name="type-test-2",
            destination=tmp_path,
            class_name=456,  # type: ignore[arg-type]
        )


def test_custom_package_and_class_names(tmp_path: Path) -> None:
    """Verify explicit package_name and class_name parameters work."""
    project_dir = create_component_project(
        name="custom-naming",
        destination=tmp_path,
        package_name="bespoke_pkg",
        class_name="BespokeComponent",
    )
    manifest = load_manifest(project_dir / "component.yaml")
    assert manifest.entrypoint == "bespoke_pkg.component:BespokeComponent"
    assert (project_dir / "src" / "bespoke_pkg" / "component.py").is_file()


def test_template_env_var_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify FINFORGE_TEMPLATE_DIR environment variable is respected."""
    from finforge.sdk.template import get_default_template_dir

    custom_tpl = tmp_path / "custom_tpl"
    custom_tpl.mkdir(parents=True)
    monkeypatch.setenv("FINFORGE_TEMPLATE_DIR", str(custom_tpl))
    assert get_default_template_dir() == custom_tpl.resolve()


def test_cleanup_on_generation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify partial directory is cleaned up if file writing fails."""

    # Monkeypatch render_template_string to raise on a specific condition
    def failing_render(raw_text: str, context: dict[str, Any]) -> str:
        if "scale_factor" in raw_text:
            raise RuntimeError("Disk write simulation failure")
        return raw_text

    monkeypatch.setattr("finforge.sdk.generator.render_template_string", failing_render)

    with pytest.raises(RuntimeError):
        create_component_project(
            name="fail-cleanup",
            destination=tmp_path,
        )

    # Directory must have been cleaned up
    assert not (tmp_path / "fail-cleanup").exists()
