"""Comprehensive unit tests for FinForge AI Pipeline Graph subsystem (FF-08).

Tests all 35 architectural requirements across:
  - Node operations (add, get, list, remove, uniqueness, component resolution)
  - Edge operations (connect, remove, validation, single incoming port constraint)
  - DAG validation (chains, branches, diamonds, independent nodes, cycles)
  - Deterministic topological dependency ordering (Kahn's algorithm, min-heap)
  - Safety and isolation (no component execution, defensive copies)
"""

from typing import Any

import pytest
from pydantic import ValidationError

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentNotFoundError,
    CycleDetectedError,
    DuplicateEdgeError,
    DuplicateNodeError,
    GraphValidationError,
    InvalidEdgeError,
    NodeNotFoundError,
    PortIncompatibleError,
    PortNotFoundError,
    SelfLoopError,
)
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.pipeline import PipelineEdge, PipelineGraph, PipelineNode
from finforge.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Test Fixtures & Tracking Components
# ---------------------------------------------------------------------------


class SpyComponent(BaseComponent):
    """Component instrumented to detect any execution or lifecycle calls."""

    setup_called: bool = False
    run_called: bool = False
    teardown_called: bool = False
    instances_created: int = 0

    def __init__(self) -> None:
        SpyComponent.instances_created += 1

    def setup(self, config: dict[str, Any]) -> None:
        SpyComponent.setup_called = True

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        SpyComponent.run_called = True
        return {"out_val": inputs.get("in_val", 0)}

    def teardown(self) -> None:
        SpyComponent.teardown_called = True

    @classmethod
    def reset_tracking(cls) -> None:
        cls.setup_called = False
        cls.run_called = False
        cls.teardown_called = False
        cls.instances_created = 0


@pytest.fixture(autouse=True)
def reset_spy() -> None:
    """Reset execution tracking before every test."""
    SpyComponent.reset_tracking()


@pytest.fixture
def populated_registry() -> ComponentRegistry:
    """Provide a registry with a standard suite of test components."""
    registry = ComponentRegistry()

    # 1. Producer component (number and string outputs)
    registry.register(
        component_class=SpyComponent,
        manifest=ComponentManifest(
            name="producer",
            version="0.1.0",
            description="Emits numeric and string values.",
            category="data-processing",
            entrypoint="tests.unit.test_pipeline_graph:SpyComponent",
            inputs={},
            outputs={
                "num_out": PortDefinition(type="integer"),
                "str_out": PortDefinition(type="string"),
                "arr_out": PortDefinition(
                    type="array", items=PortDefinition(type="integer")
                ),
            },
        ),
    )

    # 2. Consumer component (number, string, and array inputs)
    registry.register(
        component_class=SpyComponent,
        manifest=ComponentManifest(
            name="consumer",
            version="0.1.0",
            description="Consumes inputs and emits processed result.",
            category="machine-learning",
            entrypoint="tests.unit.test_pipeline_graph:SpyComponent",
            inputs={
                "num_in": PortDefinition(type="number"),
                "str_in": PortDefinition(type="string"),
                "int_in": PortDefinition(type="integer"),
                "arr_in": PortDefinition(
                    type="array", items=PortDefinition(type="number")
                ),
                "opt_in": PortDefinition(type="string", required=False),
            },
            outputs={
                "res_out": PortDefinition(type="number"),
                "extra_out": PortDefinition(type="string"),
            },
        ),
    )

    # 3. Multi-port component for diamond & branch testing
    registry.register(
        component_class=SpyComponent,
        manifest=ComponentManifest(
            name="transformer",
            version="0.1.0",
            description="Transforms data intermediate steps.",
            category="data-processing",
            entrypoint="tests.unit.test_pipeline_graph:SpyComponent",
            inputs={
                "in_a": PortDefinition(type="number"),
                "in_b": PortDefinition(type="number", required=False),
            },
            outputs={
                "out_a": PortDefinition(type="number"),
                "out_b": PortDefinition(type="number"),
            },
        ),
    )

    return registry


@pytest.fixture
def empty_graph(populated_registry: ComponentRegistry) -> PipelineGraph:
    """Return an empty PipelineGraph backed by populated_registry."""
    return PipelineGraph(registry=populated_registry)


# ---------------------------------------------------------------------------
# Section 1: Node Operations (Tests 1 - 9)
# ---------------------------------------------------------------------------


def test_1_add_valid_node(empty_graph: PipelineGraph) -> None:
    """1. Add a valid node and verify its properties."""
    node = empty_graph.add_node(
        node_id="node_1",
        component_name="producer",
        config={"threshold": 42},
        metadata={"author": "alice"},
    )
    assert isinstance(node, PipelineNode)
    assert node.node_id == "node_1"
    assert node.component_name == "producer"
    assert node.config == {"threshold": 42}
    assert node.metadata == {"author": "alice"}
    assert len(empty_graph) == 1
    assert "node_1" in empty_graph


def test_2_retrieve_node(empty_graph: PipelineGraph) -> None:
    """2. Retrieve a node by ID."""
    empty_graph.add_node("n1", "producer", config={"a": 1})
    retrieved = empty_graph.get_node("n1")
    assert retrieved.node_id == "n1"
    assert retrieved.component_name == "producer"
    assert retrieved.config == {"a": 1}


def test_3_list_nodes(empty_graph: PipelineGraph) -> None:
    """3. List nodes in insertion order."""
    empty_graph.add_node("n1", "producer")
    empty_graph.add_node("n2", "consumer")
    empty_graph.add_node("n3", "transformer")

    nodes = empty_graph.list_nodes()
    assert len(nodes) == 3
    assert [n.node_id for n in nodes] == ["n1", "n2", "n3"]


def test_4_remove_node(empty_graph: PipelineGraph) -> None:
    """4. Remove a node and confirm it is no longer in the graph."""
    empty_graph.add_node("n1", "producer")
    assert empty_graph.has_node("n1")
    empty_graph.remove_node("n1")
    assert not empty_graph.has_node("n1")
    assert len(empty_graph) == 0


def test_5_duplicate_node_ids_rejected(empty_graph: PipelineGraph) -> None:
    """5. Adding a node with duplicate ID raises DuplicateNodeError."""
    empty_graph.add_node("node_dup", "producer")
    with pytest.raises(DuplicateNodeError) as exc_info:
        empty_graph.add_node("node_dup", "consumer")
    assert "already exists" in str(exc_info.value)


def test_6_unknown_component_name_rejected(empty_graph: PipelineGraph) -> None:
    """6. Unknown component name raises ComponentNotFoundError."""
    with pytest.raises(ComponentNotFoundError) as exc_info:
        empty_graph.add_node("n1", "nonexistent-component")
    assert "nonexistent-component" in str(exc_info.value)


def test_7_unknown_node_id_produces_clear_error(empty_graph: PipelineGraph) -> None:
    """7. Retrieving or removing unknown node ID raises NodeNotFoundError."""
    with pytest.raises(NodeNotFoundError) as exc_info:
        empty_graph.get_node("missing_node")
    assert "missing_node" in str(exc_info.value)

    with pytest.raises(NodeNotFoundError):
        empty_graph.remove_node("missing_node")


def test_8_removing_node_removes_connected_edges(empty_graph: PipelineGraph) -> None:
    """8. Removing a node cascades to remove its connected edges."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")
    empty_graph.add_node("t", "transformer")

    empty_graph.add_edge("p", "num_out", "c", "num_in")
    empty_graph.add_edge("c", "res_out", "t", "in_a")

    assert len(empty_graph.list_edges()) == 2
    # Removing 'c' should remove both edges connected to 'c'
    empty_graph.remove_node("c")
    assert len(empty_graph.list_edges()) == 0


def test_9_adding_node_does_not_instantiate_component(
    empty_graph: PipelineGraph,
) -> None:
    """9. Adding nodes does not instantiate component classes."""
    assert SpyComponent.instances_created == 0
    empty_graph.add_node("n1", "producer")
    empty_graph.add_node("n2", "consumer")
    assert SpyComponent.instances_created == 0


# ---------------------------------------------------------------------------
# Section 2: Edge Operations (Tests 10 - 19)
# ---------------------------------------------------------------------------


def test_10_connect_compatible_ports(empty_graph: PipelineGraph) -> None:
    """10. Connecting compatible ports succeeds and returns PipelineEdge."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")

    edge = empty_graph.add_edge("p", "num_out", "c", "num_in")
    assert edge.source_node_id == "p"
    assert edge.source_port == "num_out"
    assert edge.destination_node_id == "c"
    assert edge.destination_port == "num_in"
    assert edge in empty_graph
    assert len(empty_graph.list_edges()) == 1


def test_11_reject_incompatible_port_types(empty_graph: PipelineGraph) -> None:
    """11. Incompatible port types raise PortIncompatibleError."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")

    # string cannot connect to number input
    with pytest.raises(PortIncompatibleError) as exc_info:
        empty_graph.add_edge("p", "str_out", "c", "num_in")
    assert (
        "incompatible" in str(exc_info.value).lower()
        or "cannot" in str(exc_info.value).lower()
    )


def test_12_reject_nonexistent_source_node(empty_graph: PipelineGraph) -> None:
    """12. Edge connecting from nonexistent source node raises NodeNotFoundError."""
    empty_graph.add_node("c", "consumer")
    with pytest.raises(NodeNotFoundError) as exc_info:
        empty_graph.add_edge("ghost", "num_out", "c", "num_in")
    assert "ghost" in str(exc_info.value)


def test_13_reject_nonexistent_destination_node(empty_graph: PipelineGraph) -> None:
    """13. Edge connecting to nonexistent destination node raises NodeNotFoundError."""
    empty_graph.add_node("p", "producer")
    with pytest.raises(NodeNotFoundError) as exc_info:
        empty_graph.add_edge("p", "num_out", "ghost", "num_in")
    assert "ghost" in str(exc_info.value)


def test_14_reject_nonexistent_source_port(empty_graph: PipelineGraph) -> None:
    """14. Nonexistent source output port raises PortNotFoundError."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")
    with pytest.raises(PortNotFoundError) as exc_info:
        empty_graph.add_edge("p", "bad_out_port", "c", "num_in")
    assert "bad_out_port" in str(exc_info.value)


def test_15_reject_nonexistent_destination_port(empty_graph: PipelineGraph) -> None:
    """15. Nonexistent destination input port raises PortNotFoundError."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")
    with pytest.raises(PortNotFoundError) as exc_info:
        empty_graph.add_edge("p", "num_out", "c", "bad_in_port")
    assert "bad_in_port" in str(exc_info.value)


def test_16_reject_duplicate_edge(empty_graph: PipelineGraph) -> None:
    """16. Adding an identical edge twice raises DuplicateEdgeError."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")

    empty_graph.add_edge("p", "num_out", "c", "num_in")
    with pytest.raises(DuplicateEdgeError) as exc_info:
        empty_graph.add_edge("p", "num_out", "c", "num_in")
    assert "already exists" in str(exc_info.value)


def test_17_reject_self_loops(empty_graph: PipelineGraph) -> None:
    """17. Connecting a node to itself raises SelfLoopError."""
    empty_graph.add_node("t", "transformer")
    with pytest.raises(SelfLoopError) as exc_info:
        empty_graph.add_edge("t", "out_a", "t", "in_a")
    assert "self-loop" in str(exc_info.value).lower()
    # Confirm it also inherits from CycleDetectedError and InvalidEdgeError
    assert isinstance(exc_info.value, CycleDetectedError)
    assert isinstance(exc_info.value, InvalidEdgeError)


def test_18_reject_multiple_incoming_edges_to_one_port(
    empty_graph: PipelineGraph,
) -> None:
    """18. Two different producers connecting to same input port is rejected."""
    empty_graph.add_node("p1", "producer")
    empty_graph.add_node("p2", "producer")
    empty_graph.add_node("c", "consumer")

    empty_graph.add_edge("p1", "num_out", "c", "num_in")
    with pytest.raises(InvalidEdgeError) as exc_info:
        empty_graph.add_edge("p2", "num_out", "c", "num_in")
    assert "multiple incoming" in str(exc_info.value).lower()


def test_19_remove_edge_correctly(empty_graph: PipelineGraph) -> None:
    """19. Removing an edge by coordinates or by instance works as expected."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")

    edge = empty_graph.add_edge("p", "num_out", "c", "num_in")
    assert len(empty_graph.list_edges()) == 1

    # Remove by instance
    empty_graph.remove_edge(edge)
    assert len(empty_graph.list_edges()) == 0

    # Re-add and remove by coordinate strings
    edge2 = empty_graph.add_edge("p", "num_out", "c", "num_in")
    empty_graph.remove_edge("p", "num_out", "c", "num_in")
    assert len(empty_graph.list_edges()) == 0

    # Removing non-existent edge raises InvalidEdgeError
    with pytest.raises(InvalidEdgeError):
        empty_graph.remove_edge(edge2)


# ---------------------------------------------------------------------------
# Section 3: Graph Validation & Topologies (Tests 20 - 26)
# ---------------------------------------------------------------------------


def test_20_validate_simple_chain(empty_graph: PipelineGraph) -> None:
    """20. Validate simple linear chain: A -> B -> C."""
    empty_graph.add_node("a", "producer")
    empty_graph.add_node("b", "consumer")
    empty_graph.add_node("c", "transformer")

    empty_graph.add_edge("a", "num_out", "b", "num_in")
    empty_graph.add_edge("b", "res_out", "c", "in_a")

    empty_graph.validate()  # Should not raise


def test_21_validate_independent_nodes(empty_graph: PipelineGraph) -> None:
    """21. Validate independent disconnected nodes without edges."""
    empty_graph.add_node("x", "producer")
    empty_graph.add_node("y", "consumer")
    empty_graph.add_node("z", "transformer")

    empty_graph.validate()
    assert len(empty_graph) == 3
    assert len(empty_graph.list_edges()) == 0


def test_22_validate_branching_graphs(empty_graph: PipelineGraph) -> None:
    """22. Validate 1-to-many branching: Root -> B1, Root -> B2."""
    empty_graph.add_node("root", "producer")
    empty_graph.add_node("b1", "consumer")
    empty_graph.add_node("b2", "consumer")

    # One output port can feed multiple consumers' input ports!
    empty_graph.add_edge("root", "num_out", "b1", "num_in")
    empty_graph.add_edge("root", "num_out", "b2", "num_in")

    empty_graph.validate()
    assert len(empty_graph.list_edges()) == 2


def test_23_validate_diamond_shaped_graphs(empty_graph: PipelineGraph) -> None:
    """23. Validate diamond graph: S -> A, S -> B; A -> D, B -> D."""
    empty_graph.add_node("source", "producer")
    empty_graph.add_node("left", "transformer")
    empty_graph.add_node("right", "transformer")
    empty_graph.add_node("sink", "transformer")

    empty_graph.add_edge("source", "num_out", "left", "in_a")
    empty_graph.add_edge("source", "num_out", "right", "in_a")
    empty_graph.add_edge("left", "out_a", "sink", "in_a")
    empty_graph.add_edge("right", "out_a", "sink", "in_b")

    empty_graph.validate()
    order = empty_graph.execution_order()
    assert order.index("source") < order.index("left")
    assert order.index("source") < order.index("right")
    assert order.index("left") < order.index("sink")
    assert order.index("right") < order.index("sink")


def test_24_detect_direct_cycles(empty_graph: PipelineGraph) -> None:
    """24. Adding or validating a 2-node cycle A -> B -> A raises CycleDetectedError."""
    empty_graph.add_node("t1", "transformer")
    empty_graph.add_node("t2", "transformer")

    empty_graph.add_edge("t1", "out_a", "t2", "in_a")
    with pytest.raises(CycleDetectedError) as exc_info:
        empty_graph.add_edge("t2", "out_a", "t1", "in_a")
    assert "cycle detected" in str(exc_info.value).lower()


def test_25_detect_indirect_cycles(empty_graph: PipelineGraph) -> None:
    """25. Detecting indirect 3-node cycle: A -> B -> C -> A."""
    empty_graph.add_node("n_a", "transformer")
    empty_graph.add_node("n_b", "transformer")
    empty_graph.add_node("n_c", "transformer")

    empty_graph.add_edge("n_a", "out_a", "n_b", "in_a")
    empty_graph.add_edge("n_b", "out_a", "n_c", "in_a")

    with pytest.raises(CycleDetectedError) as exc_info:
        empty_graph.add_edge("n_c", "out_a", "n_a", "in_a")
    assert "cycle detected" in str(exc_info.value).lower()


def test_26_detect_cycles_in_disconnected_graph_sections(
    empty_graph: PipelineGraph,
) -> None:
    """26. Cycle detection finds cycles in disconnected components during validate()."""
    # Component 1: valid chain
    empty_graph.add_node("v1", "producer")
    empty_graph.add_node("v2", "consumer")
    empty_graph.add_edge("v1", "num_out", "v2", "num_in")

    # Component 2: cyclic section forced internally into _edges
    empty_graph.add_node("c1", "transformer")
    empty_graph.add_node("c2", "transformer")
    empty_graph._edges.append(
        PipelineEdge(
            source_node_id="c1",
            source_port="out_a",
            destination_node_id="c2",
            destination_port="in_a",
        )
    )
    empty_graph._edges.append(
        PipelineEdge(
            source_node_id="c2",
            source_port="out_a",
            destination_node_id="c1",
            destination_port="in_a",
        )
    )

    with pytest.raises(CycleDetectedError) as exc_info:
        empty_graph.validate()
    assert "cycle detected" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Section 4: Topological Ordering (Tests 27 - 30)
# ---------------------------------------------------------------------------


def test_27_return_valid_topological_order(empty_graph: PipelineGraph) -> None:
    """27. Execution order respects directed edge constraints."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")
    empty_graph.add_edge("p", "num_out", "c", "num_in")

    order = empty_graph.execution_order()
    assert order == ["p", "c"]


def test_28_respect_every_dependency(empty_graph: PipelineGraph) -> None:
    """28. In complex graph, every dependency is respected."""
    # Build: A -> B -> D; A -> C -> D; E (independent)
    empty_graph.add_node("A", "producer")
    empty_graph.add_node("B", "transformer")
    empty_graph.add_node("C", "transformer")
    empty_graph.add_node("D", "transformer")
    empty_graph.add_node("E", "producer")

    empty_graph.add_edge("A", "num_out", "B", "in_a")
    empty_graph.add_edge("A", "num_out", "C", "in_a")
    empty_graph.add_edge("B", "out_a", "D", "in_a")
    empty_graph.add_edge("C", "out_a", "D", "in_b")

    order = empty_graph.execution_order()
    pos = {nid: i for i, nid in enumerate(order)}

    assert pos["A"] < pos["B"]
    assert pos["A"] < pos["C"]
    assert pos["B"] < pos["D"]
    assert pos["C"] < pos["D"]
    assert "E" in pos


def test_29_return_deterministic_results(empty_graph: PipelineGraph) -> None:
    """29. Min-heap tie-breaking produces deterministic lexicographic order."""
    # Multiple valid starting nodes: Z, M, A
    empty_graph.add_node("Z", "producer")
    empty_graph.add_node("M", "producer")
    empty_graph.add_node("A", "producer")

    order1 = empty_graph.execution_order()
    order2 = empty_graph.execution_order()
    assert order1 == ["A", "M", "Z"]
    assert order1 == order2


def test_30_reject_cyclic_graphs_in_execution_order(empty_graph: PipelineGraph) -> None:
    """30. execution_order() raises CycleDetectedError if cycle exists."""
    empty_graph.add_node("a", "transformer")
    empty_graph.add_node("b", "transformer")
    # Manually bypass add_edge to force a cycle into graph state
    empty_graph._edges.append(
        PipelineEdge(
            source_node_id="a",
            source_port="out_a",
            destination_node_id="b",
            destination_port="in_a",
        )
    )
    empty_graph._edges.append(
        PipelineEdge(
            source_node_id="b",
            source_port="out_a",
            destination_node_id="a",
            destination_port="in_a",
        )
    )

    with pytest.raises(CycleDetectedError):
        empty_graph.execution_order()


# ---------------------------------------------------------------------------
# Section 5: Safety and Integration (Tests 31 - 35)
# ---------------------------------------------------------------------------


def test_31_graph_operations_do_not_execute_components(
    empty_graph: PipelineGraph,
) -> None:
    """31. Graph creation, edge addition, validation, and ordering execute no code."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c", "consumer")
    empty_graph.add_edge("p", "num_out", "c", "num_in")
    empty_graph.validate()
    empty_graph.execution_order()

    assert SpyComponent.instances_created == 0
    assert not SpyComponent.setup_called
    assert not SpyComponent.run_called
    assert not SpyComponent.teardown_called


def test_32_graph_operations_do_not_call_setup(empty_graph: PipelineGraph) -> None:
    """32. Adding node with config does not call setup()."""
    empty_graph.add_node("p", "producer", config={"key": "val"})
    assert not SpyComponent.setup_called


def test_33_graph_operations_do_not_call_run(empty_graph: PipelineGraph) -> None:
    """33. Validating and ordering does not call run()."""
    empty_graph.add_node("p", "producer")
    empty_graph.validate()
    empty_graph.execution_order()
    assert not SpyComponent.run_called


def test_34_returned_metadata_cannot_mutate_internal_state(
    empty_graph: PipelineGraph,
) -> None:
    """34. Mutating returned node config does not mutate internal graph state."""
    empty_graph.add_node("p", "producer", config={"orig": 123})

    # Retrieve and mutate
    node = empty_graph.get_node("p")
    node.config["orig"] = 999
    node.config["new_key"] = "hacked"

    # Verify original node remains unchanged
    node_fresh = empty_graph.get_node("p")
    assert node_fresh.config == {"orig": 123}
    assert "new_key" not in node_fresh.config

    # Same for list_nodes
    listed = empty_graph.list_nodes()[0]
    listed.config["orig"] = 888
    assert empty_graph.get_node("p").config == {"orig": 123}


def test_35_pipeline_edge_immutability_and_validation() -> None:
    """35. PipelineEdge is frozen, cannot be mutated, and validates fields."""
    edge = PipelineEdge(
        source_node_id="src",
        source_port="out",
        destination_node_id="dst",
        destination_port="in",
    )
    assert str(edge) == "src.out -> dst.in"

    with pytest.raises(ValidationError):
        edge.source_node_id = "new_src"  # Frozen

    with pytest.raises(ValidationError):
        PipelineEdge(
            source_node_id="",
            source_port="out",
            destination_node_id="dst",
            destination_port="in",
        )


def test_graph_incoming_and_outgoing_edges(empty_graph: PipelineGraph) -> None:
    """Verify get_incoming_edges and get_outgoing_edges helpers."""
    empty_graph.add_node("p", "producer")
    empty_graph.add_node("c1", "consumer")
    empty_graph.add_node("c2", "consumer")

    e1 = empty_graph.add_edge("p", "num_out", "c1", "num_in")
    e2 = empty_graph.add_edge("p", "str_out", "c2", "str_in")

    assert empty_graph.get_outgoing_edges("p") == [e1, e2]
    assert empty_graph.get_incoming_edges("c1") == [e1]
    assert empty_graph.get_incoming_edges("c2") == [e2]
    assert empty_graph.get_incoming_edges("p") == []

    with pytest.raises(NodeNotFoundError):
        empty_graph.get_incoming_edges("ghost")
    with pytest.raises(NodeNotFoundError):
        empty_graph.get_outgoing_edges("ghost")


def test_graph_validation_error_on_unregistered_component(
    empty_graph: PipelineGraph,
) -> None:
    """Verify GraphValidationError when a node's component is unregistered later."""
    empty_graph.add_node("p", "producer")
    # Unregister from registry
    empty_graph.registry.unregister("producer")

    with pytest.raises(GraphValidationError) as exc_info:
        empty_graph.validate()
    assert "unregistered" in str(exc_info.value).lower()
