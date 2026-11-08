"""Comprehensive unit tests for FinForge AI Local Synchronous Runtime Executor (FF-10).

Covers all 32+ required testing scenarios:
  - Successful execution: single-node, two-node, multi-node, branching, diamond DAG
  - Input & output passing, external inputs, validation
  - Component lifecycle: setup, run, teardown in reverse order, instance uniqueness
  - Error handling: setup failures, run failures, teardown failures, skipped nodes
  - Data isolation: defensive deep copies, non-shared mutable dictionaries
"""

from typing import Any

import pytest

from finforge import Pipeline
from finforge.component import BaseComponent
from finforge.exceptions import (
    CycleDetectedError,
    InputResolutionError,
)
from finforge.manifest import ComponentManifest, PortDefinition
from finforge.registry import ComponentRegistry
from finforge.runtime import (
    ExecutionStatus,
    LocalSynchronousExecutor,
)

# ---------------------------------------------------------------------------
# Test Components
# ---------------------------------------------------------------------------


class RuntimeSpyComponent(BaseComponent):
    """Component instrumented to record execution lifecycle events."""

    instances: list["RuntimeSpyComponent"] = []
    events: list[str] = []

    def __init__(self) -> None:
        self.node_id = ""
        self.setup_called = False
        self.run_called = False
        self.teardown_called = False
        self.config: dict[str, Any] = {}
        self.received_inputs: dict[str, Any] = {}
        self.received_context: dict[str, Any] = {}
        RuntimeSpyComponent.instances.append(self)

    def setup(self, config: dict[str, Any]) -> None:
        self.setup_called = True
        self.config = config
        RuntimeSpyComponent.events.append(f"setup:{config.get('id', 'unknown')}")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self.run_called = True
        self.received_inputs = inputs
        self.received_context = context
        node_id = context.get("node_id", "unknown")
        RuntimeSpyComponent.events.append(f"run:{node_id}")

        multiplier = self.config.get("multiplier", 1)
        val = inputs.get("val", 0)
        return {"out_val": val * multiplier}

    def teardown(self) -> None:
        self.teardown_called = True
        node_id = self.config.get("id", "unknown")
        RuntimeSpyComponent.events.append(f"teardown:{node_id}")

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()
        cls.events.clear()


class MultiSpyComponent(BaseComponent):
    """Component for multi-port testing."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        a = inputs.get("in_a", 0)
        b = inputs.get("in_b", 0)
        return {"out_a": a, "out_b": b}

    def teardown(self) -> None:
        pass


class FailingSetupComponent(BaseComponent):
    """Component whose setup() raises an exception."""

    teardown_called = False

    def setup(self, config: dict[str, Any]) -> None:
        raise ValueError("Simulated setup failure")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {}

    def teardown(self) -> None:
        FailingSetupComponent.teardown_called = True


class FailingRunComponent(BaseComponent):
    """Component whose run() raises an exception."""

    teardown_called = False

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Simulated run failure")

    def teardown(self) -> None:
        FailingRunComponent.teardown_called = True


class FailingTeardownComponent(BaseComponent):
    """Component whose teardown() raises an exception."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"out_val": inputs.get("val", 0)}

    def teardown(self) -> None:
        raise OSError("Simulated teardown failure")


class UninstantiableComponent(BaseComponent):
    """Component whose __init__ raises an error."""

    def __init__(self) -> None:
        raise RuntimeError("Cannot instantiate component")

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {}


class InvalidOutputComponent(BaseComponent):
    """Component that returns output violating output contract schema."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        # out_val is declared as integer, but return string
        return {"out_val": "not-an-integer"}


class MutatingComponent(BaseComponent):
    """Component that attempts to mutate its inputs in-place."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        lst = inputs.get("data", [])
        lst.append(9999)  # Mutate input list
        return {"data": lst}


@pytest.fixture(autouse=True)
def reset_tracker() -> None:
    RuntimeSpyComponent.reset()
    FailingSetupComponent.teardown_called = False
    FailingRunComponent.teardown_called = False


@pytest.fixture
def test_registry() -> ComponentRegistry:
    """Build a ComponentRegistry populated with standard test components."""
    registry = ComponentRegistry()

    # 1. Standard Spy Component
    registry.register(
        component_class=RuntimeSpyComponent,
        manifest=ComponentManifest(
            name="spy-comp",
            version="0.1.0",
            description="Spy component",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:RuntimeSpyComponent",
            inputs={"val": PortDefinition(type="integer", required=False)},
            outputs={"out_val": PortDefinition(type="integer")},
        ),
    )

    # 2. Multi-port transformer
    registry.register(
        component_class=MultiSpyComponent,
        manifest=ComponentManifest(
            name="multi-comp",
            version="0.1.0",
            description="Multi port component",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:MultiSpyComponent",
            inputs={
                "in_a": PortDefinition(type="integer", required=False),
                "in_b": PortDefinition(type="integer", required=False),
            },
            outputs={
                "out_a": PortDefinition(type="integer"),
                "out_b": PortDefinition(type="integer"),
            },
        ),
    )

    # 3. Failing setup component
    registry.register(
        component_class=FailingSetupComponent,
        manifest=ComponentManifest(
            name="fail-setup-comp",
            version="0.1.0",
            description="Failing setup",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:FailingSetupComponent",
            inputs={},
            outputs={},
        ),
    )

    # 4. Failing run component
    registry.register(
        component_class=FailingRunComponent,
        manifest=ComponentManifest(
            name="fail-run-comp",
            version="0.1.0",
            description="Failing run",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:FailingRunComponent",
            inputs={},
            outputs={},
        ),
    )

    # 5. Failing teardown component
    registry.register(
        component_class=FailingTeardownComponent,
        manifest=ComponentManifest(
            name="fail-teardown-comp",
            version="0.1.0",
            description="Failing teardown",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:FailingTeardownComponent",
            inputs={"val": PortDefinition(type="integer", required=False)},
            outputs={"out_val": PortDefinition(type="integer")},
        ),
    )

    # 6. Uninstantiable component
    registry.register(
        component_class=UninstantiableComponent,
        manifest=ComponentManifest(
            name="uninstantiable-comp",
            version="0.1.0",
            description="Uninstantiable",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:UninstantiableComponent",
            inputs={},
            outputs={},
        ),
    )

    # 7. Invalid output component
    registry.register(
        component_class=InvalidOutputComponent,
        manifest=ComponentManifest(
            name="invalid-output-comp",
            version="0.1.0",
            description="Invalid output",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:InvalidOutputComponent",
            inputs={},
            outputs={"out_val": PortDefinition(type="integer")},
        ),
    )

    # 8. Mutating component
    registry.register(
        component_class=MutatingComponent,
        manifest=ComponentManifest(
            name="mutating-comp",
            version="0.1.0",
            description="Mutates inputs",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:MutatingComponent",
            inputs={"data": PortDefinition(type="array")},
            outputs={"data": PortDefinition(type="array")},
        ),
    )

    return registry


# ---------------------------------------------------------------------------
# Section 1: Successful Execution (Tests 1 - 10)
# ---------------------------------------------------------------------------


def test_1_execute_single_node_pipeline(test_registry: ComponentRegistry) -> None:
    """1. Execute a single-node pipeline."""
    p = Pipeline(name="single", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 5})

    result = p.run(inputs={"n1": {"val": 10}})
    assert result.success
    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.get_output("n1", "out_val") == 50
    assert result.node_results["n1"].status == ExecutionStatus.SUCCEEDED


def test_2_execute_two_node_pipeline(test_registry: ComponentRegistry) -> None:
    """2. Execute a two-node pipeline passing data from n1 to n2."""
    p = Pipeline(name="two-node", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 2})
    p.add("n2", "spy-comp", config={"id": "n2", "multiplier": 3})
    p.connect("n1", "out_val", "n2", "val")

    result = p.run(inputs={"n1": {"val": 4}})
    assert result.success
    assert result.get_output("n1", "out_val") == 8
    # n2 receives 8 and multiplies by 3 = 24
    assert result.get_output("n2", "out_val") == 24


def test_3_execute_multi_node_pipeline(test_registry: ComponentRegistry) -> None:
    """3. Execute a 3-node linear chain: A -> B -> C."""
    p = Pipeline(name="chain", registry=test_registry)
    p.add("A", "spy-comp", config={"id": "A", "multiplier": 2})
    p.add("B", "spy-comp", config={"id": "B", "multiplier": 2})
    p.add("C", "spy-comp", config={"id": "C", "multiplier": 2})

    p.connect("A", "out_val", "B", "val")
    p.connect("B", "out_val", "C", "val")

    result = p.run(inputs={"A": {"val": 3}})
    assert result.success
    assert result.get_output("C", "out_val") == 24  # 3 * 2 * 2 * 2


def test_4_execute_branching_pipeline_sequentially(
    test_registry: ComponentRegistry,
) -> None:
    """4. Execute branching 1-to-many DAG: Root -> B1, Root -> B2."""
    p = Pipeline(name="branch", registry=test_registry)
    p.add("root", "spy-comp", config={"id": "root", "multiplier": 10})
    p.add("b1", "spy-comp", config={"id": "b1", "multiplier": 1})
    p.add("b2", "spy-comp", config={"id": "b2", "multiplier": 2})

    p.connect("root", "out_val", "b1", "val")
    p.connect("root", "out_val", "b2", "val")

    result = p.run(inputs={"root": {"val": 5}})
    assert result.success
    assert result.get_output("b1", "out_val") == 50
    assert result.get_output("b2", "out_val") == 100


def test_5_execute_diamond_shaped_dag(test_registry: ComponentRegistry) -> None:
    """5. Execute diamond graph: S -> Left, Right -> Sink."""
    p = Pipeline(name="diamond", registry=test_registry)
    p.add("source", "spy-comp", config={"id": "source", "multiplier": 2})
    p.add("left", "spy-comp", config={"id": "left", "multiplier": 3})
    p.add("right", "spy-comp", config={"id": "right", "multiplier": 4})
    p.add("sink", "multi-comp", config={"id": "sink"})

    p.connect("source", "out_val", "left", "val")
    p.connect("source", "out_val", "right", "val")
    p.connect("left", "out_val", "sink", "in_a")
    p.connect("right", "out_val", "sink", "in_b")

    result = p.run(inputs={"source": {"val": 5}})
    assert result.success
    # source produces 10
    # left receives 10 -> produces 30
    # right receives 10 -> produces 40
    # sink receives in_a=30, in_b=40
    assert result.get_output("sink", "out_a") == 30
    assert result.get_output("sink", "out_b") == 40


def test_6_pass_external_inputs_correctly(test_registry: ComponentRegistry) -> None:
    """6. External inputs are delivered accurately to target node ports."""
    p = Pipeline(name="ext-in", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 1})

    p.run(inputs={"n1": {"val": 777}})
    inst = RuntimeSpyComponent.instances[0]
    assert inst.received_inputs == {"val": 777}


def test_7_pass_upstream_outputs_to_downstream_inputs(
    test_registry: ComponentRegistry,
) -> None:
    """7. Connected edges properly map producer output to consumer input."""
    p = Pipeline(name="flow", registry=test_registry)
    p.add("producer", "spy-comp", config={"id": "p", "multiplier": 7})
    p.add("consumer", "spy-comp", config={"id": "c", "multiplier": 1})
    p.connect("producer", "out_val", "consumer", "val")

    p.run(inputs={"producer": {"val": 3}})
    consumer_inst = RuntimeSpyComponent.instances[1]
    assert consumer_inst.received_inputs["val"] == 21


def test_8_and_9_validate_inputs_and_outputs(
    test_registry: ComponentRegistry,
) -> None:
    """8 & 9. Strict schema validation is enforced for inputs and outputs."""
    p = Pipeline(name="contracts", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})

    # Supplying invalid string for integer input port triggers contract failure
    res = p.run(inputs={"n1": {"val": "not-an-int"}})
    assert not res.success
    assert res.status == ExecutionStatus.FAILED
    assert "Input validation failed on node 'n1'" in res.execution_errors[0]


def test_10_collect_final_outputs_correctly(test_registry: ComponentRegistry) -> None:
    """10. Outputs from all nodes are collected in result.outputs."""
    p = Pipeline(name="collect", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 1})
    p.add("n2", "spy-comp", config={"id": "n2", "multiplier": 10})

    result = p.run(inputs={"n1": {"val": 5}, "n2": {"val": 2}})
    assert result.outputs == {
        "n1": {"out_val": 5},
        "n2": {"out_val": 20},
    }


# ---------------------------------------------------------------------------
# Section 2: Lifecycle and Resource Management (Tests 11 - 18)
# ---------------------------------------------------------------------------


def test_11_setup_called_before_run(test_registry: ComponentRegistry) -> None:
    """11. setup() is called before run()."""
    p = Pipeline(name="lifecycle", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})
    p.run(inputs={"n1": {"val": 1}})

    assert RuntimeSpyComponent.events == ["setup:n1", "run:n1", "teardown:n1"]


def test_12_teardown_called_after_success(test_registry: ComponentRegistry) -> None:
    """12. teardown() is called for all initialized instances after success."""
    p = Pipeline(name="teardown-success", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})
    p.add("n2", "spy-comp", config={"id": "n2"})
    p.connect("n1", "out_val", "n2", "val")

    p.run(inputs={"n1": {"val": 1}})
    assert len(RuntimeSpyComponent.instances) == 2
    assert all(inst.teardown_called for inst in RuntimeSpyComponent.instances)


def test_13_each_node_gets_separate_instance(
    test_registry: ComponentRegistry,
) -> None:
    """13. Multiple nodes using the same component get distinct instances."""
    p = Pipeline(name="distinct-inst", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})
    p.add("n2", "spy-comp", config={"id": "n2"})

    p.run(inputs={"n1": {"val": 1}, "n2": {"val": 2}})
    assert len(RuntimeSpyComponent.instances) == 2
    assert RuntimeSpyComponent.instances[0] is not RuntimeSpyComponent.instances[1]


def test_14_setup_failure_prevents_run(test_registry: ComponentRegistry) -> None:
    """14. A failure in setup() prevents calling run()."""
    p = Pipeline(name="setup-fail", registry=test_registry)
    p.add("bad", "fail-setup-comp")

    res = p.run()
    assert not res.success
    assert res.node_results["bad"].status == ExecutionStatus.FAILED
    assert "setup() failed on node 'bad'" in res.execution_errors[0]


def test_15_run_failure_triggers_teardown_for_initialized_components(
    test_registry: ComponentRegistry,
) -> None:
    """15. Run failure still triggers teardown for all initialized components."""
    p = Pipeline(name="run-fail", registry=test_registry)
    p.add("step1_first", "spy-comp", config={"id": "step1_first"})
    p.add("step2_bad", "fail-run-comp")
    p.add("step3_third", "spy-comp", config={"id": "step3_third"})

    res = p.run()
    assert not res.success
    # 'step1_first' succeeded in setup and run -> must be torn down
    first_inst = RuntimeSpyComponent.instances[0]
    assert first_inst.teardown_called
    # 'step2_bad' succeeded in setup, failed in run -> must also be torn down
    assert FailingRunComponent.teardown_called
    # 'step3_third' was skipped, never initialized -> not torn down


def test_16_one_teardown_failure_does_not_prevent_others(
    test_registry: ComponentRegistry,
) -> None:
    """16. One teardown failure does not prevent subsequent teardowns."""
    p = Pipeline(name="teardown-fail", registry=test_registry)
    p.add("good1", "spy-comp", config={"id": "good1"})
    p.add("bad_teardown", "fail-teardown-comp")
    p.add("good2", "spy-comp", config={"id": "good2"})

    res = p.run()
    # Teardown executed in reverse order: good2, bad_teardown, good1
    assert not res.success  # Cleanup failure marks run as failed
    assert len(res.cleanup_errors) == 1
    assert "Teardown error on node 'bad_teardown'" in res.cleanup_errors[0]
    # Both good1 and good2 had their teardown called
    assert all(inst.teardown_called for inst in RuntimeSpyComponent.instances)


def test_17_execution_failure_preserved_when_teardown_also_fails(
    test_registry: ComponentRegistry,
) -> None:
    """17. Original run execution failure is preserved even if teardown also fails."""
    p = Pipeline(name="double-fail", registry=test_registry)
    p.add("step1_bad_teardown", "fail-teardown-comp")
    p.add("step2_bad_run", "fail-run-comp")

    res = p.run()
    assert not res.success
    assert "run() failed on node 'step2_bad_run'" in res.execution_errors[0]
    assert "Teardown error on node 'step1_bad_teardown'" in res.cleanup_errors[0]


def test_18_teardown_not_called_if_setup_fails(
    test_registry: ComponentRegistry,
) -> None:
    """18. If setup() fails, teardown() is NOT called for that instance."""
    p = Pipeline(name="no-teardown-on-setup-fail", registry=test_registry)
    p.add("bad_setup", "fail-setup-comp")

    p.run()
    assert not FailingSetupComponent.teardown_called


# ---------------------------------------------------------------------------
# Section 3: Error Handling & Diagnostics (Tests 19 - 27)
# ---------------------------------------------------------------------------


def test_19_invalid_graph_prevents_execution(
    test_registry: ComponentRegistry,
) -> None:
    """19. Graph validation error (e.g. cycle) halts execution immediately."""
    p = Pipeline(name="invalid-graph", registry=test_registry)
    p.add("n1", "multi-comp")
    p.add("n2", "multi-comp")
    # Manually force cycle into graph
    from finforge.pipeline import PipelineEdge

    p.graph._edges.append(
        PipelineEdge(
            source_node_id="n1",
            source_port="out_a",
            destination_node_id="n2",
            destination_port="in_a",
        )
    )
    p.graph._edges.append(
        PipelineEdge(
            source_node_id="n2",
            source_port="out_a",
            destination_node_id="n1",
            destination_port="in_a",
        )
    )

    with pytest.raises(CycleDetectedError):
        p.run()


def test_20_missing_required_input_is_reported(
    test_registry: ComponentRegistry,
) -> None:
    """20. Missing required input is caught and reported."""
    # Register component requiring mandatory input
    registry = ComponentRegistry()
    registry.register(
        component_class=RuntimeSpyComponent,
        manifest=ComponentManifest(
            name="req-comp",
            version="0.1.0",
            description="Req comp",
            category="data-processing",
            entrypoint="tests.unit.test_runtime:RuntimeSpyComponent",
            inputs={"mandatory": PortDefinition(type="integer", required=True)},
            outputs={},
        ),
    )
    p = Pipeline(name="req-pipeline", registry=registry)
    p.add("n1", "req-comp")

    # Run without supplying mandatory input
    res = p.run()
    assert not res.success
    assert res.node_results["n1"].status == ExecutionStatus.FAILED
    assert "Missing required input 'mandatory'" in res.node_results["n1"].error_details  # type: ignore[operator]


def test_21_invalid_input_type_is_reported(test_registry: ComponentRegistry) -> None:
    """21. Passing wrong type to port reports ContractValidationError."""
    p = Pipeline(name="bad-input-type", registry=test_registry)
    p.add("n1", "spy-comp")

    res = p.run(inputs={"n1": {"val": [1, 2, 3]}})  # expected integer
    assert not res.success
    assert "Invalid type for 'val'" in res.node_results["n1"].error_details  # type: ignore[operator]


def test_22_invalid_output_type_is_reported(test_registry: ComponentRegistry) -> None:
    """22. Component returning wrong type reports ContractValidationError."""
    p = Pipeline(name="bad-output-type", registry=test_registry)
    p.add("bad_out", "invalid-output-comp")

    res = p.run()
    assert not res.success
    assert res.node_results["bad_out"].status == ExecutionStatus.FAILED
    assert "Invalid type for 'out_val'" in res.node_results["bad_out"].error_details  # type: ignore[operator]


def test_23_component_instantiation_failure_reported(
    test_registry: ComponentRegistry,
) -> None:
    """23. Instantiation failure marks node FAILED."""
    p = Pipeline(name="uninstantiable", registry=test_registry)
    p.add("bad", "uninstantiable-comp")

    res = p.run()
    assert not res.success
    assert res.node_results["bad"].status == ExecutionStatus.FAILED
    assert "Instantiation error" in res.node_results["bad"].error_details  # type: ignore[operator]


def test_24_and_25_component_run_failure_marks_node_failed(
    test_registry: ComponentRegistry,
) -> None:
    """24 & 25. Run failure marks node FAILED with error details."""
    p = Pipeline(name="fail-run", registry=test_registry)
    p.add("bad", "fail-run-comp")

    res = p.run()
    assert not res.success
    assert res.node_results["bad"].status == ExecutionStatus.FAILED
    assert "Simulated run failure" in res.node_results["bad"].error_details  # type: ignore[operator]


def test_26_unexecuted_nodes_are_marked_skipped(
    test_registry: ComponentRegistry,
) -> None:
    """26. Nodes following a failed node in execution order are marked SKIPPED."""
    p = Pipeline(name="skip-chain", registry=test_registry)
    p.add("first", "spy-comp", config={"id": "first"})
    p.add("second_fail", "fail-run-comp")
    p.add("third", "spy-comp", config={"id": "third"})

    res = p.run()
    assert not res.success
    assert res.node_results["first"].status == ExecutionStatus.SUCCEEDED
    assert res.node_results["second_fail"].status == ExecutionStatus.FAILED
    assert res.node_results["third"].status == ExecutionStatus.SKIPPED


def test_27_partial_outputs_not_represented_as_complete_success(
    test_registry: ComponentRegistry,
) -> None:
    """27. Partial outputs are saved for debugging, but success is False."""
    p = Pipeline(name="partial-out", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 2})
    p.add("n2", "fail-run-comp")

    res = p.run(inputs={"n1": {"val": 10}})
    assert not res.success
    assert res.status == ExecutionStatus.FAILED
    # Partial output from n1 is accessible
    assert res.get_output("n1", "out_val") == 20
    # n2 produced no output
    assert res.get_output("n2") is None


# ---------------------------------------------------------------------------
# Section 4: Isolation & Edge Cases (Tests 28 - 32)
# ---------------------------------------------------------------------------


def test_28_and_29_mutating_inputs_does_not_corrupt_upstream_outputs(
    test_registry: ComponentRegistry,
) -> None:
    """28 & 29. Mutating input data does not corrupt upstream stored outputs."""
    p = Pipeline(name="mutate-test", registry=test_registry)
    p.add("mut1", "mutating-comp")
    p.add("mut2", "mutating-comp")
    p.connect("mut1", "data", "mut2", "data")

    # Initial input: [1, 2, 3]
    initial_input = [1, 2, 3]
    res = p.run(inputs={"mut1": {"data": initial_input}})

    assert res.success
    # mut1 received copy of [1, 2, 3] and appended 9999 -> [1, 2, 3, 9999]
    assert res.get_output("mut1", "data") == [1, 2, 3, 9999]
    # mut2 received copy of [1, 2, 3, 9999] and appended 9999 -> [1, 2, 3, 9999, 9999]
    assert res.get_output("mut2", "data") == [1, 2, 3, 9999, 9999]
    # The external initial_input array was NOT mutated
    assert initial_input == [1, 2, 3]


def test_30_consecutive_executions_do_not_reuse_stale_instances(
    test_registry: ComponentRegistry,
) -> None:
    """30. Each pipeline.run() creates fresh component instances."""
    p = Pipeline(name="fresh-inst", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})

    p.run(inputs={"n1": {"val": 1}})
    first_run_instances = list(RuntimeSpyComponent.instances)

    p.run(inputs={"n1": {"val": 2}})
    second_run_instances = [
        inst
        for inst in RuntimeSpyComponent.instances
        if inst not in first_run_instances
    ]

    assert len(first_run_instances) == 1
    assert len(second_run_instances) == 1
    assert first_run_instances[0] is not second_run_instances[0]


def test_31_execution_context_contains_only_documented_info(
    test_registry: ComponentRegistry,
) -> None:
    """31. Context dictionary supplied to component contains only documented fields."""
    p = Pipeline(name="context-test", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})

    p.run(
        inputs={"n1": {"val": 1}},
        context={"custom_key": "custom_val"},
    )
    inst = RuntimeSpyComponent.instances[0]
    ctx = inst.received_context
    assert set(ctx.keys()) == {
        "pipeline_name",
        "node_id",
        "component_name",
        "metadata",
    }
    assert ctx["pipeline_name"] == "context-test"
    assert ctx["node_id"] == "n1"
    assert ctx["component_name"] == "spy-comp"
    assert ctx["metadata"] == {"custom_key": "custom_val"}


def test_external_inputs_validation_errors(test_registry: ComponentRegistry) -> None:
    """Test validation errors on external inputs dictionary."""
    p = Pipeline(name="ext-err", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1"})
    p.add("n2", "spy-comp", config={"id": "n2"})
    p.connect("n1", "out_val", "n2", "val")

    # 1. Invalid inputs type (not dict)
    with pytest.raises(InputResolutionError, match="must be a dict"):
        p.run(inputs="not-a-dict")  # type: ignore[arg-type]

    # 2. Unknown node ID
    with pytest.raises(InputResolutionError, match="unknown node 'ghost'"):
        p.run(inputs={"ghost": {"val": 1}})

    # 3. Invalid port value container
    with pytest.raises(InputResolutionError, match="must be a dict of port values"):
        p.run(inputs={"n1": "not-a-dict"})  # type: ignore[dict-item]

    # 4. Unknown port on component
    with pytest.raises(InputResolutionError, match="Unexpected external input port"):
        p.run(inputs={"n1": {"unknown_port": 123}})

    # 5. Overriding connected port
    with pytest.raises(InputResolutionError, match="already connected"):
        p.run(inputs={"n2": {"val": 999}})


def test_executor_direct_execution_on_pipeline_graph(
    test_registry: ComponentRegistry,
) -> None:
    """Verify LocalSynchronousExecutor can execute PipelineGraph directly."""
    p = Pipeline(name="graph-exec", registry=test_registry)
    p.add("n1", "spy-comp", config={"id": "n1", "multiplier": 2})

    executor = LocalSynchronousExecutor()
    res = executor.execute(p.graph, inputs={"n1": {"val": 7}})
    assert res.success
    assert res.get_output("n1", "out_val") == 14
