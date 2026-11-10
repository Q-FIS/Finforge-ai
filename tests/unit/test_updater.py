"""Comprehensive unit and integration tests for FinForge manifest updater (FF-UPDATE).

Tests cover:
  - AST code analysis of component implementation (setup, run, docstrings)
  - Extraction and inference of input ports, output ports, config options, and types
  - Automatic synchronization of component.yaml with implementation updates
  - Preservation of rich descriptions, categories, and custom port metadata
  - AST code analysis of pipeline builder scripts (Pipeline.add, Pipeline.connect)
  - Automatic synchronization of pipeline.yaml with Python scripts and local components
  - Dry-run mode and check mode verification
  - CLI commands: finforge update, finforge update-component, finforge update-pipeline
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from finforge.cli import app
from finforge.manifest import load_manifest
from finforge.pipeline.serialization import load_pipeline_document
from finforge.sdk.generator import create_component_project, create_pipeline_project
from finforge.sdk.updater import (
    ComponentCodeAnalyzer,
    PipelineCodeAnalyzer,
    update_component,
    update_pipeline,
)

runner = CliRunner()


# -----------------------------------------------------------------------------
# Component Code Analysis & Update Tests
# -----------------------------------------------------------------------------


def test_component_code_analyzer_extracts_class_and_entrypoint(tmp_path: Path) -> None:
    """Analyzer extracts class name, docstring, and entrypoint path."""
    comp_dir = create_component_project("custom-analyzer", destination=tmp_path)
    analyzer = ComponentCodeAnalyzer(comp_dir)
    meta = analyzer.analyze()

    assert meta["name"] == "custom-analyzer"
    assert meta["entrypoint"] == "custom_analyzer.component:CustomAnalyzerComponent"
    assert "custom-analyzer component" in meta["description"].lower()


def test_component_code_analyzer_detects_inputs_outputs_config(tmp_path: Path) -> None:
    """Analyzer inspects setup() and run() methods to detect ports and config."""
    comp_dir = tmp_path / "mock-comp"
    src_dir = comp_dir / "src" / "mock_comp"
    src_dir.mkdir(parents=True)

    py_code = """\"\"\"Implementation of MockCustomComponent.\"\"\"
from typing import Any
from finforge.component import BaseComponent

class MockCustomComponent(BaseComponent):
    \"\"\"Custom mathematical transformation component.

    Inputs:
        raw_values: Primary numerical list to transform.
        weights (array): Optional weighting factors.
    Outputs:
        transformed: Normalized output array.
        metric: Calculated aggregate summary score.
    Config:
        learning_rate (float): Step size for calculation.
        enable_logging (bool): Whether to log intermediate steps.
    \"\"\"

    def setup(self, config: dict[str, Any]) -> None:
        self.lr = config.get("learning_rate", 0.05)
        self.log = config.get("enable_logging", True)
        self.iterations = config.get("iterations", 50)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if "raw_values" not in inputs:
            raise ValueError("raw_values is mandatory")
        weights = inputs.get("weights")
        return {
            "transformed": [1.0, 2.0, 3.0],
            "metric": 42.0,
        }
"""
    (src_dir / "component.py").write_text(py_code, encoding="utf-8")
    (src_dir / "__init__.py").touch()

    analyzer = ComponentCodeAnalyzer(comp_dir)
    meta = analyzer.analyze()

    assert meta["name"] == "mock-custom"
    assert meta["entrypoint"] == "mock_comp.component:MockCustomComponent"
    assert "learning_rate" in meta["config"]
    assert meta["config"]["learning_rate"]["type"] == "float"
    assert meta["config"]["learning_rate"]["default"] == 0.05
    assert meta["config"]["enable_logging"]["type"] == "boolean"
    assert meta["config"]["enable_logging"]["default"] is True
    assert meta["config"]["iterations"]["type"] == "integer"
    assert meta["config"]["iterations"]["default"] == 50

    # Inputs
    assert "raw_values" in meta["inputs"]
    assert meta["inputs"]["raw_values"]["required"] is True
    assert "weights" in meta["inputs"]
    assert meta["inputs"]["weights"]["required"] is False

    # Outputs
    assert "transformed" in meta["outputs"]
    assert meta["outputs"]["transformed"]["type"] == "array"
    assert "metric" in meta["outputs"]
    assert meta["outputs"]["metric"]["type"] == "float"


def test_update_component_manifest_syncs_new_ports_and_config(tmp_path: Path) -> None:
    """update_component writes updated component.yaml reflecting added ports."""
    comp_dir = create_component_project("sync-comp", destination=tmp_path)
    comp_py = comp_dir / "src" / "sync_comp" / "component.py"

    # Modify component code: add new config 'alpha' and new output 'diagnostics'
    updated_py = """from typing import Any
from finforge.component import BaseComponent

class SyncCompComponent(BaseComponent):
    \"\"\"Updated sync component docstring.\"\"\"

    def setup(self, config: dict[str, Any]) -> None:
        self.scale = config.get("scale_factor", 2.5)
        self.alpha = config.get("alpha", 0.01)

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if "input_data" not in inputs:
            raise ValueError("Missing input_data")
        raw = inputs["input_data"]
        return {
            "output_data": [x * self.scale for x in raw],
            "diagnostics": {"processed_count": len(raw)},
        }
"""
    comp_py.write_text(updated_py, encoding="utf-8")

    result = update_component(comp_dir)
    assert result.error is None
    assert result.is_updated is True
    assert result.manifest is not None

    # Verify manifest file on disk
    manifest = load_manifest(comp_dir / "component.yaml")
    assert manifest.name == "sync-comp"
    # Config alpha added, scale_factor updated default
    assert "alpha" in manifest.config
    assert manifest.config["alpha"].default == 0.01
    assert manifest.config["scale_factor"].default == 2.5
    # Output diagnostics added
    assert "diagnostics" in manifest.outputs
    assert "output_data" in manifest.outputs


def test_update_component_preserves_custom_descriptions(tmp_path: Path) -> None:
    """update_component preserves existing custom port and config descriptions."""
    comp_dir = create_component_project("custom-desc-comp", destination=tmp_path)
    manifest_file = comp_dir / "component.yaml"

    # Edit manifest with custom documentation
    custom_manifest_text = """name: custom-desc-comp
version: "0.1.0"
description: "High performance risk analyzer."
api_version: "1"
category: evaluation
entrypoint: custom_desc_comp.component:CustomDescCompComponent

inputs:
  input_data:
    type: array
    required: true
    description: "Carefully calibrated input vector."

outputs:
  output_data:
    type: array
    description: "Proprietary calculated output scores."

config:
  scale_factor:
    type: float
    required: false
    default: 1.0
    description: "Custom volatility adjustment coefficient."

dependencies: []
"""
    manifest_file.write_text(custom_manifest_text, encoding="utf-8")

    # Run update
    result = update_component(comp_dir)
    assert result.error is None
    assert result.is_updated is False  # Already in sync!

    # Verify descriptions are preserved exactly
    manifest = load_manifest(manifest_file)
    assert manifest.description == "High performance risk analyzer."
    assert (
        manifest.inputs["input_data"].description
        == "Carefully calibrated input vector."
    )
    assert (
        manifest.outputs["output_data"].description
        == "Proprietary calculated output scores."
    )
    assert (
        manifest.config["scale_factor"].description
        == "Custom volatility adjustment coefficient."
    )


def test_update_component_dry_run_does_not_modify_disk(tmp_path: Path) -> None:
    """update_component with dry_run=True computes changes without altering file."""
    comp_dir = create_component_project("dry-run-comp", destination=tmp_path)
    comp_py = comp_dir / "src" / "dry_run_comp" / "component.py"
    manifest_file = comp_dir / "component.yaml"

    original_manifest_text = manifest_file.read_text(encoding="utf-8")

    # Add new config to python code
    comp_py.write_text(
        comp_py.read_text(encoding="utf-8").replace(
            'raw_scale = config.get("scale_factor", 1.0)',
            'raw_scale = config.get("scale_factor", 1.0)\n'
            '        self.beta = config.get("beta", 99.0)',
        ),
        encoding="utf-8",
    )

    result = update_component(comp_dir, dry_run=True)
    assert result.is_updated is True
    assert any("beta" in c.field_name for c in result.changes)

    # Manifest on disk must be completely unchanged
    current_manifest_text = manifest_file.read_text(encoding="utf-8")
    assert current_manifest_text == original_manifest_text


# -----------------------------------------------------------------------------
# Pipeline Code Analysis & Update Tests
# -----------------------------------------------------------------------------


def test_pipeline_analyzer_extracts_builder_code(tmp_path: Path) -> None:
    """PipelineCodeAnalyzer extracts nodes and edges from Python builder code."""
    pipe_dir = tmp_path / "builder-pipe"
    pipe_dir.mkdir(parents=True)

    py_script = """from finforge import Pipeline

p = Pipeline(
    name="builder-pipe",
    description="Pipeline defined via Python builder script.",
    metadata={"env": "staging"},
)
p.add("loader", "portfolio-loader", config={"scale": 2.0})
p.add("scorer", "sentiment-scorer", config={"threshold": 0.5})
p.connect("loader", "raw_texts", "scorer", "texts")
"""
    (pipe_dir / "build_pipeline.py").write_text(py_script, encoding="utf-8")

    analyzer = PipelineCodeAnalyzer(pipe_dir)
    doc_data = analyzer.analyze()

    assert doc_data["name"] == "builder-pipe"
    assert doc_data["description"] == "Pipeline defined via Python builder script."
    assert doc_data["metadata"] == {"env": "staging"}
    assert len(doc_data["nodes"]) == 2
    assert doc_data["nodes"][0]["id"] == "loader"
    assert doc_data["nodes"][1]["id"] == "scorer"
    assert len(doc_data["edges"]) == 1
    assert doc_data["edges"][0]["source_node"] == "loader"
    assert doc_data["edges"][0]["destination_node"] == "scorer"


def test_update_pipeline_creates_and_syncs_pipeline_yaml(tmp_path: Path) -> None:
    """update_pipeline writes pipeline.yaml from Python code and local components."""
    pipe_dir = tmp_path / "auto-pipe"
    pipe_dir.mkdir(parents=True)

    script = """from finforge import Pipeline

pipeline = Pipeline(name="auto-pipe", description="Auto synchronized workflow.")
pipeline.add("step_a", "step-a-comp", config={"param": 10})
pipeline.add("step_b", "step-b-comp", config={"param": 20})
pipeline.connect("step_a", "output_port", "step_b", "input_port")
"""
    (pipe_dir / "pipeline.py").write_text(script, encoding="utf-8")

    result = update_pipeline(pipe_dir)
    assert result.error is None
    assert result.is_updated is True
    assert (pipe_dir / "pipeline.yaml").is_file()

    doc = load_pipeline_document(pipe_dir / "pipeline.yaml")
    assert doc.name == "auto-pipe"
    assert len(doc.nodes) == 2
    assert len(doc.edges) == 1
    assert doc.edges[0].source_node == "step_a"
    assert doc.edges[0].destination_port == "input_port"


def test_update_pipeline_syncs_new_local_components(tmp_path: Path) -> None:
    """update_pipeline adds scaffolded components in components/ to pipeline.yaml."""
    pipe_dir = create_pipeline_project(
        name="multi-comp-pipe",
        destination=tmp_path,
        components=["stage-one"],
    )

    # Scaffold a second component directly into components/
    create_component_project(
        name="stage-two",
        destination=pipe_dir / "components",
    )

    # Run update on pipeline
    result = update_pipeline(pipe_dir)
    assert result.error is None
    assert result.is_updated is True

    doc = load_pipeline_document(pipe_dir / "pipeline.yaml")
    comp_names = {n.component for n in doc.nodes}
    assert "stage-one" in comp_names
    assert "stage-two" in comp_names


# -----------------------------------------------------------------------------
# CLI Command Tests
# -----------------------------------------------------------------------------


def test_cli_update_help() -> None:
    """finforge update --help displays options and usage information."""
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "Automatically synchronize FinForge AI manifests with code" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--check" in result.stdout


def test_cli_update_component_explicit_path(tmp_path: Path) -> None:
    """finforge update component <path> updates component manifest."""
    comp_dir = create_component_project("cli-comp-test", destination=tmp_path)
    result = runner.invoke(app, ["update", "component", str(comp_dir)])
    assert result.exit_code == 0
    assert "Up-to-date" in result.stdout or "Updated" in result.stdout
    assert "cli-comp-test" in result.stdout


def test_cli_update_pipeline_explicit_path(tmp_path: Path) -> None:
    """finforge update pipeline <path> updates pipeline manifest."""
    pipe_dir = create_pipeline_project("cli-pipe-test", destination=tmp_path)
    result = runner.invoke(app, ["update", "pipeline", str(pipe_dir)])
    assert result.exit_code == 0
    assert "cli-pipe-test" in result.stdout


def test_cli_update_component_subcommand_flag(tmp_path: Path) -> None:
    """finforge update-component command updates targeted component."""
    comp_dir = create_component_project("subcmd-comp", destination=tmp_path)
    result = runner.invoke(app, ["update-component", str(comp_dir)])
    assert result.exit_code == 0
    assert "subcmd-comp" in result.stdout


def test_cli_update_pipeline_subcommand_flag(tmp_path: Path) -> None:
    """finforge update-pipeline command updates targeted pipeline."""
    pipe_dir = create_pipeline_project("subcmd-pipe", destination=tmp_path)
    result = runner.invoke(app, ["update-pipeline", str(pipe_dir)])
    assert result.exit_code == 0
    assert "subcmd-pipe" in result.stdout


def test_cli_update_check_flag_returns_non_zero_when_out_of_date(
    tmp_path: Path,
) -> None:
    """finforge update --check returns exit code 1 when manifests differ from code."""
    comp_dir = create_component_project("check-diff-comp", destination=tmp_path)
    comp_py = comp_dir / "src" / "check_diff_comp" / "component.py"

    # Add code change
    comp_py.write_text(
        comp_py.read_text(encoding="utf-8").replace(
            'raw_scale = config.get("scale_factor", 1.0)',
            'raw_scale = config.get("scale_factor", 1.0)\n'
            '        self.gamma = config.get("gamma", 3.14)',
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["update", str(comp_dir), "--check"])
    assert result.exit_code == 1
    assert "Manifest check failed" in result.stdout


def test_cli_update_nonexistent_path_fails() -> None:
    """finforge update produces error and exits with code 1 for non-existent path."""
    result = runner.invoke(app, ["update", "completely_nonexistent_dir_999"])
    assert result.exit_code == 1
    normalized = " ".join(result.stdout.split())
    assert "does not exist" in normalized
