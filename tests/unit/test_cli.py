"""Unit tests for the FinForge AI command-line interface."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from finforge.cli import app
from finforge.cli.main import get_version
from finforge.component import BaseComponent
from finforge.manifest import load_manifest

runner = CliRunner()


def test_root_help() -> None:
    """1. Root --help displays usage and available commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage: finforge" in result.stdout
    assert "create" in result.stdout


def test_version_command() -> None:
    """2. --version displays installed version and exits."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "FinForge AI version" in result.stdout


def test_create_command_generates_component(tmp_path: Path) -> None:
    """3 & 4. finforge create generates expected component files."""
    dest = tmp_path / "components"
    result = runner.invoke(
        app,
        ["create", "sample-model", "--destination", str(dest)],
    )
    assert result.exit_code == 0
    assert "Created component sample-model" in result.stdout

    project_dir = dest / "sample-model"
    assert (project_dir / "component.yaml").is_file()
    assert (project_dir / "pyproject.toml").is_file()
    assert (project_dir / "README.md").is_file()
    assert (project_dir / "src" / "sample_model" / "__init__.py").is_file()
    assert (project_dir / "src" / "sample_model" / "component.py").is_file()
    assert (project_dir / "tests" / "test_component.py").is_file()
    assert (project_dir / "examples" / "basic_usage.py").is_file()


def test_custom_destination_and_metadata_options(tmp_path: Path) -> None:
    """5, 6, 7 & 8. Custom destination, description, category, and version options."""
    dest = tmp_path / "custom_dir"
    result = runner.invoke(
        app,
        [
            "create",
            "rag-evaluator",
            "--destination",
            str(dest),
            "--description",
            "Custom RAG evaluation engine.",
            "--category",
            "evaluation",
            "--version",
            "1.2.0",
            "--author",
            "FinForge Core Team",
        ],
    )
    assert result.exit_code == 0

    project_dir = dest / "rag-evaluator"
    manifest = load_manifest(project_dir / "component.yaml")
    assert manifest.name == "rag-evaluator"
    assert manifest.description == "Custom RAG evaluation engine."
    assert manifest.category == "evaluation"
    assert manifest.version == "1.2.0"

    readme = (project_dir / "README.md").read_text(encoding="utf-8")
    assert "FinForge Core Team" in readme


def test_invalid_component_name_rejected(tmp_path: Path) -> None:
    """9. Invalid component names produce clear errors and non-zero exit."""
    result = runner.invoke(
        app,
        ["create", "Invalid Name!", "--destination", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "Error:" in result.stdout


def test_existing_destination_rejected(tmp_path: Path) -> None:
    """10. Existing destination directory is not overwritten."""
    existing_dir = tmp_path / "conflict-comp"
    existing_dir.mkdir(parents=True)
    sentinel = existing_dir / "sentinel.txt"
    sentinel.write_text("DO_NOT_TOUCH", encoding="utf-8")

    result = runner.invoke(
        app,
        ["create", "conflict-comp", "--destination", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "Destination already exists" in result.stdout or "Error:" in result.stdout
    assert sentinel.read_text(encoding="utf-8") == "DO_NOT_TOUCH"


def test_missing_destination_created(tmp_path: Path) -> None:
    """11. Missing parent destination directory is created automatically."""
    deep_dest = tmp_path / "nested" / "subfolder" / "components"
    result = runner.invoke(
        app,
        ["create", "deep-comp", "--destination", str(deep_dest)],
    )
    assert result.exit_code == 0
    assert (deep_dest / "deep-comp" / "component.yaml").is_file()


def test_sdk_exceptions_produce_clean_errors(tmp_path: Path) -> None:
    """12. SDK exceptions produce user-friendly terminal output without tracebacks."""
    result = runner.invoke(
        app,
        [
            "create",
            "bad-cat",
            "--destination",
            str(tmp_path),
            "--category",
            "non-existent-cat",
        ],
    )
    assert result.exit_code != 0
    assert "Error:" in result.stdout
    assert "Traceback" not in result.stdout


def test_interactive_name_prompt(tmp_path: Path) -> None:
    """13. Interactive prompt supplies component name when omitted."""
    result = runner.invoke(
        app,
        ["create", "--destination", str(tmp_path)],
        input="prompted-comp\n",
    )
    assert result.exit_code == 0
    assert (tmp_path / "prompted-comp" / "component.yaml").is_file()


def test_interactive_name_empty_rejected(tmp_path: Path) -> None:
    """13b. Empty interactive prompt is rejected with error."""
    result = runner.invoke(
        app,
        ["create", "--destination", str(tmp_path)],
        input="\n",
    )
    assert result.exit_code != 0
    assert "Component name is required" in result.stdout


def test_cli_does_not_execute_component_code(tmp_path: Path, monkeypatch) -> None:
    """14. Component creation does not execute setup() or run()."""

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("Component execution method invoked during CLI create!")

    monkeypatch.setattr(BaseComponent, "setup", boom)
    monkeypatch.setattr(BaseComponent, "run", boom)

    result = runner.invoke(
        app,
        ["create", "safe-cli-comp", "--destination", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert (tmp_path / "safe-cli-comp" / "component.yaml").is_file()


def test_cli_delegates_to_sdk(tmp_path: Path) -> None:
    """15. CLI delegates directly to create_component_project without duplication."""
    with patch(
        "finforge.cli.commands.create.create_component_project",
        autospec=True,
    ) as mock_create:
        mock_create.return_value = tmp_path / "mocked-comp"
        result = runner.invoke(
            app,
            [
                "create",
                "mocked-comp",
                "--destination",
                str(tmp_path),
                "--category",
                "rag",
            ],
        )
        assert result.exit_code == 0
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["name"] == "mocked-comp"
        assert call_kwargs["category"] == "rag"


def test_cli_unexpected_error_handling(tmp_path: Path) -> None:
    """Verify unexpected non-FinForge exceptions produce clean error messages."""
    with patch(
        "finforge.cli.commands.create.create_component_project",
        side_effect=RuntimeError("Disk corrupted"),
    ):
        result = runner.invoke(
            app,
            ["create", "corrupt-comp", "--destination", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "Unexpected error:" in result.stdout
        assert "Disk corrupted" in result.stdout


def test_get_version_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_version fallback logic when package metadata is missing."""

    def raise_not_found(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", raise_not_found)
    assert get_version() == "0.1.0.dev0"


def test_inspect_valid_pipeline(tmp_path: Path) -> None:
    """finforge inspect displays pipeline topology, nodes, connections, and ordering."""
    pipeline_file = tmp_path / "valid_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: test-cli-pipeline
description: Pipeline for CLI inspection test
nodes:
  - id: step_a
    component: comp-a
    config:
      param1: 10
  - id: step_b
    component: comp-b
    config: {}
edges:
  - source_node: step_a
    source_port: out_a
    destination_node: step_b
    destination_port: in_b
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inspect", str(pipeline_file)])
    assert result.exit_code == 0
    assert "test-cli-pipeline" in result.stdout
    assert "step_a" in result.stdout
    assert "step_b" in result.stdout
    assert "comp-a" in result.stdout
    assert "comp-b" in result.stdout
    assert "step_a.out_a" in result.stdout
    assert "step_b.in_b" in result.stdout
    assert "step_a -> step_b" in result.stdout


def test_inspect_as_json(tmp_path: Path) -> None:
    """finforge inspect --json outputs machine-readable JSON."""
    import json

    pipeline_file = tmp_path / "valid_json_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: json-pipeline
nodes:
  - id: n1
    component: c1
    config: {}
edges: []
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inspect", str(pipeline_file), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["name"] == "json-pipeline"
    assert parsed["topological_ordering"] == ["n1"]


def test_inspect_missing_file() -> None:
    """finforge inspect rejects non-existent file path."""
    result = runner.invoke(app, ["inspect", "nonexistent_file_12345.yaml"])
    assert result.exit_code == 1
    normalized_stdout = " ".join(result.stdout.split())
    assert "does not exist" in normalized_stdout


def test_inspect_not_a_file(tmp_path: Path) -> None:
    """finforge inspect rejects directory path."""
    result = runner.invoke(app, ["inspect", str(tmp_path)])
    assert result.exit_code == 1
    assert "is not a file" in result.stdout


def test_inspect_malformed_yaml(tmp_path: Path) -> None:
    """finforge inspect rejects malformed or invalid pipeline YAML."""
    corrupt = tmp_path / "corrupt.yaml"
    corrupt.write_text("invalid: yaml: [unclosed", encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(corrupt)])
    assert result.exit_code == 1
    assert "Failed to inspect pipeline" in result.stdout


def test_inspect_cycle_detected(tmp_path: Path) -> None:
    """finforge inspect rejects pipeline with directed cycle."""
    cycle_pipe = tmp_path / "cycle.yaml"
    cycle_pipe.write_text(
        """format_version: "1"
name: cyclic-pipeline
nodes:
  - id: a
    component: comp-a
    config: {}
  - id: b
    component: comp-b
    config: {}
edges:
  - source_node: a
    source_port: out
    destination_node: b
    destination_port: in
  - source_node: b
    source_port: out
    destination_node: a
    destination_port: in
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inspect", str(cycle_pipe)])
    assert result.exit_code == 1
    assert "Directed cycle detected" in result.stdout
