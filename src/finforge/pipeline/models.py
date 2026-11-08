"""Data models for FinForge AI pipeline graphs.

This module defines `PipelineNode` and `PipelineEdge`, representing vertices
and directed connections within a FinForge Directed Acyclic Graph (DAG).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineNode(BaseModel):
    """A node in a pipeline graph representing a registered FinForge component.

    Attributes:
        node_id: Unique identifier for this node within the graph.
        component_name: Name of the registered component in ComponentRegistry.
        config: Node-specific configuration dictionary passed to setup().
        metadata: Optional arbitrary metadata associated with this node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str = Field(description="Unique identifier for this node.")
    component_name: str = Field(
        description="Name of the registered component in ComponentRegistry."
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration parameters for the component.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary user or framework metadata for this node.",
    )

    @field_validator("node_id", "component_name")
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        """Ensure node_id and component_name are non-empty strings."""
        stripped = value.strip()
        if not stripped:
            field_name = info.field_name if hasattr(info, "field_name") else "field"
            raise ValueError(f"'{field_name}' must be a non-empty string.")
        return stripped


class PipelineEdge(BaseModel):
    """A directed edge in a pipeline graph connecting two component ports.

    An edge routes data from an output port of a producer component
    to an input port of a consumer component.

    Attributes:
        source_node_id: ID of the producing node.
        source_port: Name of the output port on the producer component.
        destination_node_id: ID of the consuming node.
        destination_port: Name of the input port on the consumer component.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_node_id: str = Field(description="ID of the producer node.")
    source_port: str = Field(description="Name of the source output port.")
    destination_node_id: str = Field(description="ID of the consumer node.")
    destination_port: str = Field(description="Name of the destination input port.")

    @field_validator(
        "source_node_id",
        "source_port",
        "destination_node_id",
        "destination_port",
    )
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        """Ensure all edge attributes are non-empty strings."""
        stripped = value.strip()
        if not stripped:
            field_name = info.field_name if hasattr(info, "field_name") else "field"
            raise ValueError(f"'{field_name}' must be a non-empty string.")
        return stripped

    def __str__(self) -> str:
        """Return human-readable representation of the directed connection."""
        return (
            f"{self.source_node_id}.{self.source_port} -> "
            f"{self.destination_node_id}.{self.destination_port}"
        )
