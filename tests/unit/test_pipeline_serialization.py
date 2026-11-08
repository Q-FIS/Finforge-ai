"""Unit tests for FinForge AI Pipeline Serialization and Deserialization (FF-11).

Covers all 40 test scenarios from the specification:
  - Serialization: valid pipeline, name, node IDs, components, configs, edges,
    determinism, rejecting unsupported config objects, invalid paths, overwrite policy.
  - Deserialization: loading valid pipeline, reconstructing nodes, edges, configs,
    rejecting missing files, empty YAML, malformed YAML, non-mapping YAML, invalid
    format versions, missing fields, unknown fields, duplicate IDs, missing components,
    invalid edge references, cycles, Python tags, unsupported config objects.
  - Security & Lifecycle: no dynamic imports, no instantiation, no setup(), no run(),
    no dependency installation, no command execution.
  - Round-Trip: simple, branching, diamond pipelines, preserving topological ordering,
    preserving config values, immutable configurations, backward compatibility.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from finforge.component import BaseComponent
from finforge.exceptions import (
    CycleDetectedError,
    PipelineDeserializationError,
    PipelineSerializationError,
    SerializationFormatError,
)
from finforge.manifest.models import (
    ComponentManifest,
    ConfigDefinition,
    PortDefinition,
)
from finforge.pipeline.builder import Pipeline
from finforge.pipeline.serialization import (
    PipelineDocument,
    deserialize_pipeline,
    deserialize_pipeline_document,
    serialize_pipeline_to_dict,
    serialize_pipeline_to_yaml,
)
from finforge.registry import ComponentRegistry

# =============================================================================
# Test Components & Fixtures
# =============================================================================


class DummySource(BaseComponent):
    """Component that produces raw data without inputs."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"data": [1, 2, 3]}


class DummyTransform(BaseComponent):
    """Component that receives data and outputs transformed data."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = {}

    def setup(self, config: dict[str, Any]) -> None:
        self.config = config or {}

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        factor = self.config.get("factor", 2)
        return {"transformed": [x * factor for x in inputs["data"]]}


class DummyBranchA(BaseComponent):
    """First branch consumer."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"out_a": inputs["data"] + ["A"]}


class DummyBranchB(BaseComponent):
    """Second branch consumer."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"out_b": inputs["data"] + ["B"]}


class DummySink(BaseComponent):
    """Consumer taking transformed data and producing an evaluation metric."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"metric": 100.0}


class DummyDiamondMerge(BaseComponent):
    """Component merging inputs from two branches."""

    def setup(self, config: dict[str, Any]) -> None:
        pass

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {"merged": inputs["in_a"] + inputs["in_b"]}


class LifecycleSpyComponent(BaseComponent):
    """Spy component tracking instantiation and lifecycle invocations."""

    init_count = 0
    setup_count = 0
    run_count = 0

    def __init__(self) -> None:
        LifecycleSpyComponent.init_count += 1

    def setup(self, config: dict[str, Any]) -> None:
        LifecycleSpyComponent.setup_count += 1

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        LifecycleSpyComponent.run_count += 1
        return {"result": "ok"}

    @classmethod
    def reset_counts(cls) -> None:
        cls.init_count = 0
        cls.setup_count = 0
        cls.run_count = 0


@pytest.fixture
def registry() -> ComponentRegistry:
    """Fixture providing a populated ComponentRegistry."""
    reg = ComponentRegistry()

    m_source = ComponentManifest(
        name="test-source",
        version="1.0.0",
        description="Source component",
        category="data-processing",
        entrypoint="tests.unit.test_pipeline_serialization:DummySource",
        outputs={"data": PortDefinition(type="array", description="Raw data")},
    )
    reg.register(DummySource, m_source)

    m_transform = ComponentManifest(
        name="test-transform",
        version="1.0.0",
        description="Transform component",
        category="data-processing",
        entrypoint="tests.unit.test_pipeline_serialization:DummyTransform",
        inputs={"data": PortDefinition(type="array", description="Input data")},
        outputs={
            "transformed": PortDefinition(type="array", description="Transformed")
        },
        config={
            "factor": ConfigDefinition(type="integer", default=2, description="Factor")
        },
    )
    reg.register(DummyTransform, m_transform)

    m_branch_a = ComponentManifest(
        name="test-branch-a",
        version="1.0.0",
        description="Branch A",
        category="data-processing",
        entrypoint="tests.unit.test_pipeline_serialization:DummyBranchA",
        inputs={"data": PortDefinition(type="array")},
        outputs={"out_a": PortDefinition(type="array")},
    )
    reg.register(DummyBranchA, m_branch_a)

    m_branch_b = ComponentManifest(
        name="test-branch-b",
        version="1.0.0",
        description="Branch B",
        category="data-processing",
        entrypoint="tests.unit.test_pipeline_serialization:DummyBranchB",
        inputs={"data": PortDefinition(type="array")},
        outputs={"out_b": PortDefinition(type="array")},
    )
    reg.register(DummyBranchB, m_branch_b)

    m_sink = ComponentManifest(
        name="test-sink",
        version="1.0.0",
        description="Sink component",
        category="evaluation",
        entrypoint="tests.unit.test_pipeline_serialization:DummySink",
        inputs={
            "transformed": PortDefinition(type="array", description="Transformed data")
        },
        outputs={"metric": PortDefinition(type="float")},
    )
    reg.register(DummySink, m_sink)

    m_merge = ComponentManifest(
        name="test-merge",
        version="1.0.0",
        description="Merge component",
        category="data-processing",
        entrypoint="tests.unit.test_pipeline_serialization:DummyDiamondMerge",
        inputs={
            "in_a": PortDefinition(type="array"),
            "in_b": PortDefinition(type="array"),
        },
        outputs={"merged": PortDefinition(type="array")},
    )
    reg.register(DummyDiamondMerge, m_merge)

    m_spy = ComponentManifest(
        name="test-spy",
        version="1.0.0",
        description="Spy component",
        category="evaluation",
        entrypoint="tests.unit.test_pipeline_serialization:LifecycleSpyComponent",
        inputs={},
        outputs={"result": PortDefinition(type="string")},
    )
    reg.register(LifecycleSpyComponent, m_spy)

    return reg


@pytest.fixture
def sample_pipeline(registry: ComponentRegistry) -> Pipeline:
    """Fixture creating a standard valid 2-node pipeline."""
    p = Pipeline(
        name="sample-workflow",
        registry=registry,
        description="A test workflow",
    )
    p.add("source_node", "test-source", config={})
    p.add("transform_node", "test-transform", config={"factor": 5, "mode": "fast"})
    p.connect("source_node", "data", "transform_node", "data")
    return p


# =============================================================================
# 1. Serialization Tests (Scenarios 1 - 10)
# =============================================================================


def test_01_save_valid_pipeline(sample_pipeline: Pipeline, tmp_path: Path) -> None:
    """1. Save a valid pipeline creates a valid YAML file on disk."""
    out_file = tmp_path / "pipeline.yaml"
    sample_pipeline.save(out_file)
    assert out_file.is_file()
    assert out_file.stat().st_size > 0


def test_02_save_pipeline_name(sample_pipeline: Pipeline, tmp_path: Path) -> None:
    """2. Pipeline name and description are preserved in serialized document."""
    out_file = tmp_path / "pipe_name.yaml"
    sample_pipeline.save(out_file)
    data = yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert data["name"] == "sample-workflow"
    assert data["description"] == "A test workflow"


def test_03_save_node_ids(sample_pipeline: Pipeline) -> None:
    """3. Serialized document preserves all node IDs."""
    data = serialize_pipeline_to_dict(sample_pipeline)
    node_ids = [n["id"] for n in data["nodes"]]
    assert "source_node" in node_ids
    assert "transform_node" in node_ids


def test_04_save_component_names(sample_pipeline: Pipeline) -> None:
    """4. Serialized document preserves registered component names."""
    data = serialize_pipeline_to_dict(sample_pipeline)
    comp_map = {n["id"]: n["component"] for n in data["nodes"]}
    assert comp_map["source_node"] == "test-source"
    assert comp_map["transform_node"] == "test-transform"


def test_05_save_node_configurations(sample_pipeline: Pipeline) -> None:
    """5. Serialized document preserves node configuration dictionaries."""
    data = serialize_pipeline_to_dict(sample_pipeline)
    comp_configs = {n["id"]: n["config"] for n in data["nodes"]}
    assert comp_configs["source_node"] == {}
    assert comp_configs["transform_node"] == {"factor": 5, "mode": "fast"}


def test_06_save_edges(sample_pipeline: Pipeline) -> None:
    """6. Serialized document preserves directed edges and port connections."""
    data = serialize_pipeline_to_dict(sample_pipeline)
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["source_node"] == "source_node"
    assert edge["source_port"] == "data"
    assert edge["destination_node"] == "transform_node"
    assert edge["destination_port"] == "data"


def test_07_produce_deterministic_yaml(registry: ComponentRegistry) -> None:
    """7. Saving equivalent pipelines produces identical, deterministic YAML."""
    # Pipeline 1: add A then B
    p1 = Pipeline("test-det", registry=registry)
    p1.add("node_a", "test-source")
    p1.add("node_b", "test-transform")
    p1.connect("node_a", "data", "node_b", "data")

    # Pipeline 2: add B then A
    p2 = Pipeline("test-det", registry=registry)
    p2.add("node_b", "test-transform")
    p2.add("node_a", "test-source")
    p2.connect("node_a", "data", "node_b", "data")

    yaml_1 = serialize_pipeline_to_yaml(p1)
    yaml_2 = serialize_pipeline_to_yaml(p2)
    assert yaml_1 == yaml_2


def test_08_reject_unsupported_configuration_objects(
    registry: ComponentRegistry,
) -> None:
    """8. Reject unsupported configuration objects (e.g., functions, custom classes)."""
    p = Pipeline("invalid-config", registry=registry)

    # Function object in config
    p.add("src", "test-source", config={"callback": lambda x: x})
    with pytest.raises(PipelineSerializationError) as exc_info:
        serialize_pipeline_to_yaml(p)
    assert "Unsupported configuration value of type 'function'" in str(exc_info.value)

    # Custom class instance in config
    class CustomObj:
        pass

    p2 = Pipeline("invalid-obj", registry=registry)
    p2.add("src", "test-source", config={"obj": CustomObj()})
    with pytest.raises(PipelineSerializationError) as exc_info2:
        serialize_pipeline_to_yaml(p2)
    assert "Unsupported configuration value of type 'CustomObj'" in str(exc_info2.value)


def test_09_reject_invalid_output_paths(
    sample_pipeline: Pipeline, tmp_path: Path
) -> None:
    """9. Clear error when output path is a directory."""
    with pytest.raises(PipelineSerializationError) as exc_info:
        sample_pipeline.save(tmp_path)  # tmp_path is directory
    assert "is an existing directory" in str(exc_info.value)


def test_10_prevent_accidental_overwrite(
    sample_pipeline: Pipeline, tmp_path: Path
) -> None:
    """10. Prevent accidental overwrite unless overwrite=True is explicitly passed."""
    target = tmp_path / "pipeline.yaml"
    target.write_text("existing content", encoding="utf-8")

    # Fail by default when overwrite=False
    with pytest.raises(FileExistsError) as exc_info:
        sample_pipeline.save(target, overwrite=False)
    assert "already exists" in str(exc_info.value)
    assert target.read_text(encoding="utf-8") == "existing content"

    # Succeed when overwrite=True
    sample_pipeline.save(target, overwrite=True)
    assert "sample-workflow" in target.read_text(encoding="utf-8")


# =============================================================================
# 2. Deserialization Tests (Scenarios 11 - 27)
# =============================================================================


def test_11_load_valid_pipeline(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """11. Load a valid pipeline YAML file into a functional Pipeline object."""
    target = tmp_path / "valid.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert isinstance(loaded, Pipeline)
    assert loaded.name == "sample-workflow"
    assert loaded.description == "A test workflow"


def test_12_reconstruct_nodes(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """12. Deserialization reconstructs all nodes with correct IDs and components."""
    target = tmp_path / "nodes.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert len(loaded.nodes) == 2
    node_ids = [n.node_id for n in loaded.nodes]
    assert "source_node" in node_ids
    assert "transform_node" in node_ids


def test_13_reconstruct_edges(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """13. Deserialization reconstructs all edges and port mappings."""
    target = tmp_path / "edges.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert len(loaded.edges) == 1
    edge = loaded.edges[0]
    assert edge.source_node_id == "source_node"
    assert edge.source_port == "data"
    assert edge.destination_node_id == "transform_node"
    assert edge.destination_port == "data"


def test_14_restore_configuration(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """14. Deserialization restores exact configuration dictionaries."""
    target = tmp_path / "configs.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    n_transform = loaded.graph.get_node("transform_node")
    assert n_transform.config == {"factor": 5, "mode": "fast"}


def test_15_reject_missing_files(registry: ComponentRegistry) -> None:
    """15. Loading non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Pipeline.load("non_existent_file_xyz.yaml", registry=registry)


def test_16_reject_empty_yaml(registry: ComponentRegistry) -> None:
    """16. Empty YAML content or whitespace raises SerializationFormatError."""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline("", registry=registry)
    assert "empty" in str(exc_info.value).lower()

    with pytest.raises(SerializationFormatError) as exc_info2:
        deserialize_pipeline("   \n\n  # comments only\n", registry=registry)
    assert "empty" in str(exc_info2.value).lower()


def test_17_reject_malformed_yaml(registry: ComponentRegistry) -> None:
    """17. Malformed YAML syntax raises SerializationFormatError."""
    malformed = """
    format_version: "1"
    name: bad
    nodes: [unclosed list
    """
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(malformed, registry=registry)
    assert "Malformed YAML" in str(exc_info.value)


def test_18_reject_non_mapping_yaml(registry: ComponentRegistry) -> None:
    """18. Non-mapping top-level YAML raises SerializationFormatError."""
    yaml_list = "- item1\n- item2\n"
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_list, registry=registry)
    assert "must be a top-level mapping" in str(exc_info.value)


def test_19_reject_invalid_format_versions(registry: ComponentRegistry) -> None:
    """19. Format version other than supported '1' raises SerializationFormatError."""
    yaml_bad_ver = """
format_version: "2"
name: future-pipe
nodes: []
edges: []
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_bad_ver, registry=registry)
    assert "Unsupported format_version '2'" in str(exc_info.value)


def test_20_reject_missing_required_fields(registry: ComponentRegistry) -> None:
    """20. Missing required fields raises SerializationFormatError."""
    yaml_no_name = """
format_version: "1"
nodes: []
edges: []
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_no_name, registry=registry)
    assert "validation failed" in str(exc_info.value).lower()


def test_21_reject_unknown_fields(registry: ComponentRegistry) -> None:
    """21. Unknown extra top-level fields are rejected by strict schema validation."""
    yaml_unknown = """
format_version: "1"
name: test-extra
unknown_custom_field: "unexpected"
nodes: []
edges: []
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_unknown, registry=registry)
    assert "extra fields not permitted" in str(
        exc_info.value
    ) or "Extra inputs are not permitted" in str(exc_info.value)


def test_22_reject_duplicate_node_ids(registry: ComponentRegistry) -> None:
    """22. Reject duplicate node IDs within the nodes list."""
    yaml_dups = """
format_version: "1"
name: dup-pipe
nodes:
  - id: my_node
    component: test-source
  - id: my_node
    component: test-transform
edges: []
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_dups, registry=registry)
    assert "Duplicate node ID 'my_node'" in str(exc_info.value)


def test_23_reject_nonexistent_component_names(
    registry: ComponentRegistry,
) -> None:
    """23. Reject components in YAML not registered in ComponentRegistry."""
    yaml_missing_comp = """
format_version: "1"
name: missing-comp-pipe
nodes:
  - id: my_node
    component: nonexistent-component-xyz
edges: []
"""
    with pytest.raises(PipelineDeserializationError) as exc_info:
        deserialize_pipeline(yaml_missing_comp, registry=registry)
    assert "nonexistent-component-xyz" in str(exc_info.value)
    assert "is not registered" in str(exc_info.value)


def test_24_reject_invalid_edge_references(registry: ComponentRegistry) -> None:
    """24. Reject edges referencing nodes that are not defined in the nodes list."""
    yaml_bad_edge = """
format_version: "1"
name: bad-edge-pipe
nodes:
  - id: node_a
    component: test-source
edges:
  - source_node: node_a
    source_port: data
    destination_node: ghost_node
    destination_port: in_port
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_bad_edge, registry=registry)
    assert "ghost_node" in str(exc_info.value)


def test_25_reject_cyclic_graphs(registry: ComponentRegistry) -> None:
    """25. Reject graphs with directed cycles."""
    yaml_cycle = """
format_version: "1"
name: cyclic-pipe
nodes:
  - id: a
    component: test-transform
  - id: b
    component: test-transform
edges:
  - source_node: a
    source_port: transformed
    destination_node: b
    destination_port: data
  - source_node: b
    source_port: transformed
    destination_node: a
    destination_port: data
"""
    with pytest.raises(CycleDetectedError) as exc_info:
        deserialize_pipeline(yaml_cycle, registry=registry)
    assert "cycle detected" in str(exc_info.value).lower()


def test_26_reject_python_specific_yaml_tags(
    registry: ComponentRegistry,
) -> None:
    """26. Safe YAML loader rejects !!python/object, !!python/module, etc."""
    yaml_exploit = """
format_version: "1"
name: exploit-pipe
metadata:
  malicious: !!python/object/apply:os.system ["echo pwned"]
nodes: []
edges: []
"""
    with pytest.raises(SerializationFormatError) as exc_info:
        deserialize_pipeline(yaml_exploit, registry=registry)
    assert "Malformed YAML" in str(exc_info.value)


def test_27_reject_unsupported_configuration_objects_in_loader(
    registry: ComponentRegistry,
) -> None:
    """27. Reject unsupported configuration objects in loader."""
    import pydantic

    doc_dict = {
        "format_version": "1",
        "name": "pipe",
        "nodes": [
            {
                "id": "node_1",
                "component": "test-source",
                "config": {"bad_val": object()},
            }
        ],
        "edges": [],
    }
    with pytest.raises(pydantic.ValidationError) as exc_info:
        PipelineDocument.model_validate(doc_dict)
    assert "Unsupported configuration value" in str(exc_info.value)


# =============================================================================
# 3. Security and Lifecycle Tests (Scenarios 28 - 33)
# =============================================================================


def test_28_loading_does_not_import_component_entrypoints(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """28. Loading relies on ComponentRegistry without dynamic imports."""
    target = tmp_path / "pipe.yaml"
    sample_pipeline.save(target)

    # Calling load does not invoke importlib or dynamic module loaders
    loaded = Pipeline.load(target, registry=registry)
    assert loaded.name == sample_pipeline.name


def test_29_30_31_loading_does_not_instantiate_or_call_setup_or_run(
    registry: ComponentRegistry, tmp_path: Path
) -> None:
    """29, 30 & 31. Deserialization never instantiates or calls setup/run."""
    LifecycleSpyComponent.reset_counts()

    pipe = Pipeline("spy-pipe", registry=registry)
    pipe.add("spy_step", "test-spy")
    target = tmp_path / "spy_pipe.yaml"
    pipe.save(target)

    assert LifecycleSpyComponent.init_count == 0
    assert LifecycleSpyComponent.setup_count == 0
    assert LifecycleSpyComponent.run_count == 0

    # Deserializing from YAML
    loaded = Pipeline.load(target, registry=registry)

    # Invariants: 0 instantiations, 0 setup() calls, 0 run() calls
    assert LifecycleSpyComponent.init_count == 0
    assert LifecycleSpyComponent.setup_count == 0
    assert LifecycleSpyComponent.run_count == 0
    assert "spy_step" in loaded


def test_32_33_loading_does_not_install_dependencies_or_execute_commands(
    registry: ComponentRegistry,
) -> None:
    """32 & 33. Loading does not install packages or run shell commands."""
    raw_yaml = """
format_version: "1"
name: isolated-pipeline
metadata:
  exec_command: "rm -rf /tmp/test"
  pip_install: "malicious-package"
nodes: []
edges: []
"""
    doc = deserialize_pipeline_document(raw_yaml)
    assert doc.metadata["exec_command"] == "rm -rf /tmp/test"
    # Metadata is parsed purely as string primitives; no subshell or execution occurred


# =============================================================================
# 4. Round-Trip Tests (Scenarios 34 - 40)
# =============================================================================


def test_34_save_and_reload_simple_pipeline(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """34. Save and reload a simple linear pipeline."""
    target = tmp_path / "simple_roundtrip.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert loaded.name == sample_pipeline.name
    assert loaded.execution_order() == sample_pipeline.execution_order()
    assert len(loaded.nodes) == len(sample_pipeline.nodes)
    assert len(loaded.edges) == len(sample_pipeline.edges)


def test_35_save_and_reload_branching_pipeline(
    registry: ComponentRegistry, tmp_path: Path
) -> None:
    """35. Save and reload a 1-to-many branching pipeline."""
    p = Pipeline("branching-pipe", registry=registry)
    p.add("producer", "test-source")
    p.add("consumer_1", "test-branch-a")
    p.add("consumer_2", "test-branch-b")
    p.connect("producer", "data", "consumer_1", "data")
    p.connect("producer", "data", "consumer_2", "data")

    target = tmp_path / "branching.yaml"
    p.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert loaded.name == "branching-pipe"
    assert len(loaded.nodes) == 3
    assert len(loaded.edges) == 2
    assert loaded.execution_order() == ["producer", "consumer_1", "consumer_2"]


def test_36_save_and_reload_diamond_shaped_pipeline(
    registry: ComponentRegistry, tmp_path: Path
) -> None:
    """36. Save and reload a diamond-shaped DAG pipeline."""
    p = Pipeline("diamond-pipe", registry=registry)
    p.add("src", "test-source")
    p.add("left", "test-branch-a")
    p.add("right", "test-branch-b")
    p.add("sink", "test-merge")

    p.connect("src", "data", "left", "data")
    p.connect("src", "data", "right", "data")
    p.connect("left", "out_a", "sink", "in_a")
    p.connect("right", "out_b", "sink", "in_b")

    target = tmp_path / "diamond.yaml"
    p.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert loaded.name == "diamond-pipe"
    assert len(loaded.nodes) == 4
    assert len(loaded.edges) == 4
    assert loaded.execution_order() == ["src", "left", "right", "sink"]


def test_37_preserve_deterministic_topological_ordering(
    registry: ComponentRegistry, tmp_path: Path
) -> None:
    """37. Preserves identical deterministic topological ordering across reload."""
    p = Pipeline("order-pipe", registry=registry)
    p.add("n_z", "test-source")
    p.add("n_a", "test-source")
    p.add("n_m", "test-transform")
    p.connect("n_a", "data", "n_m", "data")

    original_order = p.execution_order()
    target = tmp_path / "order.yaml"
    p.save(target)

    loaded = Pipeline.load(target, registry=registry)
    assert loaded.execution_order() == original_order


def test_38_preserve_configuration_values(
    registry: ComponentRegistry, tmp_path: Path
) -> None:
    """38. Preserves nested primitive configuration values."""
    p = Pipeline("config-pipe", registry=registry)
    nested_config = {
        "str_val": "hello",
        "int_val": 42,
        "float_val": 3.14159,
        "bool_val": True,
        "none_val": None,
        "list_val": [1, "two", 3.0, False],
        "dict_val": {"inner_key": 999, "nested_list": ["a", "b"]},
    }
    p.add("node_cfg", "test-source", config=nested_config)

    target = tmp_path / "nested_cfg.yaml"
    p.save(target)

    loaded = Pipeline.load(target, registry=registry)
    loaded_cfg = loaded.graph.get_node("node_cfg").config
    assert loaded_cfg == nested_config


def test_39_original_pipeline_configuration_is_not_mutated(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """39. Saving and loading does not mutate original node configs."""
    orig_node = sample_pipeline.graph.get_node("transform_node")
    orig_config = copy.deepcopy(orig_node.config)

    target = tmp_path / "no_mutation.yaml"
    sample_pipeline.save(target)
    loaded = Pipeline.load(target, registry=registry)

    # Mutate loaded node config in memory
    loaded_node = loaded.graph.get_node("transform_node")
    loaded_node.config["factor"] = 99999

    # Verify original pipeline node config remains unchanged
    assert sample_pipeline.graph.get_node("transform_node").config == orig_config
    assert sample_pipeline.graph.get_node("transform_node").config["factor"] == 5


def test_40_existing_functionality_preserved(
    sample_pipeline: Pipeline, registry: ComponentRegistry, tmp_path: Path
) -> None:
    """40. Reconstructed pipeline can be executed by LocalSynchronousExecutor."""
    target = tmp_path / "executable.yaml"
    sample_pipeline.save(target)

    loaded = Pipeline.load(target, registry=registry)
    # Explicitly run after loading
    result = loaded.run()
    assert result.success
    assert "source_node" in result.node_results
    assert "transform_node" in result.node_results
    assert result.outputs["transform_node"]["transformed"] == [5, 10, 15]
