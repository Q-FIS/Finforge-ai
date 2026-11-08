"""Unit tests for the FinForge Component Testing Engine (FF-07)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from finforge.cli import app
from finforge.component import BaseComponent
from finforge.manifest import ComponentManifest
from finforge.sdk import create_component_project
from finforge.testing import (
    TestStatus,
    run_component_tests,
    validate_lifecycle_stage,
    validate_manifest_stage,
)

runner = CliRunner()


def test_valid_component_project_recognized(tmp_path: Path) -> None:
    """1 & 7. Valid component project recognized, structure accepted, stages pass."""
    project_dir = create_component_project(
        name="valid-comp",
        destination=tmp_path,
        category="machine-learning",
    )

    result = run_component_tests(
        project_dir,
        test_inputs={"input_data": [1.0, 2.0, 3.0]},
        test_config={"scale_factor": 2.0},
    )

    assert result.overall_status == TestStatus.PASSED
    assert result.is_success is True
    assert result.manifest_validation.status == TestStatus.PASSED
    assert result.structure_validation.status == TestStatus.PASSED
    assert result.contract_validation.status == TestStatus.PASSED
    assert result.lifecycle_test.status == TestStatus.PASSED
    assert result.developer_tests.status == TestStatus.PASSED
    assert result.developer_tests.passed >= 4
    assert len(result.all_errors) == 0


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    """2. Missing component.yaml is detected and reported clearly."""
    empty_dir = tmp_path / "empty_comp"
    empty_dir.mkdir(parents=True)

    result = run_component_tests(empty_dir)

    assert result.overall_status == TestStatus.FAILED
    assert result.manifest_validation.status == TestStatus.FAILED
    assert "manifest is invalid or missing" in result.summary_message.lower()
    assert any("does not exist" in err for err in result.all_errors)
    assert result.structure_validation.status == TestStatus.NOT_EXECUTED


def test_invalid_manifest_is_reported(tmp_path: Path) -> None:
    """3. Malformed YAML or schema violation in manifest is caught and reported."""
    bad_dir = tmp_path / "bad_manifest_comp"
    bad_dir.mkdir(parents=True)
    manifest_file = bad_dir / "component.yaml"
    manifest_file.write_text("invalid_yaml: [unclosed list", encoding="utf-8")

    result = run_component_tests(bad_dir)

    assert result.overall_status == TestStatus.FAILED
    assert result.manifest_validation.status == TestStatus.FAILED
    assert any(
        "Manifest validation error" in err or "manifest" in err.lower()
        for err in result.all_errors
    )


def test_invalid_entrypoint_is_reported(tmp_path: Path) -> None:
    """4. Non-existent module or invalid entrypoint format is reported."""
    project_dir = create_component_project("bad-entry", destination=tmp_path)
    manifest_file = project_dir / "component.yaml"
    raw_yaml = manifest_file.read_text(encoding="utf-8")
    # Replace entrypoint with missing module
    corrupted_yaml = raw_yaml.replace(
        "bad_entry.component:BadEntryComponent",
        "non_existent_module:NonExistentClass",
    )
    manifest_file.write_text(corrupted_yaml, encoding="utf-8")

    result = run_component_tests(project_dir)

    assert result.overall_status == TestStatus.FAILED
    assert result.structure_validation.status == TestStatus.FAILED
    assert any("Cannot import entrypoint module" in err for err in result.all_errors)


def test_non_base_component_class_rejected(tmp_path: Path) -> None:
    """5. Class that does not inherit from BaseComponent is rejected."""
    project_dir = create_component_project("non-base", destination=tmp_path)
    comp_file = project_dir / "src" / "non_base" / "component.py"
    # Replace component class with a plain object class
    comp_file.write_text(
        "class NonBaseComponent:\n"
        "    def setup(self, config): pass\n"
        "    def run(self, inputs, context): return {}\n"
        "    def teardown(self): pass\n",
        encoding="utf-8",
    )

    result = run_component_tests(project_dir)

    assert result.overall_status == TestStatus.FAILED
    assert result.structure_validation.status == TestStatus.FAILED
    assert any(
        "must inherit from finforge.component.BaseComponent" in err
        for err in result.all_errors
    )


def test_abstract_component_implementation_rejected(tmp_path: Path) -> None:
    """6. Subclass leaving abstract methods unimplemented is rejected."""
    project_dir = create_component_project("abstract-comp", destination=tmp_path)
    comp_file = project_dir / "src" / "abstract_comp" / "component.py"
    # Create subclass without implementing run()
    comp_file.write_text(
        "from finforge.component import BaseComponent\n"
        "class AbstractCompComponent(BaseComponent):\n"
        "    def setup(self, config):\n"
        "        pass\n",
        encoding="utf-8",
    )

    result = run_component_tests(project_dir)

    assert result.overall_status == TestStatus.FAILED
    assert result.structure_validation.status == TestStatus.FAILED
    assert any("Unimplemented abstract method" in err for err in result.all_errors)


def test_contract_input_validation_errors(tmp_path: Path) -> None:
    """8 & 9. Missing required input and invalid input types are detected."""
    project_dir = create_component_project("contract-test", destination=tmp_path)

    # Missing required input port
    result_missing = run_component_tests(
        project_dir,
        test_inputs={},  # 'input_data' is required
    )
    assert result_missing.overall_status == TestStatus.FAILED
    assert result_missing.contract_validation.status == TestStatus.FAILED
    assert any(
        "Missing required input 'input_data'" in err
        for err in result_missing.all_errors
    )

    # Invalid input type (string instead of array)
    result_bad_type = run_component_tests(
        project_dir,
        test_inputs={"input_data": "not-an-array"},
    )
    assert result_bad_type.overall_status == TestStatus.FAILED
    assert result_bad_type.contract_validation.status == TestStatus.FAILED
    assert any(
        "Invalid type for 'input_data'" in err for err in result_bad_type.all_errors
    )


def test_lifecycle_output_validation_errors(tmp_path: Path) -> None:
    """10 & 11. Missing required output or invalid output types are detected."""
    project_dir = create_component_project("bad-output-comp", destination=tmp_path)
    comp_file = project_dir / "src" / "bad_output_comp" / "component.py"

    # Mutate run() to return invalid output type
    comp_file.write_text(
        "from finforge.component import BaseComponent\n"
        "class BadOutputCompComponent(BaseComponent):\n"
        "    def setup(self, config): pass\n"
        "    def run(self, inputs, context):\n"
        "        return {'output_data': 'invalid-type-should-be-array'}\n"
        "    def teardown(self): pass\n",
        encoding="utf-8",
    )

    result = run_component_tests(
        project_dir,
        test_inputs={"input_data": [1, 2]},
        run_developer_tests=False,
    )

    assert result.overall_status == TestStatus.FAILED
    assert result.lifecycle_test.status == TestStatus.FAILED
    assert any("Invalid type for 'output_data'" in err for err in result.all_errors)


def test_developer_pytest_suite_outcomes(tmp_path: Path) -> None:
    """12, 13, 14, 15, 16. Passing, failing, skipped tests and collection errors."""
    project_dir = create_component_project("dev-test-suite", destination=tmp_path)
    test_file = project_dir / "tests" / "test_component.py"

    # Add passed, failed, and skipped tests
    test_file.write_text(
        "import pytest\n"
        "def test_passing(): assert True\n"
        "def test_failing(): assert False, 'Intentional test failure'\n"
        "@pytest.mark.skip(reason='testing skip counting')\n"
        "def test_skipped(): pass\n",
        encoding="utf-8",
    )

    result = run_component_tests(project_dir, run_developer_tests=True)

    assert result.overall_status == TestStatus.FAILED
    assert result.developer_tests.status == TestStatus.FAILED
    assert result.developer_tests.passed == 1
    assert result.developer_tests.failed == 1
    assert result.developer_tests.skipped == 1
    assert any("Intentional test failure" in err for err in result.all_errors)

    # Now simulate a collection error (syntax error in test file)
    test_file.write_text("def test_syntax_broken(: pass\n", encoding="utf-8")
    result_collect = run_component_tests(project_dir, run_developer_tests=True)
    assert result_collect.overall_status == TestStatus.FAILED
    assert result_collect.developer_tests.collection_errors >= 1


def test_missing_test_directory_handled(tmp_path: Path) -> None:
    """17. Missing tests/ directory marks developer tests as SKIPPED, not FAILED."""
    project_dir = create_component_project("no-tests-comp", destination=tmp_path)
    # Remove tests directory
    import shutil

    shutil.rmtree(project_dir / "tests")

    result = run_component_tests(project_dir, run_developer_tests=True)
    assert result.developer_tests.status == TestStatus.SKIPPED
    assert "missing 'tests/' directory" in (result.developer_tests.message or "")
    # Overall status is PASSED because framework validation succeeded
    assert result.overall_status == TestStatus.PASSED


def test_unexecuted_lifecycle_reported_as_not_executed(tmp_path: Path) -> None:
    """18. When test_inputs are not provided, lifecycle is marked NOT_EXECUTED."""
    project_dir = create_component_project("no-inputs-comp", destination=tmp_path)

    result = run_component_tests(project_dir, test_inputs=None)

    assert result.lifecycle_test.status == TestStatus.NOT_EXECUTED
    assert "skipped" in (result.lifecycle_test.message or "").lower()


def test_teardown_called_on_lifecycle_failure() -> None:
    """19. Teardown cleanup is attempted even when setup() or run() raises."""
    teardown_called = False

    class FailingComponent(BaseComponent):
        def setup(self, config: dict[str, Any]) -> None:
            raise ValueError("Failure in setup")

        def run(
            self, inputs: dict[str, Any], context: dict[str, Any]
        ) -> dict[str, Any]:
            return {}

        def teardown(self) -> None:
            nonlocal teardown_called
            teardown_called = True

    manifest = ComponentManifest.model_validate(
        {
            "name": "fail-comp",
            "version": "0.1.0",
            "description": "Fails in setup",
            "category": "machine-learning",
            "entrypoint": "mod:FailingComponent",
        }
    )

    res = validate_lifecycle_stage(
        cls=FailingComponent,
        manifest=manifest,
        test_inputs={"dummy": 1},
        test_config={},
        test_context={},
    )

    assert res.status == TestStatus.FAILED
    assert teardown_called is True


def test_manifest_inspection_does_not_execute_entrypoint(tmp_path: Path) -> None:
    """21. Manifest inspection does not import or execute entrypoint code."""
    project_dir = create_component_project("zero-exec-comp", destination=tmp_path)
    manifest_res, manifest = validate_manifest_stage(project_dir)
    assert manifest_res.status == TestStatus.PASSED
    assert manifest is not None
    # Entrypoint module was not imported during manifest stage
    assert "zero_exec_comp.component" not in sys.modules


def test_cli_finforge_test_success(tmp_path: Path) -> None:
    """CLI test: finforge test passes on a valid component project."""
    project_dir = create_component_project("cli-test-comp", destination=tmp_path)

    result = runner.invoke(app, ["test", str(project_dir)])
    assert result.exit_code == 0
    assert "Testing Component: cli-test-comp" in result.stdout
    assert "Outcome: All component checks passed successfully" in result.stdout


def test_cli_finforge_test_json_output(tmp_path: Path) -> None:
    """CLI test: finforge test --json outputs valid JSON."""
    import json

    project_dir = create_component_project("json-comp", destination=tmp_path)

    result = runner.invoke(app, ["test", str(project_dir), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["component_name"] == "json-comp"
    assert parsed["overall_status"] == "passed"
    assert parsed["manifest_validation"]["status"] == "passed"


def test_cli_finforge_test_non_existent_path(tmp_path: Path) -> None:
    """CLI test: finforge test on non-existent path exits with code 1."""
    result = runner.invoke(app, ["test", str(tmp_path / "does_not_exist")])
    assert result.exit_code != 0
    normalized_stdout = " ".join(result.stdout.split())
    assert "is not a directory" in normalized_stdout


def test_runner_error_distinguished_from_test_failures(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """22. Runner errors (e.g. process failure) distinguished from test failures."""
    project_dir = create_component_project("runner-err-comp", destination=tmp_path)
    import subprocess

    def failing_subprocess(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Subprocess spawn error")

    monkeypatch.setattr(subprocess, "run", failing_subprocess)

    result = run_component_tests(project_dir)
    assert result.overall_status == TestStatus.FAILED
    assert any(
        "Failed to execute pytest subprocess" in err for err in result.all_errors
    )


def test_pytest_result_collector_direct() -> None:
    """Verify PytestResultCollector correctly tallies call and setup reports."""
    from types import SimpleNamespace

    from finforge.testing.collector import PytestResultCollector

    collector = PytestResultCollector()

    # Passed call report
    call_passed = SimpleNamespace(
        when="call", passed=True, failed=False, skipped=False, duration=0.1
    )
    collector.pytest_runtest_logreport(call_passed)

    # Failed call report
    call_failed = SimpleNamespace(
        when="call",
        passed=False,
        failed=True,
        skipped=False,
        duration=0.2,
        nodeid="test_foo",
        longrepr="AssertionError: foo != bar",
    )
    collector.pytest_runtest_logreport(call_failed)

    # Skipped call report
    call_skipped = SimpleNamespace(
        when="call", passed=False, failed=False, skipped=True, duration=0.0
    )
    collector.pytest_runtest_logreport(call_skipped)

    # Setup failure
    setup_failed = SimpleNamespace(
        when="setup",
        passed=False,
        failed=True,
        skipped=False,
        duration=0.05,
        nodeid="test_setup",
        longrepr="Setup failed",
    )
    collector.pytest_runtest_logreport(setup_failed)

    # Collection failure
    collect_failed = SimpleNamespace(
        failed=True, nodeid="test_bad.py", longrepr="SyntaxError"
    )
    collector.pytest_collectreport(collect_failed)

    assert collector.passed == 1
    assert collector.failed == 2
    assert collector.skipped == 1
    assert collector.collection_errors == 1
    assert len(collector.failures) == 3
