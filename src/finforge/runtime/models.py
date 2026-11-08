"""Data models for FinForge AI runtime execution results.

This module defines typed schemas for execution statuses, individual node
results, and overall pipeline execution summaries.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(StrEnum):
    """Lifecycle status states for pipeline and node execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

    __test__ = False


class NodeExecutionResult(BaseModel):
    """Execution outcome and diagnostics for an individual pipeline node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(description="Unique identifier of the executed node.")
    component_name: str = Field(description="Name of the executed component.")
    status: ExecutionStatus = Field(description="Final execution status of the node.")
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Inputs resolved and supplied to the component.",
    )
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Outputs produced by the component if successful.",
    )
    duration_ms: float = Field(
        default=0.0,
        description="Execution duration in milliseconds.",
    )
    error_details: str | None = Field(
        default=None,
        description="Traceback or message if execution or validation failed.",
    )


class PipelineExecutionResult(BaseModel):
    """Structured execution summary for an entire pipeline run."""

    model_config = ConfigDict(extra="forbid")

    pipeline_name: str = Field(description="Name of the executed pipeline.")
    status: ExecutionStatus = Field(description="Overall execution status.")
    success: bool = Field(description="Whether the pipeline executed successfully.")
    duration_ms: float = Field(
        default=0.0,
        description="Total pipeline run duration in milliseconds.",
    )
    node_results: dict[str, NodeExecutionResult] = Field(
        default_factory=dict,
        description="Mapping of node ID to individual node execution results.",
    )
    outputs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Collected outputs keyed by node_id and port_name.",
    )
    execution_errors: list[str] = Field(
        default_factory=list,
        description="Primary execution errors encountered during the run.",
    )
    cleanup_errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during component teardown.",
    )

    def get_output(self, node_id: str, port: str | None = None) -> Any:
        """Retrieve output produced by a specific node and optional port.

        Args:
            node_id: The node identifier.
            port: Optional port name. If omitted, returns the entire node output dict.

        Returns:
            The requested output value or dictionary, or None if node/port not found.
        """
        node_out = self.outputs.get(node_id)
        if node_out is None:
            return None
        if port is None:
            return node_out
        return node_out.get(port)
