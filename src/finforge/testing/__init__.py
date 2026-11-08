"""Component testing engine and architecture validation subsystem."""

from finforge.testing.collector import PytestResultCollector
from finforge.testing.models import (
    ComponentTestResult,
    DeveloperTestSummary,
    TestStatus,
    ValidationStageResult,
)
from finforge.testing.runner import (
    run_component_tests,
    run_developer_tests_stage,
    validate_contracts_stage,
    validate_lifecycle_stage,
    validate_manifest_stage,
    validate_structure_stage,
)

__all__ = [
    "ComponentTestResult",
    "DeveloperTestSummary",
    "PytestResultCollector",
    "TestStatus",
    "ValidationStageResult",
    "run_component_tests",
    "run_developer_tests_stage",
    "validate_contracts_stage",
    "validate_lifecycle_stage",
    "validate_manifest_stage",
    "validate_structure_stage",
]
