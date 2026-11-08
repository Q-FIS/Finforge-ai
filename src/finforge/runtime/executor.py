"""Local synchronous runtime execution engine for FinForge AI.

This module provides `LocalSynchronousExecutor`, which executes pipeline graphs
locally and synchronously according to deterministic topological dependency order.
"""

from __future__ import annotations

import copy
import time
from typing import TYPE_CHECKING, Any

from finforge.contracts import validate_inputs, validate_outputs
from finforge.exceptions import (
    ContractValidationError,
    InputResolutionError,
)
from finforge.pipeline.graph import PipelineGraph
from finforge.runtime.context import ExecutionContext
from finforge.runtime.models import (
    ExecutionStatus,
    NodeExecutionResult,
    PipelineExecutionResult,
)

if TYPE_CHECKING:
    from finforge.component import BaseComponent
    from finforge.pipeline.builder import Pipeline


class LocalSynchronousExecutor:
    """Synchronous in-process execution engine for FinForge AI pipelines.

    The executor:
      1. Validates the pipeline DAG structure before running.
      2. Computes the deterministic topological execution order.
      3. Resolves inputs from upstream outputs and user-supplied external inputs.
      4. Validates inputs and outputs using strict contract validation.
      5. Instantiates and executes components sequentially.
      6. Guarantees teardown cleanup for all initialized component instances.
    """

    def execute(
        self,
        pipeline: Pipeline | PipelineGraph,
        inputs: dict[str, dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> PipelineExecutionResult:
        """Execute a pipeline synchronously.

        Args:
            pipeline: A Pipeline or PipelineGraph instance to execute.
            inputs: Optional external inputs keyed by node_id and port_name.
            context: Optional arbitrary execution metadata passed to components.

        Returns:
            A structured PipelineExecutionResult.

        Raises:
            TypeError: If pipeline is not a Pipeline or PipelineGraph instance.
            InputResolutionError: If external inputs reference unknown nodes/ports
                or collide with connected upstream ports.
            GraphValidationError: If pipeline graph structural validation fails.
            CycleDetectedError: If the pipeline contains a cycle.
            PortIncompatibleError: If port types are incompatible.
        """
        # 1. Resolve pipeline and graph
        if hasattr(pipeline, "graph") and hasattr(pipeline, "name"):
            graph: PipelineGraph = pipeline.graph
            pipeline_name: str = pipeline.name
        elif isinstance(pipeline, PipelineGraph):
            graph = pipeline
            pipeline_name = "pipeline"
        else:
            raise TypeError(
                f"Expected pipeline to be a Pipeline or PipelineGraph instance, "
                f"got '{type(pipeline).__name__}'."
            )

        # 2. Validate graph DAG structure before execution
        graph.validate()

        # 3. Calculate deterministic topological order
        order = graph.execution_order()

        # 4. Validate external inputs structure
        if inputs is not None:
            if not isinstance(inputs, dict):
                raise InputResolutionError(
                    f"External inputs must be a dict mapping node_id to port values, "
                    f"got '{type(inputs).__name__}'."
                )
            for node_id, port_dict in inputs.items():
                if not graph.has_node(node_id):
                    valid_nodes = [n.node_id for n in graph.list_nodes()]
                    raise InputResolutionError(
                        f"External inputs provided for unknown node '{node_id}'. "
                        f"Valid nodes in pipeline: {valid_nodes}."
                    )
                if not isinstance(port_dict, dict):
                    raise InputResolutionError(
                        f"External inputs for node '{node_id}' must be a dict of "
                        f"port values, got '{type(port_dict).__name__}'."
                    )

                # Check port collision with incoming edges and manifest existence
                incoming_edges = {
                    e.destination_port: e for e in graph.get_incoming_edges(node_id)
                }
                node_obj = graph.get_node(node_id)
                manifest = graph.registry.get_manifest(node_obj.component_name)

                for port_name in port_dict:
                    if port_name in incoming_edges:
                        edge = incoming_edges[port_name]
                        raise InputResolutionError(
                            f"Port '{port_name}' on node '{node_id}' is already "
                            f"connected to upstream output "
                            f"'{edge.source_node_id}.{edge.source_port}' and "
                            f"cannot be overridden by external inputs."
                        )
                    if port_name not in manifest.inputs:
                        declared = sorted(manifest.inputs.keys())
                        raise InputResolutionError(
                            f"Unexpected external input port '{port_name}' for node "
                            f"'{node_id}' (component '{manifest.name}'). "
                            f"Declared input ports: {declared}."
                        )

        # 5. Initialize tracking state
        start_time = time.perf_counter()
        node_results: dict[str, NodeExecutionResult] = {}
        all_outputs: dict[str, dict[str, Any]] = {}
        execution_errors: list[str] = []
        cleanup_errors: list[str] = []
        initialized_instances: list[tuple[str, BaseComponent]] = []
        overall_status = ExecutionStatus.SUCCEEDED

        def mark_remaining_skipped(start_idx: int) -> None:
            for rem_node_id in order[start_idx:]:
                rem_node = graph.get_node(rem_node_id)
                node_results[rem_node_id] = NodeExecutionResult(
                    node_id=rem_node_id,
                    component_name=rem_node.component_name,
                    status=ExecutionStatus.SKIPPED,
                )

        # 6. Execute nodes in topological order
        try:
            for idx, node_id in enumerate(order):
                node = graph.get_node(node_id)
                comp_name = node.component_name
                manifest = graph.registry.get_manifest(comp_name)

                # Step 6.1: Resolve inputs
                resolved_inputs: dict[str, Any] = {}
                for edge in graph.get_incoming_edges(node_id):
                    val = all_outputs[edge.source_node_id][edge.source_port]
                    resolved_inputs[edge.destination_port] = copy.deepcopy(val)

                if inputs and node_id in inputs:
                    for p_name, p_val in inputs[node_id].items():
                        resolved_inputs[p_name] = copy.deepcopy(p_val)

                # Step 6.2: Validate inputs against manifest contract
                try:
                    validate_inputs(resolved_inputs, manifest.inputs)
                except ContractValidationError as err:
                    overall_status = ExecutionStatus.FAILED
                    msg = f"Input validation failed on node '{node_id}': {err}"
                    execution_errors.append(msg)
                    node_results[node_id] = NodeExecutionResult(
                        node_id=node_id,
                        component_name=comp_name,
                        status=ExecutionStatus.FAILED,
                        inputs=copy.deepcopy(resolved_inputs),
                        error_details=str(err),
                    )
                    mark_remaining_skipped(idx + 1)
                    break

                # Step 6.3: Instantiate component class
                try:
                    comp_cls = graph.registry.get(comp_name)
                    instance = comp_cls()
                except Exception as err:
                    overall_status = ExecutionStatus.FAILED
                    msg = f"Component instantiation failed on node '{node_id}': {err}"
                    execution_errors.append(msg)
                    node_results[node_id] = NodeExecutionResult(
                        node_id=node_id,
                        component_name=comp_name,
                        status=ExecutionStatus.FAILED,
                        inputs=copy.deepcopy(resolved_inputs),
                        error_details=f"Instantiation error: {err}",
                    )
                    mark_remaining_skipped(idx + 1)
                    break

                # Step 6.4: Execute component setup()
                try:
                    instance.setup(copy.deepcopy(node.config))
                    initialized_instances.append((node_id, instance))
                except Exception as err:
                    overall_status = ExecutionStatus.FAILED
                    msg = f"setup() failed on node '{node_id}': {err}"
                    execution_errors.append(msg)
                    node_results[node_id] = NodeExecutionResult(
                        node_id=node_id,
                        component_name=comp_name,
                        status=ExecutionStatus.FAILED,
                        inputs=copy.deepcopy(resolved_inputs),
                        error_details=f"Setup error: {err}",
                    )
                    mark_remaining_skipped(idx + 1)
                    break

                # Step 6.5: Execute component run()
                exec_ctx = ExecutionContext(
                    pipeline_name=pipeline_name,
                    node_id=node_id,
                    component_name=comp_name,
                    metadata=copy.deepcopy(context) if context else {},
                )
                node_start = time.perf_counter()
                try:
                    raw_outputs = instance.run(
                        copy.deepcopy(resolved_inputs),
                        exec_ctx.to_dict(),
                    )
                    if not isinstance(raw_outputs, dict):
                        raise ContractValidationError(
                            f"Component '{comp_name}' run() must return a dict, "
                            f"got '{type(raw_outputs).__name__}'."
                        )
                    validate_outputs(raw_outputs, manifest.outputs)
                    node_duration = (time.perf_counter() - node_start) * 1000.0
                    all_outputs[node_id] = copy.deepcopy(raw_outputs)
                    node_results[node_id] = NodeExecutionResult(
                        node_id=node_id,
                        component_name=comp_name,
                        status=ExecutionStatus.SUCCEEDED,
                        inputs=copy.deepcopy(resolved_inputs),
                        outputs=copy.deepcopy(raw_outputs),
                        duration_ms=node_duration,
                    )
                except Exception as err:
                    node_duration = (time.perf_counter() - node_start) * 1000.0
                    overall_status = ExecutionStatus.FAILED
                    msg = f"run() failed on node '{node_id}': {err}"
                    execution_errors.append(msg)
                    node_results[node_id] = NodeExecutionResult(
                        node_id=node_id,
                        component_name=comp_name,
                        status=ExecutionStatus.FAILED,
                        inputs=copy.deepcopy(resolved_inputs),
                        duration_ms=node_duration,
                        error_details=f"Execution error: {err}",
                    )
                    mark_remaining_skipped(idx + 1)
                    break

        finally:
            # 7. Guaranteed teardown of all successfully initialized instances
            for inst_node_id, inst in reversed(initialized_instances):
                try:
                    inst.teardown()
                except Exception as err:
                    cleanup_errors.append(
                        f"Teardown error on node '{inst_node_id}': {err}"
                    )

        if cleanup_errors:
            overall_status = ExecutionStatus.FAILED

        total_duration = (time.perf_counter() - start_time) * 1000.0
        success = (
            overall_status == ExecutionStatus.SUCCEEDED
            and len(execution_errors) == 0
            and len(cleanup_errors) == 0
        )

        return PipelineExecutionResult(
            pipeline_name=pipeline_name,
            status=overall_status,
            success=success,
            duration_ms=total_duration,
            node_results=node_results,
            outputs=all_outputs,
            execution_errors=execution_errors,
            cleanup_errors=cleanup_errors,
        )
