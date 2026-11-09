"""Pipeline execution command for the FinForge AI CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from finforge.exceptions import FinForgeError
from finforge.pipeline.builder import Pipeline
from finforge.registry import ComponentRegistry
from finforge.runtime.models import ExecutionStatus, PipelineExecutionResult

console = Console()


def _parse_payload(
    value: str | None,
    file_path: Path | None = None,
    payload_name: str = "payload",
) -> dict[str, Any]:
    """Parse JSON/YAML string, key=value pairs, or file path into a dictionary."""
    if file_path is not None:
        resolved_file = file_path.resolve()
        if not resolved_file.is_file():
            raise FileNotFoundError(f"{payload_name.capitalize()} file '{resolved_file}' does not exist.")
        content = resolved_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"Content in '{resolved_file}' must be a JSON/YAML mapping/dict, got {type(parsed).__name__}.")
        return parsed

    if value is None or not value.strip():
        return {}

    trimmed = value.strip()

    # Check if value is a path to an existing file
    potential_path = Path(trimmed)
    if potential_path.is_file():
        content = potential_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        if isinstance(parsed, dict):
            return parsed

    # Try parsing as JSON
    try:
        parsed_json = json.loads(trimmed)
        if isinstance(parsed_json, dict):
            return parsed_json
    except json.JSONDecodeError:
        pass

    # Try parsing as YAML
    try:
        parsed_yaml = yaml.safe_load(trimmed)
        if isinstance(parsed_yaml, dict):
            return parsed_yaml
    except Exception:
        pass

    # Try parsing as key=value pairs (e.g. "node1.port1=val1")
    if "=" in trimmed:
        result: dict[str, Any] = {}
        tokens = [t.strip() for t in trimmed.split(",") if t.strip()]
        for token in tokens:
            if "=" in token:
                k, v = token.split("=", 1)
                k = k.strip()
                v = v.strip()
                try:
                    parsed_v = json.loads(v)
                except Exception:
                    parsed_v = v
                result[k] = parsed_v
        if result:
            return result

    raise ValueError(
        f"Could not parse {payload_name} '{trimmed}'. "
        "Expected JSON string, YAML, or path to an existing file."
    )


def _resolve_pipeline_file(pipeline_path: Path) -> Path:
    """Resolve target pipeline YAML file from path (file or directory)."""
    target = pipeline_path.resolve()
    if target.is_file():
        return target
    if target.is_dir():
        for candidate_name in ("pipeline.yaml", "pipeline.yml"):
            cand = target / candidate_name
            if cand.is_file():
                return cand
        raise FileNotFoundError(
            f"Pipeline definition ('pipeline.yaml' or 'pipeline.yml') not found in directory '{target}'."
        )
    raise FileNotFoundError(f"Pipeline path '{target}' does not exist.")


def _gather_search_paths(
    target_file: Path,
    extra_dirs: list[Path] | None = None,
) -> list[Path]:
    """Collect candidate directories to discover components for the pipeline."""
    candidates: list[Path] = []

    # 1. User specified directories
    if extra_dirs:
        for d in extra_dirs:
            p = d.resolve()
            if p.exists() and p not in candidates:
                candidates.append(p)

    # 2. Local components inside pipeline directory
    pipe_dir = target_file.parent
    local_comps = pipe_dir / "components"
    if local_comps.is_dir() and local_comps not in candidates:
        candidates.append(local_comps)

    if pipe_dir not in candidates:
        candidates.append(pipe_dir)

    # 3. Upward search for workspace components directory
    for parent in pipe_dir.parents:
        comp_sub = parent / "components"
        if comp_sub.is_dir() and comp_sub not in candidates:
            candidates.append(comp_sub)

    # 4. Current working directory components
    cwd_comps = Path.cwd().resolve() / "components"
    if cwd_comps.is_dir() and cwd_comps not in candidates:
        candidates.append(cwd_comps)

    if Path.cwd().resolve() not in candidates:
        candidates.append(Path.cwd().resolve())

    return candidates


def _auto_route_inputs(
    parsed_inputs: dict[str, Any],
    pipeline: Pipeline,
) -> dict[str, dict[str, Any]]:
    """Ensure inputs are keyed by node_id.
    
    If user provided {port: value} instead of {node_id: {port: value}},
    automatically route to entry node(s) matching port names.
    """
    if not parsed_inputs:
        return {}

    # Check if all keys already match node IDs in the pipeline graph
    graph = pipeline.graph
    all_keys_are_nodes = all(graph.has_node(k) for k in parsed_inputs.keys())
    if all_keys_are_nodes:
        # Verify sub-values are dicts
        for k, v in parsed_inputs.items():
            if not isinstance(v, dict):
                parsed_inputs[k] = {k: v}
        return parsed_inputs

    # If keys are ports, attempt routing to entry nodes
    nodes = graph.list_nodes()
    # Find entry nodes (nodes without incoming edges)
    entry_nodes: list[str] = []
    for n in nodes:
        upstream_edges = [
            e for e in graph.list_edges() if e.destination_node_id == n.node_id
        ]
        if not upstream_edges:
            entry_nodes.append(n.node_id)

    # Try mapping ports to entry nodes
    routed: dict[str, dict[str, Any]] = {}
    for node_id in entry_nodes:
        node = graph.get_node(node_id)
        manifest = graph.registry.get_manifest(node.component_name)
        node_ports = set(manifest.inputs.keys())
        matching_ports = {k: v for k, v in parsed_inputs.items() if k in node_ports}
        if matching_ports:
            routed[node_id] = matching_ports

    if routed:
        return routed

    # Fallback to passing as is
    return {k: v if isinstance(v, dict) else {k: v} for k, v in parsed_inputs.items()}


def run_pipeline_cmd(
    pipeline_path: Annotated[
        Path,
        typer.Argument(
            help="Path to pipeline YAML file or pipeline project directory.",
            show_default=False,
        ),
    ] = Path("."),
    inputs: Annotated[
        str | None,
        typer.Option(
            "--inputs",
            "-i",
            help="External inputs as JSON string, YAML, key=val pairs, or file path.",
        ),
    ] = None,
    inputs_file: Annotated[
        Path | None,
        typer.Option(
            "--inputs-file",
            help="Path to JSON or YAML file containing external pipeline inputs.",
        ),
    ] = None,
    context: Annotated[
        str | None,
        typer.Option(
            "--context",
            help="Execution context metadata as JSON string.",
        ),
    ] = None,
    components_dir: Annotated[
        list[Path] | None,
        typer.Option(
            "--components-dir",
            "-c",
            help="Additional directory to discover components from.",
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured pipeline execution result as machine-readable JSON.",
        ),
    ] = False,
) -> None:
    """Execute a serialized FinForge AI pipeline with topological runtime execution."""
    try:
        target_file = _resolve_pipeline_file(pipeline_path)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 1. Discover components
    registry = ComponentRegistry()
    search_paths = _gather_search_paths(target_file, extra_dirs=components_dir)
    discovered = registry.discover(search_paths=search_paths)

    # 2. Load and validate pipeline
    try:
        pipeline = Pipeline.load(target_file, registry=registry)
        pipeline.validate()
        order = pipeline.execution_order()
    except (FinForgeError, Exception) as exc:
        console.print(f"[bold red]Error loading pipeline:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 3. Parse inputs
    resolved_inputs: dict[str, dict[str, Any]] | None = None
    try:
        if inputs or inputs_file:
            raw_inputs = _parse_payload(inputs, inputs_file, "pipeline inputs")
            resolved_inputs = _auto_route_inputs(raw_inputs, pipeline)
    except Exception as exc:
        console.print(f"[bold red]Error parsing inputs:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 4. Parse context
    resolved_context: dict[str, Any] = {
        "execution_mode": "cli",
        "pipeline": pipeline.name,
    }
    try:
        if context:
            user_context = _parse_payload(context, None, "context")
            resolved_context.update(user_context)
    except Exception as exc:
        console.print(f"[bold red]Error parsing context:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 5. Execute pipeline
    try:
        result: PipelineExecutionResult = pipeline.run(
            inputs=resolved_inputs,
            context=resolved_context,
        )
    except (FinForgeError, Exception) as exc:
        if as_json:
            error_payload = {
                "status": "failed",
                "pipeline": pipeline.name,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            console.print(json.dumps(error_payload, indent=2))
        else:
            console.print(f"\n[bold red]Execution Failure:[/bold red] {exc}\n")
        raise typer.Exit(code=1) from exc

    # 6. Output formatting
    if as_json:
        console.print(result.model_dump_json(indent=2))
        if not result.success:
            raise typer.Exit(code=1)
        return

    # Rich formatting
    console.print(
        Panel(
            f"[bold]Pipeline:[/bold]        [cyan]{pipeline.name}[/cyan]\n"
            f"[bold]Description:[/bold]     {pipeline.description or '[dim]None[/dim]'}\n"
            f"[bold]Execution Order:[/bold] [bold]{' -> '.join(order)}[/bold]\n"
            f"[bold]Components:[/bold]      [green]{len(discovered)}[/green] discovered",
            title="FinForge Pipeline Execution",
            expand=False,
        )
    )

    # Node Telemetry Table
    table = Table(title="Pipeline Node Execution Telemetry", show_lines=True)
    table.add_column("Node ID", style="bold cyan")
    table.add_column("Component", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Duration (ms)", justify="right")
    table.add_column("Outputs Generated")

    for node_id in order:
        node_res = result.node_results.get(node_id)
        if not node_res:
            table.add_row(node_id, "-", "[dim]SKIPPED[/dim]", "0.00", "-")
            continue

        if node_res.status == ExecutionStatus.SUCCEEDED:
            status_str = "[green]SUCCEEDED[/green]"
        elif node_res.status == ExecutionStatus.FAILED:
            status_str = "[red]FAILED[/red]"
        elif node_res.status == ExecutionStatus.SKIPPED:
            status_str = "[yellow]SKIPPED[/yellow]"
        else:
            status_str = f"[dim]{node_res.status.value.upper()}[/dim]"

        dur_str = f"{node_res.duration_ms:.2f}"
        out_keys = list(node_res.outputs.keys())
        out_summary = ", ".join(out_keys) if out_keys else "[dim]None[/dim]"
        table.add_row(node_id, node_res.component_name, status_str, dur_str, out_summary)

    console.print(table)

    # Final Outputs Summary
    if result.outputs:
        out_panel_lines: list[str] = []
        for nid, nout in result.outputs.items():
            out_panel_lines.append(f"[bold cyan]{nid}:[/bold cyan]")
            for port, val in nout.items():
                val_repr = json.dumps(val, default=str) if isinstance(val, (dict, list)) else str(val)
                if len(val_repr) > 100:
                    val_repr = val_repr[:97] + "..."
                out_panel_lines.append(f"  • [magenta]{port}[/magenta]: {val_repr}")

        console.print(
            Panel(
                "\n".join(out_panel_lines),
                title="Final Pipeline Node Outputs",
                expand=False,
            )
        )

    # Errors if any
    if result.execution_errors:
        console.print("\n[bold red]Execution Errors:[/bold red]")
        for err in result.execution_errors:
            console.print(f"  [red]✗[/red] {err}")

    # Final Banner
    if result.success:
        console.print(
            f"\n[bold green]✓ Pipeline Execution Succeeded[/bold green] "
            f"(Total Duration: [bold cyan]{result.duration_ms:.2f}ms[/bold cyan])\n"
        )
    else:
        console.print(
            f"\n[bold red]✗ Pipeline Execution Failed[/bold red] "
            f"(Total Duration: [bold cyan]{result.duration_ms:.2f}ms[/bold cyan])\n"
        )
        raise typer.Exit(code=1)
