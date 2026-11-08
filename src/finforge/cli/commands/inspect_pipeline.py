"""Pipeline inspection command for the FinForge AI CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from finforge.exceptions import FinForgeError
from finforge.pipeline.serialization import (
    compute_document_execution_order,
    load_pipeline_document,
)

console = Console()


def inspect_cmd(
    pipeline_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the pipeline YAML file to inspect.",
            show_default=False,
        ),
    ],
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured pipeline inspection as machine-readable JSON.",
        ),
    ] = False,
) -> None:
    """Inspect and display the topology of a serialized FinForge AI pipeline."""
    target_file = pipeline_path.resolve()
    if not target_file.exists():
        console.print(
            f"[bold red]Error:[/bold red] Pipeline file '{target_file}' does not exist."
        )
        raise typer.Exit(code=1)

    if not target_file.is_file():
        console.print(
            f"[bold red]Error:[/bold red] Pipeline path '{target_file}' is not a file."
        )
        raise typer.Exit(code=1)

    try:
        doc = load_pipeline_document(target_file)
        topological_order = compute_document_execution_order(doc)
    except FinForgeError as exc:
        console.print(f"[bold red]Error:[/bold red] Failed to inspect pipeline: {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(
            f"[bold red]Error:[/bold red] Unexpected error reading pipeline: {exc}"
        )
        raise typer.Exit(code=1) from exc

    if as_json:
        summary_data = {
            "name": doc.name,
            "format_version": doc.format_version,
            "description": doc.description,
            "metadata": doc.metadata,
            "nodes": [
                {
                    "id": n.id,
                    "component": n.component,
                    "config": n.config,
                }
                for n in doc.nodes
            ],
            "connections": [
                {
                    "source": f"{e.source_node}.{e.source_port}",
                    "destination": f"{e.destination_node}.{e.destination_port}",
                }
                for e in doc.edges
            ],
            "topological_ordering": topological_order,
        }
        typer.echo(json.dumps(summary_data, indent=2))
        return

    # Rich formatted output
    console.print(
        Panel(
            f"[bold]Pipeline:[/bold] [cyan]{doc.name}[/cyan]  "
            f"[dim](Format v{doc.format_version})[/dim]\n"
            f"[bold]Description:[/bold] {doc.description or '[dim]None[/dim]'}",
            title="FinForge Pipeline Inspection",
            expand=False,
        )
    )

    # Nodes and Components Table
    nodes_table = Table(title="Nodes & Components", show_lines=True)
    nodes_table.add_column("Node ID", style="bold cyan")
    nodes_table.add_column("Component", style="green")
    nodes_table.add_column("Config Keys", style="yellow")

    for node in doc.nodes:
        config_summary = (
            ", ".join(node.config.keys()) if node.config else "[dim]empty[/dim]"
        )
        nodes_table.add_row(node.id, node.component, config_summary)

    console.print(nodes_table)

    # Connections Table
    edges_table = Table(title="Connections", show_lines=True)
    edges_table.add_column("Source", style="cyan")
    edges_table.add_column("Destination", style="magenta")

    if doc.edges:
        for edge in doc.edges:
            edges_table.add_row(
                f"{edge.source_node}.{edge.source_port}",
                f"{edge.destination_node}.{edge.destination_port}",
            )
    else:
        edges_table.add_row("[dim]None[/dim]", "[dim]None[/dim]")

    console.print(edges_table)

    # Topological Execution Order
    console.print("\n[bold]Topological Ordering:[/bold]")
    if topological_order:
        formatted_order = " -> ".join(
            f"[bold green]{nid}[/bold green]" for nid in topological_order
        )
        console.print(f"  {formatted_order}\n")
    else:
        console.print("  [dim]Empty pipeline (0 nodes)[/dim]\n")
