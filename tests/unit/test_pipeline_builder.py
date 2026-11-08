"""Comprehensive unit tests for the Python Pipeline Builder API (FF-09).

Tests all 25+ requirements:
  - Pipeline initialization and name validation
  - Explicit vs default isolated registry handling (no hidden global state)
  - Node operations (add, remove, get, list, has, duplicate rejection)
  - Connection operations (connect, disconnect, port compatibility, cycle rejection)
  - Introspection (name, description, metadata, component_names, summary)
  - Delegation to PipelineGraph (no state duplication)
  - Safety and lifecycle isolation (components are never instantiated or executed)
"""

from typing import Any

import pytest

from finforge import Pipeline
from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentNotFoundError,
    CycleDetectedError,
    DuplicateNodeError,
    InvalidEdgeError,
    NodeNotFoundError,
    PipelineValidationError,
    PortIncompatibleError,
    PortNotFoundError,
    SelfLoopError,
)
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.pipeline import PipelineEdge, PipelineGraph, PipelineNode
from finforge.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Spy Component to track any unexpected instantiation or lifecycle calls
# ---------------------------------------------------------------------------


class BuilderSpyComponent(BaseComponent):
    """Component instrumented to detect any execution or lifecycle calls."""

    instances_created: int = 0
    setup_called: bool = False
    run_called: bool = False

    def __init__(self) -> None:
        BuilderSpyComponent.instances_created += 1

    def setup(self, config: dict[str, Any]) -> None:
        BuilderSpyComponent.setup_called = True

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        BuilderSpyComponent.run_called = True
        return {"out_val": 42}


@pytest.fixture(autouse=True)
def reset_spy() -> None:
    """Reset execution tracking before every test."""
    BuilderSpyComponent.instances_created = 0
    BuilderSpyComponent.setup_called = False
    BuilderSpyComponent.run_called = False


@pytest.fixture
def test_registry() -> ComponentRegistry:
    """Create a test registry with producer, consumer, and transformer."""
    registry = ComponentRegistry()

    registry.register(
        component_class=BuilderSpyComponent,
        manifest=ComponentManifest(
            name="test-producer",
            version="0.1.0",
            description="Emits numeric output.",
            category="data-processing",
            entrypoint="tests.unit.test_pipeline_builder:BuilderSpyComponent",
            inputs={},
            outputs={
                "num_out": PortDefinition(type="integer"),
                "str_out": PortDefinition(type="string"),
            },
        ),
    )

    registry.register(
        component_class=BuilderSpyComponent,
        manifest=ComponentManifest(
            name="test-consumer",
            version="0.1.0",
            description="Consumes numeric or string input.",
            category="machine-learning",
            entrypoint="tests.unit.test_pipeline_builder:BuilderSpyComponent",
            inputs={
                "num_in": PortDefinition(type="number"),
                "str_in": PortDefinition(type="string"),
            },
            outputs={"result": PortDefinition(type="number")},
        ),
    )

    registry.register(
        component_class=BuilderSpyComponent,
        manifest=ComponentManifest(
            name="test-transformer",
            version="0.1.0",
            description="Transforms numeric input.",
            category="data-processing",
            entrypoint="tests.unit.test_pipeline_builder:BuilderSpyComponent",
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


# ---------------------------------------------------------------------------
# Section 1: Initialization and Registry Isolation (Tests 1 - 4)
# ---------------------------------------------------------------------------


def test_1_pipeline_initializes_correctly(test_registry: ComponentRegistry) -> None:
    """1. Pipeline initializes correctly with name and registry."""
    pipeline = Pipeline(
        name="my-pipeline",
        registry=test_registry,
        description="A sample pipeline.",
        metadata={"env": "test"},
    )
    assert pipeline.name == "my-pipeline"
    assert pipeline.description == "A sample pipeline."
    assert pipeline.metadata == {"env": "test"}
    assert pipeline.registry is test_registry
    assert len(pipeline) == 0
    assert repr(pipeline) == "<Pipeline name='my-pipeline' nodes=0 edges=0>"


def test_2_pipeline_name_is_validated() -> None:
    """2. Pipeline name must be a non-empty string."""
    with pytest.raises(ValueError, match="non-empty string"):
        Pipeline(name="")

    with pytest.raises(ValueError, match="non-empty string"):
        Pipeline(name="   ")

    with pytest.raises(ValueError, match="must be a string"):
        Pipeline(name=123)  # type: ignore[arg-type]


def test_3_explicit_registry_is_used(test_registry: ComponentRegistry) -> None:
    """3. Explicit registry passed to Pipeline is retained."""
    pipeline = Pipeline(name="explicit-reg", registry=test_registry)
    assert pipeline.registry is test_registry
    assert pipeline.registry.contains("test-producer")


def test_4_no_hidden_global_registry_is_used() -> None:
    """4. Pipelines created with default registry have distinct registry instances."""
    p1 = Pipeline(name="pipeline-1")
    p2 = Pipeline(name="pipeline-2")
    assert p1.registry is not p2.registry
    assert len(p1.registry) == 0
    assert len(p2.registry) == 0


def test_custom_graph_initialization(test_registry: ComponentRegistry) -> None:
    """Test initializing with pre-existing graph or mismatched registry."""
    graph = PipelineGraph(registry=test_registry)
    p = Pipeline(name="from-graph", graph=graph)
    assert p.graph is graph

    # Mismatched registry raises PipelineValidationError
    other_registry = ComponentRegistry()
    with pytest.raises(PipelineValidationError, match="does not match"):
        Pipeline(name="mismatch", registry=other_registry, graph=graph)

    # Invalid graph type raises TypeError
    with pytest.raises(TypeError, match="PipelineGraph instance"):
        Pipeline(name="bad-graph", graph="not-a-graph")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Section 2: Node Operations (Tests 5 - 9, 13, 14)
# ---------------------------------------------------------------------------


def test_5_add_node(test_registry: ComponentRegistry) -> None:
    """5. Add a node via pipeline.add()."""
    p = Pipeline(name="test", registry=test_registry)
    node = p.add("n1", "test-producer", config={"batch": 16})
    assert isinstance(node, PipelineNode)
    assert node.node_id == "n1"
    assert node.component_name == "test-producer"
    assert len(p) == 1
    assert p.has("n1")
    assert "n1" in p


def test_6_add_multiple_nodes(test_registry: ComponentRegistry) -> None:
    """6. Add multiple nodes and verify count and list."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("p1", "test-producer")
    p.add("c1", "test-consumer")
    p.add("t1", "test-transformer")
    assert len(p) == 3
    assert [n.node_id for n in p.list()] == ["p1", "c1", "t1"]


def test_7_remove_node(test_registry: ComponentRegistry) -> None:
    """7. Remove a node via pipeline.remove()."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("n1", "test-producer")
    assert p.has("n1")
    p.remove("n1")
    assert not p.has("n1")
    assert len(p) == 0

    with pytest.raises(NodeNotFoundError):
        p.remove("n1")


def test_8_get_node(test_registry: ComponentRegistry) -> None:
    """8. Get a node by ID via pipeline.get()."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("n1", "test-producer", config={"alpha": 0.5})
    retrieved = p.get("n1")
    assert retrieved.node_id == "n1"
    assert retrieved.config == {"alpha": 0.5}

    with pytest.raises(NodeNotFoundError):
        p.get("unknown")


def test_9_list_nodes(test_registry: ComponentRegistry) -> None:
    """9. List nodes via pipeline.list() and pipeline.nodes property."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("a", "test-producer")
    p.add("b", "test-consumer")
    nodes_method = p.list()
    nodes_prop = p.nodes
    assert len(nodes_method) == 2
    assert nodes_method == nodes_prop


def test_13_reject_invalid_node_ids(test_registry: ComponentRegistry) -> None:
    """13. Reject empty or whitespace node IDs."""
    p = Pipeline(name="test", registry=test_registry)
    with pytest.raises(ValueError):
        p.add("", "test-producer")
    with pytest.raises(ValueError):
        p.add("   ", "test-producer")


def test_14_reject_duplicate_nodes(test_registry: ComponentRegistry) -> None:
    """14. Duplicate node IDs raise DuplicateNodeError."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("dup", "test-producer")
    with pytest.raises(DuplicateNodeError):
        p.add("dup", "test-consumer")


def test_unknown_component_name_rejected(test_registry: ComponentRegistry) -> None:
    """Reject adding node with un-registered component name."""
    p = Pipeline(name="test", registry=test_registry)
    with pytest.raises(ComponentNotFoundError):
        p.add("bad", "unregistered-comp")


# ---------------------------------------------------------------------------
# Section 3: Connection Operations (Tests 10 - 12, 15)
# ---------------------------------------------------------------------------


def test_10_connect_compatible_components(test_registry: ComponentRegistry) -> None:
    """10. Connect compatible ports via pipeline.connect()."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")

    edge = p.connect("prod", "num_out", "cons", "num_in")
    assert isinstance(edge, PipelineEdge)
    assert edge.source_node_id == "prod"
    assert edge.destination_node_id == "cons"
    assert len(p.edges) == 1
    assert edge in p


def test_11_disconnect_components(test_registry: ComponentRegistry) -> None:
    """11. Disconnect components via pipeline.disconnect()."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")

    edge = p.connect("prod", "num_out", "cons", "num_in")
    assert len(p.edges) == 1

    # Disconnect by edge instance
    p.disconnect(edge)
    assert len(p.edges) == 0

    # Re-connect and disconnect by coordinates
    edge2 = p.connect("prod", "num_out", "cons", "num_in")
    p.disconnect("prod", "num_out", "cons", "num_in")
    assert len(p.edges) == 0

    # Disconnecting nonexistent edge raises InvalidEdgeError
    with pytest.raises(InvalidEdgeError):
        p.disconnect(edge2)


def test_12_reject_incompatible_connections(
    test_registry: ComponentRegistry,
) -> None:
    """12. Incompatible port types raise PortIncompatibleError."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")

    # string output to number input
    with pytest.raises(PortIncompatibleError):
        p.connect("prod", "str_out", "cons", "num_in")


def test_15_reject_cycles(test_registry: ComponentRegistry) -> None:
    """15. Cycle detection prevents connecting cycle in pipeline."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("t1", "test-transformer")
    p.add("t2", "test-transformer")

    p.connect("t1", "out_a", "t2", "in_a")
    with pytest.raises(CycleDetectedError):
        p.connect("t2", "out_a", "t1", "in_a")


def test_reject_self_loops(test_registry: ComponentRegistry) -> None:
    """Reject connecting node to itself."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("t1", "test-transformer")
    with pytest.raises(SelfLoopError):
        p.connect("t1", "out_a", "t1", "in_a")


def test_reject_missing_ports(test_registry: ComponentRegistry) -> None:
    """Reject nonexistent ports."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")

    with pytest.raises(PortNotFoundError):
        p.connect("prod", "missing_out", "cons", "num_in")

    with pytest.raises(PortNotFoundError):
        p.connect("prod", "num_out", "cons", "missing_in")


# ---------------------------------------------------------------------------
# Section 4: Validation and Topologies (Tests 16 - 19)
# ---------------------------------------------------------------------------


def test_16_validate_complete_graph(test_registry: ComponentRegistry) -> None:
    """16. Validate complete pipeline graph."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")
    p.connect("prod", "num_out", "cons", "num_in")

    p.validate()  # Passes without raising


def test_17_retrieve_deterministic_topological_order(
    test_registry: ComponentRegistry,
) -> None:
    """17. execution_order() returns deterministic order."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("Z", "test-producer")
    p.add("A", "test-producer")
    p.add("M", "test-consumer")
    p.connect("A", "num_out", "M", "num_in")

    order1 = p.execution_order()
    order2 = p.execution_order()
    # A must precede M; Z is independent and lexicographically after M
    assert order1.index("A") < order1.index("M")
    assert order1 == order2


def test_18_support_branching_graphs(test_registry: ComponentRegistry) -> None:
    """18. Support fan-out branching: Root -> B1, Root -> B2."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("root", "test-producer")
    p.add("b1", "test-consumer")
    p.add("b2", "test-consumer")

    p.connect("root", "num_out", "b1", "num_in")
    p.connect("root", "num_out", "b2", "num_in")

    p.validate()
    order = p.execution_order()
    assert order.index("root") < order.index("b1")
    assert order.index("root") < order.index("b2")


def test_19_support_diamond_shaped_graphs(test_registry: ComponentRegistry) -> None:
    """19. Support diamond DAG: Source -> Left, Right -> Sink."""
    p = Pipeline(name="test", registry=test_registry)
    p.add("source", "test-producer")
    p.add("left", "test-transformer")
    p.add("right", "test-transformer")
    p.add("sink", "test-transformer")

    p.connect("source", "num_out", "left", "in_a")
    p.connect("source", "num_out", "right", "in_a")
    p.connect("left", "out_a", "sink", "in_a")
    p.connect("right", "out_a", "sink", "in_b")

    p.validate()
    order = p.execution_order()
    assert order.index("source") < order.index("left")
    assert order.index("source") < order.index("right")
    assert order.index("left") < order.index("sink")
    assert order.index("right") < order.index("sink")


# ---------------------------------------------------------------------------
# Section 5: Introspection and Immutability (Tests 20, 21)
# ---------------------------------------------------------------------------


def test_20_introspection_returns_correct_information(
    test_registry: ComponentRegistry,
) -> None:
    """20. Introspection returns name, nodes, edges, component_names, summary."""
    p = Pipeline(
        name="intro-pipeline",
        registry=test_registry,
        description="Inspect me",
    )
    p.add("prod", "test-producer")
    p.add("cons", "test-consumer")
    p.connect("prod", "num_out", "cons", "num_in")

    assert p.name == "intro-pipeline"
    assert p.description == "Inspect me"
    assert p.component_names == {"test-producer", "test-consumer"}
    assert len(p.nodes) == 2
    assert len(p.edges) == 1

    summary = p.summary()
    assert summary["name"] == "intro-pipeline"
    assert summary["description"] == "Inspect me"
    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["nodes"] == ["prod", "cons"]
    assert summary["edges"] == ["prod.num_out -> cons.num_in"]
    assert summary["component_names"] == ["test-consumer", "test-producer"]


def test_21_returned_metadata_cannot_mutate_internal_state(
    test_registry: ComponentRegistry,
) -> None:
    """21. Modifying returned metadata or node copies does not corrupt pipeline."""
    p = Pipeline(
        name="safe-pipeline",
        registry=test_registry,
        metadata={"key": "val"},
    )
    meta = p.metadata
    meta["key"] = "tampered"
    assert p.metadata == {"key": "val"}

    p.add("n1", "test-producer", config={"threshold": 10})
    node = p.get("n1")
    node.config["threshold"] = 999
    assert p.get("n1").config == {"threshold": 10}


# ---------------------------------------------------------------------------
# Section 6: Delegation and Lifecycle Isolation (Tests 22 - 25)
# ---------------------------------------------------------------------------


def test_22_and_23_builder_delegates_without_state_duplication(
    test_registry: ComponentRegistry,
) -> None:
    """22 & 23. Pipeline operations directly affect underlying PipelineGraph."""
    p = Pipeline(name="delegate-pipeline", registry=test_registry)
    p.add("n1", "test-producer")

    # Directly inspect graph: n1 must exist on graph
    assert p.graph.has_node("n1")
    assert len(p.graph) == 1

    # Add directly to graph: immediately visible on pipeline
    p.graph.add_node("n2", "test-consumer")
    assert p.has("n2")
    assert len(p) == 2

    # Connect through pipeline: immediately visible on graph
    edge = p.connect("n1", "num_out", "n2", "num_in")
    assert edge in p.graph.list_edges()


def test_24_and_25_components_not_instantiated_or_executed(
    test_registry: ComponentRegistry,
) -> None:
    """24 & 25. Pipeline construction, validation, and ordering never call setup/run."""
    assert BuilderSpyComponent.instances_created == 0

    p = Pipeline(name="no-exec", registry=test_registry)
    p.add("prod", "test-producer", config={"cfg": 1})
    p.add("cons", "test-consumer", config={"cfg": 2})
    p.connect("prod", "num_out", "cons", "num_in")

    p.validate()
    order = p.execution_order()
    assert order == ["prod", "cons"]

    # Invariants: no instantiation, no setup, no run
    assert BuilderSpyComponent.instances_created == 0
    assert not BuilderSpyComponent.setup_called
    assert not BuilderSpyComponent.run_called
