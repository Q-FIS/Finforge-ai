"""Component test runner and validation orchestration engine."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from finforge.component import BaseComponent
from finforge.contracts import validate_inputs, validate_outputs
from finforge.exceptions import (
    ComponentError,
    ContractError,
    FinForgeError,
    ManifestError,
)
from finforge.manifest import ComponentManifest, load_manifest
from finforge.testing.models import (
    ComponentTestResult,
    DeveloperTestSummary,
    TestStatus,
    ValidationStageResult,
)


@contextmanager
def _isolated_sys_path(extra_paths: list[Path]) -> Iterator[None]:
    """Context manager to temporarily prepend paths and clean up imported modules."""
    original_path = list(sys.path)
    original_modules = set(sys.modules.keys())
    for p in reversed(extra_paths):
        p_str = str(p.resolve())
        if p_str not in sys.path:
            sys.path.insert(0, p_str)
    try:
        yield
    finally:
        sys.path = original_path
        # Remove any new modules loaded during this block
        new_modules = set(sys.modules.keys()) - original_modules
        for mod_name in new_modules:
            sys.modules.pop(mod_name, None)


def validate_manifest_stage(
    component_dir: Path,
) -> tuple[ValidationStageResult, ComponentManifest | None]:
    """Stage 1: Validate component.yaml manifest existence and schema."""
    manifest_file = component_dir / "component.yaml"
    if not manifest_file.is_file():
        return (
            ValidationStageResult(
                stage="manifest",
                status=TestStatus.FAILED,
                message=f"Missing component manifest at '{manifest_file}'.",
                errors=[f"Manifest file '{manifest_file}' does not exist."],
            ),
            None,
        )

    try:
        # Zero-execution parsing using FF-02 engine
        manifest = load_manifest(manifest_file)
        return (
            ValidationStageResult(
                stage="manifest",
                status=TestStatus.PASSED,
                message=f"Manifest '{manifest.name}' (v{manifest.version}) is valid.",
                details={
                    "name": manifest.name,
                    "version": manifest.version,
                    "category": manifest.category,
                    "entrypoint": manifest.entrypoint,
                },
            ),
            manifest,
        )
    except ManifestError as err:
        return (
            ValidationStageResult(
                stage="manifest",
                status=TestStatus.FAILED,
                message=f"Manifest validation error: {err}",
                errors=[str(err)],
            ),
            None,
        )
    except Exception as err:
        return (
            ValidationStageResult(
                stage="manifest",
                status=TestStatus.FAILED,
                message=f"Unexpected error loading manifest: {err}",
                errors=[str(err)],
            ),
            None,
        )


def validate_structure_stage(
    component_dir: Path,
    manifest: ComponentManifest,
) -> tuple[ValidationStageResult, type[BaseComponent] | None]:
    """Stage 2: Validate component class structure and abstract methods."""
    entrypoint = manifest.entrypoint
    if ":" not in entrypoint:
        return (
            ValidationStageResult(
                stage="structure",
                status=TestStatus.FAILED,
                message=f"Invalid entrypoint format '{entrypoint}'.",
                errors=[
                    f"Entrypoint '{entrypoint}' must follow '<module>:<class>' format."
                ],
            ),
            None,
        )

    module_name, class_name = entrypoint.split(":", 1)
    src_dir = component_dir / "src"
    candidate_paths = [src_dir, component_dir] if src_dir.is_dir() else [component_dir]

    with _isolated_sys_path(candidate_paths):
        import importlib

        importlib.invalidate_caches()
        sys.modules.pop(module_name, None)
        sys.modules.pop(module_name.split(".")[0], None)

        try:
            mod = importlib.import_module(module_name)
        except Exception as err:
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=f"Cannot import entrypoint module '{module_name}': {err}",
                    errors=[f"Cannot import entrypoint module '{module_name}': {err}"],
                ),
                None,
            )

        if not hasattr(mod, class_name):
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=(
                        f"Class '{class_name}' not found in module '{module_name}'."
                    ),
                    errors=[
                        f"Module '{module_name}' does not export class '{class_name}'."
                    ],
                ),
                None,
            )

        cls = getattr(mod, class_name)
        if not isinstance(cls, type):
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=f"Entrypoint target '{class_name}' is not a class.",
                    errors=[f"Expected class, got {type(cls).__name__}."],
                ),
                None,
            )

        if not issubclass(cls, BaseComponent):
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=(
                        f"Class '{class_name}' does not inherit from BaseComponent."
                    ),
                    errors=[
                        f"Class '{class_name}' must inherit from "
                        "finforge.component.BaseComponent."
                    ],
                ),
                None,
            )

        # In Python ABC, unimplemented abstract methods appear in __abstractmethods__
        abstract_methods = getattr(cls, "__abstractmethods__", None)
        if abstract_methods:
            missing = ", ".join(sorted(abstract_methods))
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=(
                        f"Class '{class_name}' is abstract; "
                        f"missing implementations: {missing}."
                    ),
                    errors=[
                        f"Unimplemented abstract method(s): {missing}. "
                        "Subclasses must implement setup() and run()."
                    ],
                ),
                None,
            )

        # Test safe instantiation without calling setup or run
        try:
            instance = cls()
        except Exception as err:
            return (
                ValidationStageResult(
                    stage="structure",
                    status=TestStatus.FAILED,
                    message=f"Failed to instantiate '{class_name}': {err}",
                    errors=[f"Instantiation error: {err}"],
                ),
                None,
            )

        # Verify lifecycle hooks exist and are callable
        for hook in ("setup", "run", "teardown"):
            if not hasattr(instance, hook) or not callable(getattr(instance, hook)):
                return (
                    ValidationStageResult(
                        stage="structure",
                        status=TestStatus.FAILED,
                        message=(
                            f"Missing callable lifecycle hook '{hook}' "
                            f"on '{class_name}'."
                        ),
                        errors=[f"Component instance lacks callable '{hook}' method."],
                    ),
                    None,
                )

    return (
        ValidationStageResult(
            stage="structure",
            status=TestStatus.PASSED,
            message=f"Component class '{class_name}' satisfies BaseComponent contract.",
            details={"class": class_name, "module": module_name},
        ),
        cls,
    )


def validate_contracts_stage(
    manifest: ComponentManifest,
    test_inputs: dict[str, Any] | None = None,
) -> ValidationStageResult:
    """Stage 3: Validate declared input/output contracts and verify test_inputs."""
    # If test_inputs is supplied, validate it against manifest inputs via FF-03
    if test_inputs is not None:
        try:
            validate_inputs(test_inputs, manifest.inputs)
            return ValidationStageResult(
                stage="contracts",
                status=TestStatus.PASSED,
                message="Declared contracts and test input data verified.",
                details={"ports": list(manifest.inputs.keys())},
            )
        except ContractError as err:
            return ValidationStageResult(
                stage="contracts",
                status=TestStatus.FAILED,
                message=f"Contract validation failure on test inputs: {err}",
                errors=[str(err)],
            )

    return ValidationStageResult(
        stage="contracts",
        status=TestStatus.PASSED,
        message="Static port schema definitions are valid.",
        details={
            "inputs": list(manifest.inputs.keys()),
            "outputs": list(manifest.outputs.keys()),
        },
    )


def validate_lifecycle_stage(
    cls: type[BaseComponent] | None,
    manifest: ComponentManifest,
    test_inputs: dict[str, Any] | None,
    test_config: dict[str, Any] | None,
    test_context: dict[str, Any] | None,
) -> ValidationStageResult:
    """Stage 4: Execute setup(), run(), teardown() if test_inputs are supplied."""
    if test_inputs is None or cls is None:
        return ValidationStageResult(
            stage="lifecycle",
            status=TestStatus.NOT_EXECUTED,
            message="Lifecycle execution skipped: no test_inputs provided.",
        )

    instance = cls()
    try:
        # 1. Setup
        instance.setup(test_config or {})

        # 2. Run
        outputs = instance.run(test_inputs, test_context or {})
        if not isinstance(outputs, dict):
            return ValidationStageResult(
                stage="lifecycle",
                status=TestStatus.FAILED,
                message=f"run() must return a dict, got {type(outputs).__name__}.",
                errors=[f"Invalid run() return type: {type(outputs).__name__}"],
            )

        # 3. Output contract validation
        validate_outputs(outputs, manifest.outputs)

        return ValidationStageResult(
            stage="lifecycle",
            status=TestStatus.PASSED,
            message="Lifecycle setup, run, and output contract validation passed.",
            details={"output_keys": list(outputs.keys())},
        )
    except (ComponentError, ContractError, FinForgeError) as err:
        return ValidationStageResult(
            stage="lifecycle",
            status=TestStatus.FAILED,
            message=f"Lifecycle execution failed: {err}",
            errors=[str(err)],
        )
    except Exception as err:
        return ValidationStageResult(
            stage="lifecycle",
            status=TestStatus.FAILED,
            message=f"Unexpected failure during lifecycle execution: {err}",
            errors=[str(err)],
        )
    finally:
        # Always attempt teardown cleanup
        with suppress(Exception):
            instance.teardown()


def run_developer_tests_stage(
    component_dir: Path,
) -> DeveloperTestSummary:
    """Stage 5: Discover and execute developer pytest test suite in isolated process."""
    tests_dir = component_dir / "tests"
    if not tests_dir.is_dir():
        # Check if any test files exist at root
        test_files = list(component_dir.glob("test_*.py"))
        if not test_files:
            return DeveloperTestSummary(
                status=TestStatus.SKIPPED,
                message="No developer test suite found (missing 'tests/' directory).",
            )
        target = "."
    else:
        target = "tests"

    import os
    import re
    import subprocess

    src_dir = (component_dir / "src").resolve()
    env = os.environ.copy()
    if src_dir.is_dir():
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

    # Execute pytest in an isolated subprocess (trusted code, shell=False)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-o",
        "addopts=",
        "-q",
        "--tb=short",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(component_dir),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except Exception as err:
        return DeveloperTestSummary(
            status=TestStatus.FAILED,
            failures=[f"Failed to execute pytest subprocess: {err}"],
            message=f"Pytest execution failed: {err}",
        )

    output = proc.stdout + "\n" + proc.stderr

    passed = int(m.group(1)) if (m := re.search(r"(\d+)\s+passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+)\s+failed", output)) else 0
    skipped = int(m.group(1)) if (m := re.search(r"(\d+)\s+skipped", output)) else 0
    collection_errors = (
        int(m.group(1)) if (m := re.search(r"(\d+)\s+error", output)) else 0
    )
    duration = (
        float(m.group(1)) if (m := re.search(r"in\s+([\d\.]+)\s*s", output)) else 0.0
    )

    failures: list[str] = []
    if proc.returncode != 0:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        relevant_errors = [
            line
            for line in lines
            if line.startswith(("E   ", "ERROR ", "FAILED ")) or "Error" in line
        ]
        failures = relevant_errors if relevant_errors else lines[-10:]

    if proc.returncode == 0:
        status = TestStatus.PASSED
    elif collection_errors > 0 or failed > 0 or proc.returncode in (1, 2):
        status = TestStatus.FAILED
    else:
        status = TestStatus.SKIPPED

    return DeveloperTestSummary(
        status=status,
        passed=passed,
        failed=failed,
        skipped=skipped,
        collection_errors=collection_errors,
        duration_seconds=duration,
        failures=failures,
        message=(
            f"{passed} passed, {failed} failed, {skipped} skipped, "
            f"{collection_errors} collection errors"
        ),
    )


def run_component_tests(
    component_path: str | Path,
    *,
    test_inputs: dict[str, Any] | None = None,
    test_config: dict[str, Any] | None = None,
    test_context: dict[str, Any] | None = None,
    run_developer_tests: bool = True,
) -> ComponentTestResult:
    """Run full architectural validation and developer tests on a component project.

    Args:
        component_path: Directory path of the component project to verify.
        test_inputs: Optional dictionary of test inputs to evaluate runtime contracts.
        test_config: Optional dictionary of configuration parameters for setup().
        test_context: Optional runtime context dictionary.
        run_developer_tests: If True, discover and run developer pytest tests.

    Returns:
        ComponentTestResult communicating the detailed status across all stages.
    """
    comp_dir = Path(component_path).resolve()
    all_errors: list[str] = []

    # 1. Manifest Validation
    manifest_res, manifest = validate_manifest_stage(comp_dir)
    all_errors.extend(manifest_res.errors)

    component_name = manifest.name if manifest else comp_dir.name
    component_version = manifest.version if manifest else None

    # If manifest is invalid, cannot proceed with structure or contracts
    if manifest is None:
        skipped_stage = ValidationStageResult(
            stage="skipped",
            status=TestStatus.NOT_EXECUTED,
            message="Skipped due to prior manifest failure.",
        )
        return ComponentTestResult(
            component_name=component_name,
            component_version=component_version,
            component_path=str(comp_dir),
            overall_status=TestStatus.FAILED,
            manifest_validation=manifest_res,
            structure_validation=skipped_stage,
            contract_validation=skipped_stage,
            lifecycle_test=skipped_stage,
            developer_tests=DeveloperTestSummary(
                status=TestStatus.NOT_EXECUTED,
                message="Developer tests skipped due to manifest failure.",
            ),
            summary_message="Component test failed: manifest is invalid or missing.",
            all_errors=all_errors,
        )

    # 2. Structure Validation
    structure_res, cls = validate_structure_stage(comp_dir, manifest)
    all_errors.extend(structure_res.errors)

    # 3. Contract Validation
    contract_res = validate_contracts_stage(manifest, test_inputs)
    all_errors.extend(contract_res.errors)

    # 4. Lifecycle Validation (if test_inputs provided)
    lifecycle_res = validate_lifecycle_stage(
        cls=cls,
        manifest=manifest,
        test_inputs=test_inputs,
        test_config=test_config,
        test_context=test_context,
    )
    all_errors.extend(lifecycle_res.errors)

    # 5. Developer Pytest Execution
    if run_developer_tests:
        dev_tests_res = run_developer_tests_stage(comp_dir)
        all_errors.extend(dev_tests_res.failures)
    else:
        dev_tests_res = DeveloperTestSummary(
            status=TestStatus.SKIPPED,
            message="Developer tests skipped by request.",
        )

    # Determine overall status
    is_failed = (
        manifest_res.status == TestStatus.FAILED
        or structure_res.status == TestStatus.FAILED
        or contract_res.status == TestStatus.FAILED
        or lifecycle_res.status == TestStatus.FAILED
        or dev_tests_res.status == TestStatus.FAILED
    )

    overall_status = TestStatus.FAILED if is_failed else TestStatus.PASSED
    summary_message = (
        "Component verification failed."
        if is_failed
        else "All component checks passed successfully."
    )

    return ComponentTestResult(
        component_name=component_name,
        component_version=component_version,
        component_path=str(comp_dir),
        overall_status=overall_status,
        manifest_validation=manifest_res,
        structure_validation=structure_res,
        contract_validation=contract_res,
        lifecycle_test=lifecycle_res,
        developer_tests=dev_tests_res,
        summary_message=summary_message,
        all_errors=all_errors,
    )
