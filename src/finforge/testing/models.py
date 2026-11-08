"""Data models for component testing outcomes and structured results."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TestStatus(StrEnum):
    """Execution status for component tests and validation stages."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_EXECUTED = "not_executed"


# Inform pytest that TestStatus is an enum, not a test suite class
TestStatus.__test__ = False  # type: ignore[attr-defined]


class ValidationStageResult(BaseModel):
    """Outcome of a single framework validation stage."""

    stage: str = Field(description="Name of the validation stage.")
    status: TestStatus = Field(description="Outcome status of this stage.")
    message: str | None = Field(
        default=None, description="Informational message or summary."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Metadata or inspection details."
    )
    errors: list[str] = Field(
        default_factory=list, description="Specific error messages if failed."
    )


class DeveloperTestSummary(BaseModel):
    """Aggregated outcome of developer-authored pytest execution."""

    status: TestStatus = Field(description="Overall status of developer tests.")
    passed: int = Field(default=0, description="Count of passed test cases.")
    failed: int = Field(default=0, description="Count of failed test cases.")
    skipped: int = Field(default=0, description="Count of skipped test cases.")
    collection_errors: int = Field(
        default=0, description="Count of test collection errors."
    )
    duration_seconds: float = Field(
        default=0.0, description="Total execution time in seconds."
    )
    failures: list[str] = Field(
        default_factory=list, description="Detailed test failure reports."
    )
    message: str | None = Field(default=None, description="Summary or explanation.")


class ComponentTestResult(BaseModel):
    """Comprehensive, structured result of all component checks."""

    component_name: str = Field(description="Name of the component tested.")
    component_version: str | None = Field(
        default=None, description="Version from component.yaml."
    )
    component_path: str = Field(description="Path to component project directory.")
    overall_status: TestStatus = Field(
        description="Overall pass/fail outcome across all stages."
    )
    manifest_validation: ValidationStageResult = Field(
        description="Outcome of component.yaml schema parsing."
    )
    structure_validation: ValidationStageResult = Field(
        description="Outcome of class structure and inheritance checks."
    )
    contract_validation: ValidationStageResult = Field(
        description="Outcome of port and type contract checks."
    )
    lifecycle_test: ValidationStageResult = Field(
        description="Outcome of setup/run/teardown execution if performed."
    )
    developer_tests: DeveloperTestSummary = Field(
        description="Outcome of pytest test suite execution."
    )
    summary_message: str = Field(
        description="High-level human summary of test outcome."
    )
    all_errors: list[str] = Field(
        default_factory=list, description="Consolidated list of all errors encountered."
    )

    @property
    def is_success(self) -> bool:
        """Return True if all executed checks passed."""
        return self.overall_status == TestStatus.PASSED
