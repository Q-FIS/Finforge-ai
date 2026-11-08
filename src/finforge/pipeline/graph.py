"""Directed Acyclic Graph (DAG) architecture for FinForge AI pipelines.

This module provides `PipelineGraph`, which represents workflows as directed
acyclic graphs where nodes correspond to registered FinForge components and
edges represent typed data flows between output and input ports.
"""

from __future__ import annotations

import copy
import heapq
from typing import Any

from finforge.contracts import check_port_compatibility
from finforge.exceptions import (
    ComponentNotFoundError,
    CycleDetectedError,
    DuplicateEdgeError,
    DuplicateNodeError,
    GraphValidationError,
    InvalidEdgeError,
    NodeNotFoundError,
    PortNotFoundError,
    SelfLoopError,
)
from finforge.pipeline.models import PipelineEdge, PipelineNode
from finforge.registry import ComponentRegistry


class PipelineGraph:
    """In-memory Directed Acyclic Graph (DAG) representation of a pipeline.

    A `PipelineGraph` manages:
      - Nodes representing registered components and their configurations.
      - Edges representing directed data flows between component ports.
      - Static contract and structural validation.
      - Deterministic topological dependency ordering.

    The graph operates entirely on component manifests and metadata. It never
    instantiates component classes or invokes component execution methods.
    """

    def __init__(self, registry: ComponentRegistry | None = None) -> None:
        """Initialize an empty PipelineGraph.

        Args:
            registry: Optional ComponentRegistry instance to resolve component
                metadata. If omitted, an empty in-memory registry is created.
        """
        self._registry: ComponentRegistry = (
            registry if registry is not None else ComponentRegistry()
        )
        self._nodes: dict[str, PipelineNode] = {}
        self._edges: list[PipelineEdge] = []

    @property
    def registry(self) -> ComponentRegistry:
        """Return the underlying component registry."""
        return self._registry

    # -------------------------------------------------------------------------
    # Node Operations
    # -------------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        component_name: str,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineNode:
        """Add a component node to the graph.

        Args:
            node_id: Unique identifier for the node within this graph.
            component_name: Name of a registered component in the registry.
            config: Optional configuration dictionary for the component.
            metadata: Optional arbitrary metadata for the node.

        Returns:
            The created PipelineNode.

        Raises:
            DuplicateNodeError: If a node with node_id already exists in the graph.
            ComponentNotFoundError: If component_name is not registered.
            ValueError: If node_id or component_name is empty or invalid.
        """
        norm_node_id = node_id.strip() if isinstance(node_id, str) else ""
        if not norm_node_id:
            raise ValueError("node_id must be a non-empty string.")

        if norm_node_id in self._nodes:
            raise DuplicateNodeError(
                f"Node '{norm_node_id}' already exists in the pipeline graph."
            )

        if not self._registry.contains(component_name):
            raise ComponentNotFoundError(
                f"Component '{component_name}' is not registered in the "
                f"ComponentRegistry."
            )

        safe_config = copy.deepcopy(config) if config is not None else {}
        safe_metadata = copy.deepcopy(metadata) if metadata is not None else {}

        node = PipelineNode(
            node_id=norm_node_id,
            component_name=component_name,
            config=safe_config,
            metadata=safe_metadata,
        )
        self._nodes[norm_node_id] = node
        return node.model_copy(deep=True)

    def get_node(self, node_id: str) -> PipelineNode:
        """Retrieve a node by its unique ID.

        Args:
            node_id: Unique identifier of the node.

        Returns:
            A deep copy of the PipelineNode.

        Raises:
            NodeNotFoundError: If node_id does not exist in the graph.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Node '{node_id}' does not exist in the pipeline graph."
            )
        return self._nodes[node_id].model_copy(deep=True)

    def list_nodes(self) -> list[PipelineNode]:
        """List all nodes in the graph in insertion order.

        Returns:
            A list of PipelineNode deep copies.
        """
        return [node.model_copy(deep=True) for node in self._nodes.values()]

    def has_node(self, node_id: str) -> bool:
        """Check whether a node exists by ID."""
        return node_id in self._nodes

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all of its connected edges from the graph.

        Args:
            node_id: Unique identifier of the node to remove.

        Raises:
            NodeNotFoundError: If node_id does not exist in the graph.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Cannot remove node: node '{node_id}' does not exist in graph."
            )

        del self._nodes[node_id]
        # Remove any incoming or outgoing edges connected to this node
        self._edges = [
            e
            for e in self._edges
            if e.source_node_id != node_id and e.destination_node_id != node_id
        ]

    # -------------------------------------------------------------------------
    # Edge Operations
    # -------------------------------------------------------------------------

    def add_edge(
        self,
        source_node_id: str,
        source_port: str,
        destination_node_id: str,
        destination_port: str,
    ) -> PipelineEdge:
        """Connect an output port of a producer node to an input port of a consumer.

        Args:
            source_node_id: ID of the producing node.
            source_port: Name of the output port on the producer.
            destination_node_id: ID of the consuming node.
            destination_port: Name of the input port on the consumer.

        Returns:
            The created PipelineEdge.

        Raises:
            NodeNotFoundError: If either source or destination node does not exist.
            SelfLoopError: If source_node_id == destination_node_id.
            PortNotFoundError: If source_port or destination_port is not declared.
            PortIncompatibleError: If port data types are statically incompatible.
            DuplicateEdgeError: If the exact edge already exists.
            InvalidEdgeError: If destination port already has an incoming edge.
            CycleDetectedError: If adding the edge would introduce a directed cycle.
        """
        # 1. Verify existence of source and destination nodes
        if source_node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Source node '{source_node_id}' does not exist in graph."
            )
        if destination_node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Destination node '{destination_node_id}' does not exist in graph."
            )

        # 2. Reject self-loops immediately
        if source_node_id == destination_node_id:
            raise SelfLoopError(
                f"Cannot connect node '{source_node_id}' to itself: "
                f"self-loops are not permitted in DAGs."
            )

        # 3. Retrieve manifests to verify ports
        source_comp_name = self._nodes[source_node_id].component_name
        dest_comp_name = self._nodes[destination_node_id].component_name

        source_manifest = self._registry.get_manifest(source_comp_name)
        dest_manifest = self._registry.get_manifest(dest_comp_name)

        if source_port not in source_manifest.outputs:
            available = sorted(source_manifest.outputs.keys())
            raise PortNotFoundError(
                f"Source port '{source_port}' not found in outputs of component "
                f"'{source_comp_name}' for node '{source_node_id}'. "
                f"Available outputs: {available}."
            )

        if destination_port not in dest_manifest.inputs:
            available = sorted(dest_manifest.inputs.keys())
            raise PortNotFoundError(
                f"Destination port '{destination_port}' not found in inputs of "
                f"component '{dest_comp_name}' for node '{destination_node_id}'. "
                f"Available inputs: {available}."
            )

        # 4. Check port type compatibility (raises PortIncompatibleError)
        src_port_def = source_manifest.outputs[source_port]
        dst_port_def = dest_manifest.inputs[destination_port]
        check_port_compatibility(
            src_port_def,
            dst_port_def,
            source_name=f"{source_node_id}.{source_port}",
            destination_name=f"{destination_node_id}.{destination_port}",
        )

        # 5. Check duplicate edge
        edge = PipelineEdge(
            source_node_id=source_node_id,
            source_port=source_port,
            destination_node_id=destination_node_id,
            destination_port=destination_port,
        )
        if edge in self._edges:
            raise DuplicateEdgeError(
                f"Edge from '{source_node_id}.{source_port}' to "
                f"'{destination_node_id}.{destination_port}' already exists."
            )

        # 6. Reject multiple incoming connections to the same input port
        for existing in self._edges:
            if (
                existing.destination_node_id == destination_node_id
                and existing.destination_port == destination_port
            ):
                raise InvalidEdgeError(
                    f"Multiple incoming connections to destination port "
                    f"'{destination_port}' on node '{destination_node_id}' "
                    f"are not permitted (already connected from "
                    f"'{existing.source_node_id}.{existing.source_port}'). "
                    f"Use an explicit merge component to combine values."
                )

        # 7. Check if adding this edge introduces a cycle
        if self._has_path(destination_node_id, source_node_id):
            raise CycleDetectedError(
                f"Cycle detected: adding edge '{source_node_id}' -> "
                f"'{destination_node_id}' introduces a directed cycle."
            )

        self._edges.append(edge)
        return edge

    def remove_edge(
        self,
        source_node_id: str | PipelineEdge,
        source_port: str | None = None,
        destination_node_id: str | None = None,
        destination_port: str | None = None,
    ) -> None:
        """Remove a directed edge from the graph.

        Args:
            source_node_id: Either a PipelineEdge instance or the source node ID.
            source_port: Source output port name (if passing string IDs).
            destination_node_id: Destination node ID (if passing string IDs).
            destination_port: Destination input port name (if passing string IDs).

        Raises:
            InvalidEdgeError: If the edge does not exist in the graph.
        """
        if isinstance(source_node_id, PipelineEdge):
            target = source_node_id
        else:
            if (
                source_port is None
                or destination_node_id is None
                or destination_port is None
            ):
                raise InvalidEdgeError(
                    "All 4 edge coordinates (source_node_id, source_port, "
                    "destination_node_id, destination_port) are required."
                )
            target = PipelineEdge(
                source_node_id=source_node_id,
                source_port=source_port,
                destination_node_id=destination_node_id,
                destination_port=destination_port,
            )

        if target not in self._edges:
            raise InvalidEdgeError(f"Edge '{target}' does not exist in graph.")

        self._edges.remove(target)

    def list_edges(self) -> list[PipelineEdge]:
        """List all edges currently in the graph in insertion order."""
        return list(self._edges)

    def get_incoming_edges(self, node_id: str) -> list[PipelineEdge]:
        """Return all edges terminating at the specified node."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Node '{node_id}' does not exist in the pipeline graph."
            )
        return [e for e in self._edges if e.destination_node_id == node_id]

    def get_outgoing_edges(self, node_id: str) -> list[PipelineEdge]:
        """Return all edges originating from the specified node."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(
                f"Node '{node_id}' does not exist in the pipeline graph."
            )
        return [e for e in self._edges if e.source_node_id == node_id]

    # -------------------------------------------------------------------------
    # Cycle Detection and Graph Reachability
    # -------------------------------------------------------------------------

    def _has_path(self, start: str, target: str) -> bool:
        """Check if target node is reachable from start node using BFS."""
        if start == target:
            return True

        visited: set[str] = {start}
        queue: list[str] = [start]

        # Build adjacency mapping for existing edges
        adj: dict[str, list[str]] = {nid: [] for nid in self._nodes}
        for edge in self._edges:
            adj[edge.source_node_id].append(edge.destination_node_id)

        while queue:
            current = queue.pop(0)
            for neighbor in adj.get(current, []):
                if neighbor == target:
                    return True
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return False

    def detect_cycle(self) -> list[str] | None:
        """Detect if the graph contains any cycles using 3-color DFS.

        Returns:
            A list of node IDs showing the cycle path (e.g. ['A', 'B', 'A'])
            if a cycle is detected, or None if the graph is strictly acyclic.
        """
        adj: dict[str, list[str]] = {nid: [] for nid in self._nodes}
        for edge in self._edges:
            adj[edge.source_node_id].append(edge.destination_node_id)

        white, gray, black = 0, 1, 2
        colors: dict[str, int] = dict.fromkeys(self._nodes, white)

        def dfs(node: str, path: list[str]) -> list[str] | None:
            colors[node] = gray
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor == node:
                    # Self-loop
                    return [node, node]
                if colors[neighbor] == gray:
                    # Cycle found
                    idx = path.index(neighbor)
                    return path[idx:] + [neighbor]
                if colors[neighbor] == white:
                    res = dfs(neighbor, path)
                    if res is not None:
                        return res

            path.pop()
            colors[node] = black
            return None

        for node_id in sorted(self._nodes.keys()):
            if colors[node_id] == white:
                cycle_found = dfs(node_id, [])
                if cycle_found is not None:
                    return cycle_found

        return None

    # -------------------------------------------------------------------------
    # DAG Structural Validation
    # -------------------------------------------------------------------------

    def validate(self) -> None:
        """Validate that the pipeline graph satisfies all structural invariants.

        Verifications performed:
          1. All referenced nodes exist in the graph.
          2. All referenced components exist in the registry.
          3. All referenced output ports exist on the source component manifest.
          4. All referenced input ports exist on the destination component manifest.
          5. All edges satisfy contract type compatibility.
          6. No self-loops exist.
          7. No multiple incoming connections to a single input port exist.
          8. No cycles exist across any connected or disconnected components.

        Raises:
            GraphValidationError: If structural or manifest validation fails.
            PortNotFoundError: If a referenced port is missing.
            PortIncompatibleError: If port types are incompatible.
            SelfLoopError: If a self-loop is detected.
            CycleDetectedError: If a cycle is detected.
        """
        # 1. Verify component existence in registry for all nodes
        for node_id, node in self._nodes.items():
            if not self._registry.contains(node.component_name):
                raise GraphValidationError(
                    f"Node '{node_id}' references unregistered component "
                    f"'{node.component_name}'."
                )

        # 2. Verify all edges
        seen_dest_ports: set[tuple[str, str]] = set()
        for edge in self._edges:
            # Check node existence
            if edge.source_node_id not in self._nodes:
                raise GraphValidationError(
                    f"Edge references nonexistent source node '{edge.source_node_id}'."
                )
            if edge.destination_node_id not in self._nodes:
                raise GraphValidationError(
                    f"Edge references nonexistent destination node "
                    f"'{edge.destination_node_id}'."
                )

            # Check self-loops
            if edge.source_node_id == edge.destination_node_id:
                raise SelfLoopError(
                    f"Self-loop detected on node '{edge.source_node_id}'."
                )

            # Check port existence on manifests
            src_node = self._nodes[edge.source_node_id]
            dst_node = self._nodes[edge.destination_node_id]
            src_manifest = self._registry.get_manifest(src_node.component_name)
            dst_manifest = self._registry.get_manifest(dst_node.component_name)

            if edge.source_port not in src_manifest.outputs:
                raise PortNotFoundError(
                    f"Source port '{edge.source_port}' not found in outputs of "
                    f"component '{src_manifest.name}' for node "
                    f"'{edge.source_node_id}'."
                )

            if edge.destination_port not in dst_manifest.inputs:
                raise PortNotFoundError(
                    f"Destination port '{edge.destination_port}' not found in "
                    f"inputs of component '{dst_manifest.name}' for node "
                    f"'{edge.destination_node_id}'."
                )

            # Check type compatibility
            check_port_compatibility(
                src_manifest.outputs[edge.source_port],
                dst_manifest.inputs[edge.destination_port],
                source_name=f"{edge.source_node_id}.{edge.source_port}",
                destination_name=f"{edge.destination_node_id}.{edge.destination_port}",
            )

            # Check single incoming connection invariant
            dest_key = (edge.destination_node_id, edge.destination_port)
            if dest_key in seen_dest_ports:
                raise GraphValidationError(
                    f"Multiple incoming connections to destination port "
                    f"'{edge.destination_port}' on node "
                    f"'{edge.destination_node_id}' are not permitted."
                )
            seen_dest_ports.add(dest_key)

        # 3. Detect cycles
        cycle = self.detect_cycle()
        if cycle is not None:
            cycle_str = " -> ".join(cycle)
            raise CycleDetectedError(f"Cycle detected in pipeline graph: {cycle_str}.")

    # -------------------------------------------------------------------------
    # Topological Dependency Ordering
    # -------------------------------------------------------------------------

    def execution_order(self) -> list[str]:
        """Compute a deterministic topological ordering using Kahn's algorithm.

        The ordering satisfies the invariant that every node appears after all
        nodes providing its inputs.

        Tie-Breaking:
            When multiple nodes have an in-degree of 0 (no unresolved upstream
            dependencies), the node with the lexicographically smallest
            `node_id` is processed first. This ensures 100% deterministic
            ordering across equivalent graph topologies.

        Note:
            Topological ordering represents dependency resolution order, not
            the actual runtime execution. Graph nodes are never executed during
            this operation.

        Returns:
            A deterministic list of node IDs in topological dependency order.

        Raises:
            CycleDetectedError: If the graph contains a cycle.
        """
        # Calculate in-degree for all nodes
        in_degree: dict[str, int] = dict.fromkeys(self._nodes, 0)
        adj: dict[str, list[str]] = {nid: [] for nid in self._nodes}

        for edge in self._edges:
            adj[edge.source_node_id].append(edge.destination_node_id)
            in_degree[edge.destination_node_id] += 1

        # Min-heap of available nodes with in-degree 0 for deterministic tie-breaking
        ready: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
        heapq.heapify(ready)

        order: list[str] = []

        while ready:
            curr = heapq.heappop(ready)
            order.append(curr)

            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    heapq.heappush(ready, neighbor)

        if len(order) != len(self._nodes):
            # Graph contains a cycle
            cycle = self.detect_cycle()
            cycle_msg = f" ({' -> '.join(cycle)})" if cycle else ""
            raise CycleDetectedError(
                f"Cycle detected in pipeline graph{cycle_msg}; "
                f"topological execution ordering cannot be resolved."
            )

        return order

    # -------------------------------------------------------------------------
    # Dunder Helpers
    # -------------------------------------------------------------------------

    def __contains__(self, item: object) -> bool:
        """Check whether a node ID or edge exists in the graph."""
        if isinstance(item, str):
            return item in self._nodes
        if isinstance(item, PipelineEdge):
            return item in self._edges
        return False

    def __len__(self) -> int:
        """Return the total number of nodes in the graph."""
        return len(self._nodes)

    def __repr__(self) -> str:
        """Return a string summary of the graph state."""
        return f"<PipelineGraph nodes={len(self._nodes)} edges={len(self._edges)}>"
