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


def test_cli_does_not_execute_component_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    normalized_stdout = " ".join(result.stdout.split())
    assert "is not a file" in normalized_stdout


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


def test_create_pipeline_command(tmp_path: Path) -> None:
    """CLI test: finforge create-pipeline scaffolds pipeline and components."""
    dest = tmp_path / "pipelines"
    result = runner.invoke(
        app,
        [
            "create-pipeline",
            "fraud-detector",
            "--destination",
            str(dest),
            "--components",
            "tx-loader,risk-filter",
            "--description",
            "End-to-end fraud detection pipeline",
        ],
    )
    assert result.exit_code == 0
    assert "Created pipeline project fraud-detector" in result.stdout

    pipe_dir = dest / "fraud-detector"
    assert pipe_dir.is_dir()
    assert (pipe_dir / "pipeline.yaml").is_file()
    assert (pipe_dir / "run_pipeline.py").is_file()
    assert (pipe_dir / "README.md").is_file()
    assert (pipe_dir / "components" / "tx-loader" / "component.yaml").is_file()
    assert (pipe_dir / "components" / "risk-filter" / "component.yaml").is_file()


def test_create_component_into_pipeline_flag(tmp_path: Path) -> None:
    """CLI test: finforge create --pipeline scaffolds into <pipeline>/components."""
    pipe_dir = tmp_path / "my-pipe"
    pipe_dir.mkdir(parents=True)
    (pipe_dir / "components").mkdir()

    result = runner.invoke(
        app,
        [
            "create",
            "extra-step",
            "--pipeline",
            str(pipe_dir),
        ],
    )
    assert result.exit_code == 0
    assert (pipe_dir / "components" / "extra-step" / "component.yaml").is_file()


def test_export_mermaid_default(tmp_path: Path) -> None:
    """finforge export outputs Mermaid flowchart by default."""
    pipeline_file = tmp_path / "valid_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: test-export-pipeline
description: Pipeline for CLI export test
nodes:
  - id: step_a
    component: comp-a
    config: {}
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

    result = runner.invoke(app, ["export", str(pipeline_file)])
    assert result.exit_code == 0
    assert "flowchart LR" in result.stdout
    assert 'step_a["step_a (comp-a)"]' in result.stdout
    assert 'step_b["step_b (comp-b)"]' in result.stdout
    assert 'step_a -->|"out_a -> in_b"| step_b' in result.stdout


def test_export_dot_format(tmp_path: Path) -> None:
    """finforge export --format dot outputs valid Graphviz DOT markup."""
    pipeline_file = tmp_path / "dot_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: dot-pipeline
nodes:
  - id: n1
    component: c1
  - id: n2
    component: c2
edges:
  - source_node: n1
    source_port: p1
    destination_node: n2
    destination_port: p2
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["export", str(pipeline_file), "--format", "dot"])
    assert result.exit_code == 0
    assert 'digraph "dot-pipeline"' in result.stdout
    assert '"n1" -> "n2" [label="p1 -> p2"]' in result.stdout


def test_export_markdown_format(tmp_path: Path) -> None:
    """finforge export --format markdown generates markdown with embedded mermaid and tables."""
    pipeline_file = tmp_path / "md_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: md-pipeline
description: A markdown export test pipeline
nodes:
  - id: n1
    component: c1
    config:
      threshold: 0.5
edges: []
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["export", str(pipeline_file), "--format", "markdown"])
    assert result.exit_code == 0
    assert "# Pipeline: md-pipeline" in result.stdout
    assert "```mermaid" in result.stdout
    assert "| `n1` | `c1` | `threshold` |" in result.stdout


def test_export_to_file(tmp_path: Path) -> None:
    """finforge export --output writes visualization directly to specified file."""
    pipeline_file = tmp_path / "file_pipe.yaml"
    pipeline_file.write_text(
        """format_version: "1"
name: file-pipeline
nodes:
  - id: a
    component: comp-a
edges: []
""",
        encoding="utf-8",
    )
    out_file = tmp_path / "exported.mmd"
    result = runner.invoke(
        app,
        ["export", str(pipeline_file), "--output", str(out_file)],
    )
    assert result.exit_code == 0
    assert out_file.is_file()
    assert "flowchart LR" in out_file.read_text(encoding="utf-8")


def test_export_missing_file() -> None:
    """finforge export rejects non-existent file."""
    result = runner.invoke(app, ["export", "missing_pipeline_99999.yaml"])
    assert result.exit_code == 1
    normalized_stdout = " ".join(result.stdout.split())
    assert "does not exist" in normalized_stdout


def test_export_not_a_file(tmp_path: Path) -> None:
    """finforge export rejects directory path."""
    result = runner.invoke(app, ["export", str(tmp_path)])
    assert result.exit_code == 1
    normalized_stdout = " ".join(result.stdout.split())
    assert "is not a file" in normalized_stdout


# ---------------------------------------------------------------------------
# finforge run component & finforge run pipeline testcases
# ---------------------------------------------------------------------------


def test_run_component_basic(tmp_path: Path) -> None:
    """finforge run component executes component and produces clear output."""
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("calc-step", destination=tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "component",
            str(comp_dir),
            "--input",
            '{"input_data": [10.0, 20.0]}',
            "--config",
            '{"scale_factor": 2.5}',
        ],
    )
    assert result.exit_code == 0
    assert "FinForge Component Execution" in result.stdout
    assert "calc-step" in result.stdout
    assert "output_data" in result.stdout
    assert "25.0" in result.stdout
    assert "50.0" in result.stdout
    assert "Component Execution Succeeded" in result.stdout


def test_run_component_synthetic_inputs(tmp_path: Path) -> None:
    """finforge run component synthesizes default inputs matching manifest ports."""
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("synth-step", destination=tmp_path)
    result = runner.invoke(app, ["run", "component", str(comp_dir)])
    assert result.exit_code == 0
    assert "Component Execution Succeeded" in result.stdout
    assert "output_data" in result.stdout


def test_run_component_json_output(tmp_path: Path) -> None:
    """finforge run component --json outputs machine-readable execution result."""
    import json
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("json-step", destination=tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "component",
            str(comp_dir),
            "--input",
            '{"input_data": [5.0, 10.0]}',
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["component"] == "json-step"
    assert payload["outputs"]["output_data"] == [5.0, 10.0]
    assert "duration_ms" in payload


def test_run_component_alias(tmp_path: Path) -> None:
    """finforge run-component alias executes identically to finforge run component."""
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("alias-step", destination=tmp_path)
    result = runner.invoke(
        app,
        [
            "run-component",
            str(comp_dir),
            "--input",
            '{"input_data": [4.0]}',
        ],
    )
    assert result.exit_code == 0
    assert "Component Execution Succeeded" in result.stdout


def test_run_component_input_and_config_files(tmp_path: Path) -> None:
    """finforge run component supports --input-file and --config-file options."""
    import json
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("file-step", destination=tmp_path)
    in_file = tmp_path / "in.json"
    in_file.write_text(json.dumps({"input_data": [3.0, 6.0]}), encoding="utf-8")
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps({"scale_factor": 4.0}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            "component",
            str(comp_dir),
            "--input-file",
            str(in_file),
            "--config-file",
            str(cfg_file),
        ],
    )
    assert result.exit_code == 0
    assert "12.0" in result.stdout
    assert "24.0" in result.stdout
    assert "Component Execution Succeeded" in result.stdout


def test_run_component_missing_path() -> None:
    """finforge run component rejects nonexistent path."""
    result = runner.invoke(app, ["run", "component", "nonexistent_component_dir"])
    assert result.exit_code == 1
    normalized = " ".join(result.stdout.split())
    assert "does not exist" in normalized


def test_run_component_missing_manifest(tmp_path: Path) -> None:
    """finforge run component rejects directory lacking component.yaml."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    result = runner.invoke(app, ["run", "component", str(empty_dir)])
    assert result.exit_code == 1
    assert "component.yaml" in result.stdout


def test_run_component_contract_violation_failure(tmp_path: Path) -> None:
    """finforge run component reports clear contract error when input violates schema."""
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("bad-inputs", destination=tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "component",
            str(comp_dir),
            "--input",
            '{"input_data": "not_a_list"}',
        ],
    )
    assert result.exit_code == 1
    assert "Execution Failure" in result.stdout
    assert "ContractValidationError" in result.stdout


def test_run_component_json_error(tmp_path: Path) -> None:
    """finforge run component --json outputs structured failure json on error."""
    import json
    from finforge.sdk import create_component_project

    comp_dir = create_component_project("err-step", destination=tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "component",
            str(comp_dir),
            "--config",
            '{"scale_factor": "not_a_float"}',
            "--json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert "error" in payload


def test_run_pipeline_basic(tmp_path: Path) -> None:
    """finforge run pipeline executes pipeline with topological runtime telemetry."""
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="test-pipe",
        destination=tmp_path,
        components=["step-one"],
    )
    pipeline_file = pipe_dir / "pipeline.yaml"

    result = runner.invoke(
        app,
        [
            "run",
            "pipeline",
            str(pipeline_file),
            "--inputs",
            '{"step_one": {"input_data": [1.0, 2.0]}}',
        ],
    )
    assert result.exit_code == 0
    assert "FinForge Pipeline Execution" in result.stdout
    assert "test-pipe" in result.stdout
    assert "Pipeline Node Execution Telemetry" in result.stdout
    assert "SUCCEEDED" in result.stdout
    assert "step_one" in result.stdout
    assert "Pipeline Execution Succeeded" in result.stdout


def test_run_pipeline_directory_argument(tmp_path: Path) -> None:
    """finforge run pipeline accepts directory path containing pipeline.yaml."""
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="dir-pipe",
        destination=tmp_path,
        components=["stage-a"],
    )

    result = runner.invoke(
        app,
        [
            "run",
            "pipeline",
            str(pipe_dir),
            "--inputs",
            '{"stage_a": {"input_data": [3.0]}}',
        ],
    )
    assert result.exit_code == 0
    assert "Pipeline Execution Succeeded" in result.stdout


def test_run_pipeline_json_output(tmp_path: Path) -> None:
    """finforge run pipeline --json outputs structured pipeline execution json."""
    import json
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="pipe-json",
        destination=tmp_path,
        components=["task-a"],
    )

    result = runner.invoke(
        app,
        [
            "run",
            "pipeline",
            str(pipe_dir / "pipeline.yaml"),
            "--inputs",
            '{"task_a": {"input_data": [10.0]}}',
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["pipeline_name"] == "pipe-json"
    assert payload["status"] == "succeeded"
    assert payload["success"] is True
    assert "task_a" in payload["node_results"]
    assert payload["outputs"]["task_a"]["output_data"] == [10.0]


def test_run_pipeline_alias(tmp_path: Path) -> None:
    """finforge run-pipeline alias works identically."""
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="alias-pipe",
        destination=tmp_path,
        components=["worker"],
    )

    result = runner.invoke(
        app,
        [
            "run-pipeline",
            str(pipe_dir),
            "--inputs",
            '{"worker": {"input_data": [7.0]}}',
        ],
    )
    assert result.exit_code == 0
    assert "Pipeline Execution Succeeded" in result.stdout


def test_run_pipeline_inputs_file(tmp_path: Path) -> None:
    """finforge run pipeline accepts inputs from file via --inputs-file."""
    import json
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="inputs-file-pipe",
        destination=tmp_path,
        components=["stage-x"],
    )
    in_file = tmp_path / "pipe_in.json"
    in_file.write_text(
        json.dumps({"stage_x": {"input_data": [8.0, 9.0]}}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "run",
            "pipeline",
            str(pipe_dir),
            "--inputs-file",
            str(in_file),
        ],
    )
    assert result.exit_code == 0
    assert "Pipeline Execution Succeeded" in result.stdout


def test_run_pipeline_auto_route_inputs(tmp_path: Path) -> None:
    """finforge run pipeline auto-routes flat port inputs to matching entry node."""
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="autoroute-pipe",
        destination=tmp_path,
        components=["loader"],
    )

    # Flat port input without nesting under "loader"
    result = runner.invoke(
        app,
        [
            "run",
            "pipeline",
            str(pipe_dir),
            "--inputs",
            '{"input_data": [11.0, 12.0]}',
        ],
    )
    assert result.exit_code == 0
    assert "Pipeline Execution Succeeded" in result.stdout


def test_run_pipeline_missing_file() -> None:
    """finforge run pipeline rejects non-existent pipeline path."""
    result = runner.invoke(app, ["run", "pipeline", "nonexistent_pipe_12345.yaml"])
    assert result.exit_code == 1
    normalized = " ".join(result.stdout.split())
    assert "does not exist" in normalized


def test_run_pipeline_missing_pipeline_yaml_in_dir(tmp_path: Path) -> None:
    """finforge run pipeline rejects directory without pipeline.yaml."""
    empty_dir = tmp_path / "no_pipe_dir"
    empty_dir.mkdir()
    result = runner.invoke(app, ["run", "pipeline", str(empty_dir)])
    assert result.exit_code == 1
    assert "pipeline.yaml" in result.stdout


def test_run_pipeline_missing_required_inputs_failure(tmp_path: Path) -> None:
    """finforge run pipeline reports error when required inputs are omitted."""
    from finforge.sdk import create_pipeline_project

    pipe_dir = create_pipeline_project(
        name="missing-inputs-pipe",
        destination=tmp_path,
        components=["needs-input"],
    )

    # No --inputs supplied, but component requires input_data
    result = runner.invoke(app, ["run", "pipeline", str(pipe_dir)])
    assert result.exit_code == 1
    assert "Pipeline Execution Failed" in result.stdout
    assert "Missing required input" in result.stdout



