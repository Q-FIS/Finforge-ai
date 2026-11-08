"""Python Pipeline Builder API for FinForge AI.

This module provides `Pipeline`, a developer-friendly builder abstraction
for constructing, inspecting, and validating Directed Acyclic Graphs (DAGs)
of FinForge AI components.
"""

from __future__ import annotations

import builtins
import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from finforge.exceptions import PipelineValidationError
from finforge.pipeline.graph import PipelineGraph
from finforge.pipeline.models import PipelineEdge, PipelineNode
from finforge.registry import ComponentRegistry

if TYPE_CHECKING:
    from finforge.runtime.models import PipelineExecutionResult


class Pipeline:
    """Developer-friendly Python builder for FinForge AI workflows.

    The `Pipeline` class provides a high-level API over an underlying
    `PipelineGraph`. It delegates all graph operations directly to the graph
    without duplicating graph representation or maintaining shadow state.

    Attributes:
        name: Name of the pipeline.
        description: Optional human-readable description of the pipeline.
    """

    def __init__(
        self,
        name: str,
        registry: ComponentRegistry | None = None,
        graph: PipelineGraph | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a new Pipeline.

        Args:
            name: Non-empty identifier for the pipeline.
            registry: Optional explicit ComponentRegistry. If omitted and `graph`
                is not supplied, a fresh in-memory ComponentRegistry is created.
            graph: Optional pre-existing PipelineGraph instance. If provided,
                the pipeline delegates directly to this graph.
            description: Optional human-readable description of the pipeline.
            metadata: Optional arbitrary metadata dictionary for the pipeline.

        Raises:
            ValueError: If `name` is empty or not a valid string.
            TypeError: If `graph` is not an instance of PipelineGraph.
            PipelineValidationError: If both `graph` and `registry` are provided
                and `graph.registry` is not the supplied `registry`.
        """
        if not isinstance(name, str):
            raise ValueError(
                f"Pipeline name must be a string, got '{type(name).__name__}'."
            )

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Pipeline name must be a non-empty string.")

        if graph is not None:
            if not isinstance(graph, PipelineGraph):
                raise TypeError(
                    f"Expected graph to be a PipelineGraph instance, got "
                    f"'{type(graph).__name__}'."
                )
            if registry is not None and graph.registry is not registry:
                raise PipelineValidationError(
                    "Explicitly supplied registry does not match the registry "
                    "associated with the supplied PipelineGraph."
                )
            self._graph = graph
        else:
            self._graph = PipelineGraph(registry=registry)

        self._name = clean_name
        self._description = description
        self._metadata = copy.deepcopy(metadata) if metadata is not None else {}

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the pipeline name."""
        return self._name

    @property
    def description(self) -> str | None:
        """Return the pipeline description, if provided."""
        return self._description

    @property
    def metadata(self) -> dict[str, Any]:
        """Return a defensive copy of the pipeline metadata."""
        return copy.deepcopy(self._metadata)

    @property
    def graph(self) -> PipelineGraph:
        """Return the underlying PipelineGraph instance."""
        return self._graph

    @property
    def registry(self) -> ComponentRegistry:
        """Return the component registry associated with this pipeline."""
        return self._graph.registry

    @property
    def nodes(self) -> builtins.list[PipelineNode]:
        """Return all nodes in the pipeline in insertion order."""
        return self._graph.list_nodes()

    @property
    def edges(self) -> builtins.list[PipelineEdge]:
        """Return all edges in the pipeline in insertion order."""
        return self._graph.list_edges()

    @property
    def component_names(self) -> set[str]:
        """Return unique component names referenced by nodes in the pipeline."""
        return {node.component_name for node in self._graph.list_nodes()}

    # -------------------------------------------------------------------------
    # Node Operations (Delegating to PipelineGraph)
    # -------------------------------------------------------------------------

    def add(
        self,
        node_id: str,
        component_name: str,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineNode:
        """Add a component node to the pipeline.

        Args:
            node_id: Unique identifier for the node within this pipeline.
            component_name: Name of a registered component in the registry.
            config: Optional configuration dictionary for the component.
            metadata: Optional arbitrary metadata for the node.

        Returns:
            The created PipelineNode.

        Raises:
            DuplicateNodeError: If a node with node_id already exists.
            ComponentNotFoundError: If component_name is not registered.
            ValueError: If node_id or component_name is invalid.
        """
        return self._graph.add_node(
            node_id=node_id,
            component_name=component_name,
            config=config,
            metadata=metadata,
        )

    def remove(self, node_id: str) -> None:
        """Remove a node and its connected edges from the pipeline.

        Args:
            node_id: Unique identifier of the node to remove.

        Raises:
            NodeNotFoundError: If node_id does not exist in the pipeline.
        """
        self._graph.remove_node(node_id)

    def get(self, node_id: str) -> PipelineNode:
        """Retrieve a node by its ID.

        Args:
            node_id: Unique identifier of the node.

        Returns:
            A deep copy of the PipelineNode.

        Raises:
            NodeNotFoundError: If node_id does not exist in the pipeline.
        """
        return self._graph.get_node(node_id)

    def list(self) -> builtins.list[PipelineNode]:
        """List all nodes in the pipeline in insertion order.

        Returns:
            A list of PipelineNode deep copies.
        """
        return self._graph.list_nodes()

    def has(self, node_id: str) -> bool:
        """Check whether a node exists in the pipeline by ID."""
        return self._graph.has_node(node_id)

    # -------------------------------------------------------------------------
    # Connection Operations (Delegating to PipelineGraph)
    # -------------------------------------------------------------------------

    def connect(
        self,
        source_node: str,
        source_port: str,
        destination_node: str,
        destination_port: str,
    ) -> PipelineEdge:
        """Connect an output port of a producer node to an input port of a consumer.

        Args:
            source_node: ID of the producing node.
            source_port: Name of the output port on the producer.
            destination_node: ID of the consuming node.
            destination_port: Name of the input port on the consumer.

        Returns:
            The created PipelineEdge.

        Raises:
            NodeNotFoundError: If source or destination node does not exist.
            SelfLoopError: If source_node == destination_node.
            PortNotFoundError: If source_port or destination_port is undeclared.
            PortIncompatibleError: If port data types are incompatible.
            DuplicateEdgeError: If the connection already exists.
            InvalidEdgeError: If destination port already has an incoming edge.
            CycleDetectedError: If the connection introduces a cycle.
        """
        return self._graph.add_edge(
            source_node_id=source_node,
            source_port=source_port,
            destination_node_id=destination_node,
            destination_port=destination_port,
        )

    def disconnect(
        self,
        source_node: str | PipelineEdge,
        source_port: str | None = None,
        destination_node: str | None = None,
        destination_port: str | None = None,
    ) -> None:
        """Remove a directed connection between two component ports.

        Args:
            source_node: Either a PipelineEdge instance or the source node ID.
            source_port: Source output port name (if passing string IDs).
            destination_node: Destination node ID (if passing string IDs).
            destination_port: Destination input port name (if passing string IDs).

        Raises:
            InvalidEdgeError: If the edge does not exist in the pipeline.
        """
        self._graph.remove_edge(
            source_node_id=source_node,
            source_port=source_port,
            destination_node_id=destination_node,
            destination_port=destination_port,
        )

    # -------------------------------------------------------------------------
    # Validation and Dependency Ordering
    # -------------------------------------------------------------------------

    def validate(self) -> None:
        """Validate that the pipeline satisfies all structural and contract invariants.

        Verifies:
          - All referenced nodes and registered components exist.
          - All ports exist and satisfy contract type compatibility.
          - No self-loops, duplicate edges, or multiple incoming connections.
          - No cycles exist across any connected or disconnected components.

        Raises:
            GraphValidationError: If structural validation fails.
            PortNotFoundError: If a referenced port is missing.
            PortIncompatibleError: If port types are incompatible.
            SelfLoopError: If a self-loop is detected.
            CycleDetectedError: If a cycle is detected.
        """
        self._graph.validate()

    def execution_order(self) -> builtins.list[str]:
        """Compute a deterministic topological dependency ordering of node IDs.

        Uses Kahn's algorithm with min-heap tie-breaking to ensure
        reproducible dependency resolution.

        Note:
            Topological ordering represents dependency resolution order, not
            the actual runtime execution. No components are executed.

        Returns:
            A deterministic list of node IDs in dependency order.

        Raises:
            CycleDetectedError: If the graph contains a cycle.
        """
        return self._graph.execution_order()

    def run(
        self,
        inputs: dict[str, dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PipelineExecutionResult:
        """Execute the pipeline synchronously using LocalSynchronousExecutor.

        Args:
            inputs: Optional external inputs keyed by node_id and port_name.
            context: Optional arbitrary metadata passed to components.

        Returns:
            A structured PipelineExecutionResult.
        """
        from finforge.runtime.executor import LocalSynchronousExecutor

        executor = LocalSynchronousExecutor()
        return executor.execute(self, inputs=inputs, context=context)

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def save(self, path: str | Path, overwrite: bool = False) -> None:
        """Save this pipeline to a YAML file safely.

        Args:
            path: Destination file path.
            overwrite: Whether to overwrite target if it already exists (default False).

        Raises:
            FileExistsError: If target path exists and overwrite=False.
            PipelineSerializationError: If serialization fails.
        """
        from finforge.pipeline.serialization import save_pipeline

        save_pipeline(self, path=path, overwrite=overwrite)

    @classmethod
    def load(
        cls,
        path: str | Path,
        registry: ComponentRegistry,
    ) -> Pipeline:
        """Load and reconstruct a pipeline from a YAML file.

        Args:
            path: Path to the pipeline YAML file.
            registry: Explicit ComponentRegistry containing all referenced components.

        Returns:
            Constructed and validated Pipeline instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            PipelineDeserializationError: If component is missing or loading fails.
            SerializationFormatError: If YAML is malformed or invalid schema.
        """
        from finforge.pipeline.serialization import load_pipeline

        return load_pipeline(path=path, registry=registry)

    # -------------------------------------------------------------------------
    # Introspection and Diagnostics
    # -------------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a structured summary of the pipeline metadata and topology."""
        return {
            "name": self._name,
            "description": self._description,
            "node_count": len(self._graph),
            "edge_count": len(self._graph.list_edges()),
            "nodes": [n.node_id for n in self._graph.list_nodes()],
            "edges": [str(e) for e in self._graph.list_edges()],
            "component_names": sorted(self.component_names),
        }

    # -------------------------------------------------------------------------
    # Dunder Helpers
    # -------------------------------------------------------------------------

    def __contains__(self, item: object) -> bool:
        """Check whether a node ID or edge exists in the pipeline."""
        return item in self._graph

    def __len__(self) -> int:
        """Return the number of nodes in the pipeline."""
        return len(self._graph)

    def __repr__(self) -> str:
        """Return a string summary of the pipeline."""
        return (
            f"<Pipeline name='{self._name}' "
            f"nodes={len(self._graph)} edges={len(self._graph.list_edges())}>"
        )
