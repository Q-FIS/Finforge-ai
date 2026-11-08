"""Pipeline serialization and deserialization engine for FinForge AI.

This module provides declarative YAML serialization and deserialization for
FinForge AI pipelines. It enables pipelines to be saved to and loaded from
versioned YAML definitions without executing component code or instantiating
component classes.
"""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finforge.exceptions import (
    CycleDetectedError,
    PipelineDeserializationError,
    PipelineSerializationError,
    SerializationFormatError,
)
from finforge.registry import ComponentRegistry

if TYPE_CHECKING:
    from finforge.pipeline.builder import Pipeline
    from finforge.pipeline.graph import PipelineGraph

CURRENT_FORMAT_VERSION = "1"
SUPPORTED_FORMAT_VERSIONS = {CURRENT_FORMAT_VERSION}

SAFE_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def validate_safe_config_value(value: Any, path: str = "config") -> None:
    """Recursively validate configuration values contain only YAML-safe primitives.

    Allowed types:
        - Strings
        - Integers
        - Floats
        - Booleans
        - None
        - Lists of allowed types
        - Dictionaries with string keys and allowed values

    Args:
        value: The configuration value or tree to validate.
        path: Dot/bracket notation path for clear error messages.

    Raises:
        PipelineSerializationError: If an unsupported object, function, class,
            or non-string dictionary key is encountered.
    """
    # Note: bool is a subclass of int in Python, handled cleanly by isinstance checks
    if value is None or isinstance(value, (str, float)):
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            validate_safe_config_value(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise PipelineSerializationError(
                    f"Configuration dictionary keys must be strings, got "
                    f"'{type(k).__name__}' at '{path}.{k}'."
                )
            validate_safe_config_value(v, path=f"{path}.{k}")
        return

    raise PipelineSerializationError(
        f"Unsupported configuration value of type '{type(value).__name__}' "
        f"at '{path}'. FinForge pipelines only support YAML-safe primitives "
        f"(str, int, float, bool, None, list, dict)."
    )


class SerializedNode(BaseModel):
    """Declarative serialization model for a pipeline node.

    Attributes:
        id: Unique identifier for the node within the pipeline.
        component: Name of the registered component in ComponentRegistry.
        config: Primitive-only configuration parameters for the component.
        metadata: Arbitrary user or framework metadata for this node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="Unique node identifier in the pipeline.")
    component: str = Field(description="Name of the registered component.")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration parameters for the component.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary user or framework metadata for this node.",
    )

    @field_validator("id", "component")
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        """Ensure node id and component name are non-empty strings."""
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            field_name = info.field_name if hasattr(info, "field_name") else "field"
            raise ValueError(f"'{field_name}' must be a non-empty string.")
        return stripped

    @field_validator("config", "metadata")
    @classmethod
    def validate_primitives(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        """Ensure config and metadata dictionaries contain only YAML-safe primitives."""
        field_name = info.field_name if hasattr(info, "field_name") else "config"
        try:
            validate_safe_config_value(value, path=field_name)
        except PipelineSerializationError as exc:
            raise ValueError(str(exc)) from exc
        return value


class SerializedEdge(BaseModel):
    """Declarative serialization model for a directed edge between ports.

    Attributes:
        source_node: ID of the producing node.
        source_port: Name of the output port on the producer node.
        destination_node: ID of the consuming node.
        destination_port: Name of the input port on the consumer node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_node: str = Field(description="Source node ID.")
    source_port: str = Field(description="Output port name on producer node.")
    destination_node: str = Field(description="Destination node ID.")
    destination_port: str = Field(description="Input port name on consumer node.")

    @field_validator(
        "source_node", "source_port", "destination_node", "destination_port"
    )
    @classmethod
    def validate_non_empty(cls, value: str, info: Any) -> str:
        """Ensure all endpoint attributes are non-empty strings."""
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            field_name = info.field_name if hasattr(info, "field_name") else "field"
            raise ValueError(f"'{field_name}' must be a non-empty string.")
        return stripped


class PipelineDocument(BaseModel):
    """Complete declarative serialization model for a FinForge pipeline document.

    Attributes:
        format_version: Format specification version string (currently '1').
        name: Name of the pipeline.
        description: Optional human-readable description.
        metadata: Arbitrary pipeline metadata.
        nodes: List of declarative serialized nodes.
        edges: List of declarative serialized edges.
    """

    model_config = ConfigDict(extra="forbid")

    format_version: str = Field(
        default=CURRENT_FORMAT_VERSION,
        description="FinForge pipeline serialization format version.",
    )
    name: str = Field(description="Unique pipeline name.")
    description: str | None = Field(
        default=None, description="Human-readable pipeline description."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary pipeline metadata dictionary.",
    )
    nodes: list[SerializedNode] = Field(
        default_factory=list,
        description="Declarative nodes in the pipeline.",
    )
    edges: list[SerializedEdge] = Field(
        default_factory=list,
        description="Declarative edges routing data between ports.",
    )

    @field_validator("format_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Verify that the format version is supported."""
        norm_v = str(value).strip()
        if norm_v not in SUPPORTED_FORMAT_VERSIONS:
            raise ValueError(
                f"Unsupported format_version '{value}'. Supported versions are: "
                f"{sorted(SUPPORTED_FORMAT_VERSIONS)}."
            )
        return norm_v

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Verify pipeline name is a non-empty string."""
        stripped = value.strip() if isinstance(value, str) else ""
        if not stripped:
            raise ValueError("Pipeline 'name' must be a non-empty string.")
        return stripped

    @field_validator("metadata")
    @classmethod
    def validate_metadata_primitives(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Ensure document metadata contains only YAML-safe primitives."""
        try:
            validate_safe_config_value(value, path="metadata")
        except PipelineSerializationError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @model_validator(mode="after")
    def validate_graph_structure(self) -> PipelineDocument:
        """Validate node uniqueness and edge references."""
        # 1. Reject duplicate node IDs
        seen_nodes: set[str] = set()
        for node in self.nodes:
            if node.id in seen_nodes:
                raise ValueError(f"Duplicate node ID '{node.id}' in pipeline document.")
            seen_nodes.add(node.id)

        # 2. Reject edges referencing undefined nodes or self-loops
        for edge in self.edges:
            if edge.source_node not in seen_nodes:
                raise ValueError(
                    f"Edge references nonexistent source node '{edge.source_node}'."
                )
            if edge.destination_node not in seen_nodes:
                raise ValueError(
                    f"Edge references nonexistent destination node "
                    f"'{edge.destination_node}'."
                )
            if edge.source_node == edge.destination_node:
                raise ValueError(
                    f"Self-loop detected: edge connects '{edge.source_node}' to itself."
                )

        return self


def compute_document_execution_order(doc: PipelineDocument) -> list[str]:
    """Compute deterministic topological execution order from a PipelineDocument.

    Uses Kahn's algorithm with min-heap tie-breaking for independent nodes.

    Args:
        doc: Validated PipelineDocument.

    Returns:
        List of node IDs in topological dependency order.

    Raises:
        CycleDetectedError: If a cycle exists in the edges.
    """
    import heapq

    in_degrees: dict[str, int] = {node.id: 0 for node in doc.nodes}
    adjacency: dict[str, list[str]] = {node.id: [] for node in doc.nodes}

    for edge in doc.edges:
        in_degrees[edge.destination_node] += 1
        adjacency[edge.source_node].append(edge.destination_node)

    # Initialize min-heap with nodes having in-degree 0
    zero_in_degree = [node_id for node_id, deg in in_degrees.items() if deg == 0]
    heapq.heapify(zero_in_degree)

    order: list[str] = []
    while zero_in_degree:
        current = heapq.heappop(zero_in_degree)
        order.append(current)

        for downstream in adjacency[current]:
            in_degrees[downstream] -= 1
            if in_degrees[downstream] == 0:
                heapq.heappush(zero_in_degree, downstream)

    if len(order) < len(doc.nodes):
        unresolved = [nid for nid, deg in in_degrees.items() if deg > 0]
        raise CycleDetectedError(
            f"Directed cycle detected in pipeline '{doc.name}'. "
            f"Unresolved cyclic nodes: {unresolved}."
        )

    return order


# -----------------------------------------------------------------------------
# Serialization Functions
# -----------------------------------------------------------------------------


def serialize_pipeline_to_dict(
    pipeline: Pipeline | PipelineGraph,
) -> dict[str, Any]:
    """Serialize a Pipeline or PipelineGraph into a clean dictionary.

    The returned dictionary strictly conforms to the `PipelineDocument` schema.
    Output is normalized and deterministic: nodes are sorted by node ID, and
    edges are sorted by (source_node, source_port, destination_node, destination_port).

    Args:
        pipeline: Pipeline or PipelineGraph instance to serialize.

    Returns:
        Deterministic dictionary representation conforming to format_version "1".

    Raises:
        PipelineSerializationError: If configuration contains unsupported types.
    """
    from finforge.pipeline.builder import Pipeline
    from finforge.pipeline.graph import PipelineGraph

    if isinstance(pipeline, Pipeline):
        name = pipeline.name
        description = pipeline.description
        metadata = pipeline.metadata
        nodes = pipeline.nodes
        edges = pipeline.edges
    elif isinstance(pipeline, PipelineGraph):
        name = "pipeline"
        description = None
        metadata = {}
        nodes = pipeline.list_nodes()
        edges = pipeline.list_edges()
    else:
        raise TypeError(
            f"Expected pipeline to be a Pipeline or PipelineGraph instance, "
            f"got '{type(pipeline).__name__}'."
        )

    # Validate safe configuration values defensively
    for node in nodes:
        validate_safe_config_value(node.config, path=f"nodes[{node.node_id}].config")
        validate_safe_config_value(
            node.metadata, path=f"nodes[{node.node_id}].metadata"
        )
    validate_safe_config_value(metadata, path="metadata")

    # Sort nodes deterministically by node_id
    sorted_nodes = sorted(nodes, key=lambda n: n.node_id)
    serialized_nodes: list[dict[str, Any]] = []
    for n in sorted_nodes:
        node_dict: dict[str, Any] = {
            "id": n.node_id,
            "component": n.component_name,
            "config": copy.deepcopy(n.config),
        }
        if n.metadata:
            node_dict["metadata"] = copy.deepcopy(n.metadata)
        serialized_nodes.append(node_dict)

    # Sort edges deterministically
    sorted_edges = sorted(
        edges,
        key=lambda e: (
            e.source_node_id,
            e.source_port,
            e.destination_node_id,
            e.destination_port,
        ),
    )
    serialized_edges: list[dict[str, Any]] = [
        {
            "source_node": e.source_node_id,
            "source_port": e.source_port,
            "destination_node": e.destination_node_id,
            "destination_port": e.destination_port,
        }
        for e in sorted_edges
    ]

    doc_dict: dict[str, Any] = {
        "format_version": CURRENT_FORMAT_VERSION,
        "name": name,
    }
    if description is not None:
        doc_dict["description"] = description
    if metadata:
        doc_dict["metadata"] = copy.deepcopy(metadata)

    doc_dict["nodes"] = serialized_nodes
    doc_dict["edges"] = serialized_edges

    return doc_dict


def serialize_pipeline_to_yaml(pipeline: Pipeline | PipelineGraph) -> str:
    """Serialize a Pipeline or PipelineGraph into a deterministic YAML string.

    Args:
        pipeline: Pipeline or PipelineGraph instance.

    Returns:
        Deterministic YAML string.

    Raises:
        PipelineSerializationError: If configuration contains unsupported types.
    """
    doc_dict = serialize_pipeline_to_dict(pipeline)
    return yaml.safe_dump(doc_dict, sort_keys=False, default_flow_style=False)


def save_pipeline(
    pipeline: Pipeline | PipelineGraph,
    path: str | Path,
    overwrite: bool = False,
) -> None:
    """Save a Pipeline or PipelineGraph to a YAML file safely and atomically.

    Guarantees:
        - Atomic write: writes to a temporary file before renaming, preventing
          corrupted or partial files on failure.
        - Safe configuration checking: rejects non-primitive objects.
        - File collision protection: raises `FileExistsError` if the target
          already exists and `overwrite=False`.

    Args:
        pipeline: Pipeline or PipelineGraph to save.
        path: Target file path.
        overwrite: Whether to overwrite target if it already exists (default False).

    Raises:
        FileExistsError: If target path exists and `overwrite=False`.
        PipelineSerializationError: If destination is a directory, serialization
            fails, or unsupported objects are in the configuration.
    """
    target_path = Path(path).resolve()
    if target_path.is_dir():
        raise PipelineSerializationError(
            f"Destination path '{target_path}' is an existing directory, not a file."
        )

    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f"Destination file '{target_path}' already exists. Pass overwrite=True "
            f"to replace it."
        )

    # Generate YAML content first (catches configuration validation errors before
    # touching disk)
    yaml_content = serialize_pipeline_to_yaml(pipeline)

    # Ensure parent directory exists
    parent_dir = target_path.parent
    if not parent_dir.exists():
        parent_dir.mkdir(parents=True, exist_ok=True)

    # Write atomically using a temporary file in the same directory
    temp_file = parent_dir / f".{target_path.name}.tmp_{uuid.uuid4().hex}"
    try:
        temp_file.write_text(yaml_content, encoding="utf-8")
        temp_file.replace(target_path)
    except Exception as exc:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise PipelineSerializationError(
            f"Failed to write pipeline to '{target_path}': {exc}"
        ) from exc


# -----------------------------------------------------------------------------
# Deserialization Functions
# -----------------------------------------------------------------------------


def deserialize_pipeline_document(yaml_content: str) -> PipelineDocument:
    """Parse and validate raw YAML content into a `PipelineDocument`.

    Guarantees:
        - Safe YAML loading: rejects Python executable tags and arbitrary objects.
        - Document validation: validates schema, required fields, format version,
          node IDs, and edge endpoint references.
        - Rejection of unknown fields (extra='forbid').

    Args:
        yaml_content: Raw YAML string content.

    Returns:
        Validated `PipelineDocument` instance.

    Raises:
        SerializationFormatError: If YAML is empty, malformed, non-mapping, has
            unsupported format version, or fails schema validation.
    """
    if not isinstance(yaml_content, str) or not yaml_content.strip():
        raise SerializationFormatError("Pipeline YAML content is empty.")

    try:
        raw_data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise SerializationFormatError(f"Malformed YAML content: {exc}") from exc

    if raw_data is None:
        raise SerializationFormatError("Pipeline YAML document is empty.")

    if not isinstance(raw_data, dict):
        raise SerializationFormatError(
            f"Pipeline YAML must be a top-level mapping (key-value dictionary), "
            f"got '{type(raw_data).__name__}'."
        )

    if "format_version" not in raw_data:
        raise SerializationFormatError(
            "Missing required field 'format_version' in pipeline document."
        )

    norm_ver = str(raw_data.get("format_version", "")).strip()
    if norm_ver not in SUPPORTED_FORMAT_VERSIONS:
        raise SerializationFormatError(
            f"Unsupported format_version '{raw_data.get('format_version')}'. "
            f"FinForge AI currently supports format_version: "
            f"'{CURRENT_FORMAT_VERSION}'."
        )

    try:
        return PipelineDocument.model_validate(raw_data)
    except Exception as exc:
        raise SerializationFormatError(
            f"Pipeline document schema validation failed: {exc}"
        ) from exc


def load_pipeline_document(path: str | Path) -> PipelineDocument:
    """Read a pipeline YAML file and parse it into a `PipelineDocument`.

    Args:
        path: Path to the pipeline YAML file.

    Returns:
        Validated `PipelineDocument`.

    Raises:
        FileNotFoundError: If the file does not exist.
        PipelineDeserializationError: If the path is a directory.
        SerializationFormatError: If parsing or document validation fails.
    """
    target_path = Path(path).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Pipeline file '{target_path}' does not exist.")
    if not target_path.is_file():
        raise PipelineDeserializationError(
            f"Pipeline path '{target_path}' is not a file."
        )

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise PipelineDeserializationError(
            f"Could not read pipeline file '{target_path}': {exc}"
        ) from exc

    return deserialize_pipeline_document(content)


def deserialize_pipeline(
    yaml_content: str,
    registry: ComponentRegistry,
) -> Pipeline:
    """Deserialize a pipeline YAML string and reconstruct a validated `Pipeline`.

    Reconstruction steps:
        1. Parse and validate the document schema safely (`PipelineDocument`).
        2. Resolve all component names against the supplied `ComponentRegistry`.
        3. Reconstruct `Pipeline` and its underlying `PipelineGraph`.
        4. Reconnect all directed edges between ports.
        5. Run graph validation to guarantee port compatibility and DAG structure.

    Security & Safety guarantees:
        - Never dynamically imports untrusted Python entrypoints.
        - Never instantiates component classes.
        - Never calls lifecycle methods (`setup()` or `run()`).

    Args:
        yaml_content: Raw YAML string content.
        registry: Explicit ComponentRegistry containing all referenced components.

    Returns:
        Constructed and validated `Pipeline` instance.

    Raises:
        TypeError: If registry is None or not a ComponentRegistry.
        SerializationFormatError: If YAML is malformed or invalid schema.
        PipelineDeserializationError: If a referenced component is not registered.
        PipelineError: If graph validation or port compatibility fails.
    """
    from finforge.pipeline.builder import Pipeline

    if registry is None or not isinstance(registry, ComponentRegistry):
        raise TypeError(
            f"A valid ComponentRegistry instance must be provided to load a pipeline, "
            f"got '{type(registry).__name__}'."
        )

    doc = deserialize_pipeline_document(yaml_content)

    # 1. Verify all referenced components exist in the registry
    for node in doc.nodes:
        if not registry.contains(node.component):
            raise PipelineDeserializationError(
                f"Component '{node.component}' referenced by node '{node.id}' "
                f"is not registered in the ComponentRegistry."
            )

    # 2. Reconstruct the Pipeline using existing builder and graph APIs
    pipeline = Pipeline(
        name=doc.name,
        registry=registry,
        description=doc.description,
        metadata=doc.metadata,
    )

    for node in doc.nodes:
        pipeline.add(
            node_id=node.id,
            component_name=node.component,
            config=node.config,
            metadata=node.metadata,
        )

    for edge in doc.edges:
        pipeline.connect(
            source_node=edge.source_node,
            source_port=edge.source_port,
            destination_node=edge.destination_node,
            destination_port=edge.destination_port,
        )

    # 3. Validate structural DAG invariants
    pipeline.validate()

    return pipeline


def load_pipeline(
    path: str | Path,
    registry: ComponentRegistry,
) -> Pipeline:
    """Load a pipeline YAML file and reconstruct a validated `Pipeline`.

    Args:
        path: Path to the pipeline YAML file.
        registry: Explicit ComponentRegistry containing all referenced components.

    Returns:
        Constructed and validated `Pipeline` instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        PipelineDeserializationError: If path is not a file or component is missing.
        SerializationFormatError: If parsing or document validation fails.
    """
    target_path = Path(path).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Pipeline file '{target_path}' does not exist.")
    if not target_path.is_file():
        raise PipelineDeserializationError(
            f"Pipeline path '{target_path}' is not a file."
        )

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise PipelineDeserializationError(
            f"Could not read pipeline file '{target_path}': {exc}"
        ) from exc

    return deserialize_pipeline(content, registry=registry)
