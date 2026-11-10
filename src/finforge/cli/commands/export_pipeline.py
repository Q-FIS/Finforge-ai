"""Pipeline visualization export command for the FinForge AI CLI."""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from finforge.exceptions import FinForgeError
from finforge.pipeline.serialization import (
    PipelineDocument,
    compute_document_execution_order,
    load_pipeline_document,
)

console = Console()


class ExportFormat(enum.StrEnum):
    """Supported visual export formats."""

    MERMAID = "mermaid"
    DOT = "dot"
    MARKDOWN = "markdown"
    JSON = "json"


def generate_mermaid(
    doc: PipelineDocument,
    direction: str = "LR",
) -> str:
    """Generate a Mermaid flowchart diagram for a pipeline document."""
    lines: list[str] = [f"flowchart {direction}"]

    # Declare nodes
    for node in doc.nodes:
        # Quote node labels to ensure valid Mermaid syntax
        label = f"{node.id} ({node.component})"
        lines.append(f'    {node.id}["{label}"]')

    # Declare edges
    if doc.edges:
        lines.append("")
        for edge in doc.edges:
            port_label = f"{edge.source_port} -> {edge.destination_port}"
            lines.append(
                f'    {edge.source_node} -->|"{port_label}"| {edge.destination_node}'
            )

    return "\n".join(lines)


def generate_dot(
    doc: PipelineDocument,
    direction: str = "LR",
) -> str:
    """Generate Graphviz DOT digraph markup for a pipeline document."""
    rankdir = "LR" if direction.upper() == "LR" else "TB"
    lines: list[str] = [
        f'digraph "{doc.name}" {{',
        f"  rankdir={rankdir};",
        '  graph [fontname="Helvetica", bgcolor="transparent"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#e0e7ff", '
        'color="#4338ca", fontname="Helvetica", fontsize=11, margin="0.2,0.1"];',
        '  edge [color="#64748b", fontname="Helvetica", fontsize=9, '
        'fontcolor="#475569"];',
        "",
    ]

    for node in doc.nodes:
        label = f"{node.id}\\n[{node.component}]"
        lines.append(f'  "{node.id}" [label="{label}"];')

    if doc.edges:
        lines.append("")
        for edge in doc.edges:
            port_label = f"{edge.source_port} -> {edge.destination_port}"
            lines.append(
                f'  "{edge.source_node}" -> "{edge.destination_node}" '
                f'[label="{port_label}"];'
            )

    lines.append("}")
    return "\n".join(lines)


def generate_markdown(
    doc: PipelineDocument,
    direction: str = "LR",
) -> str:
    """Generate a Markdown document embedding the Mermaid diagram and node details."""
    mermaid_block = generate_mermaid(doc, direction=direction)
    lines: list[str] = [
        f"# Pipeline: {doc.name}",
        "",
    ]
    if doc.description:
        lines.extend([f"> {doc.description}", ""])

    lines.extend([
        "## Topology Diagram",
        "",
        "```mermaid",
        mermaid_block,
        "```",
        "",
        "## Nodes & Components",
        "",
        "| Node ID | Component | Config Keys |",
        "| :--- | :--- | :--- |",
    ])

    for node in doc.nodes:
        cfg = ", ".join(f"`{k}`" for k in node.config) if node.config else "*None*"
        lines.append(f"| `{node.id}` | `{node.component}` | {cfg} |")

    if doc.edges:
        lines.extend([
            "",
            "## Port Connections",
            "",
            "| Source | Destination |",
            "| :--- | :--- |",
        ])
        for edge in doc.edges:
            src_str = f"{edge.source_node}.{edge.source_port}"
            dst_str = f"{edge.destination_node}.{edge.destination_port}"
            lines.append(f"| `{src_str}` | `{dst_str}` |")

    return "\n".join(lines)


def export_cmd(
    pipeline_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the pipeline YAML file to export.",
            show_default=False,
        ),
    ],
    export_format: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            "-f",
            help="Visual export format (mermaid, dot, markdown, json).",
        ),
    ] = ExportFormat.MERMAID,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path. If omitted, prints directly to stdout.",
        ),
    ] = None,
    direction: Annotated[
        str,
        typer.Option(
            "--direction",
            "-d",
            help="Flowchart layout orientation ('LR' left-to-right, 'TD' top-down).",
        ),
    ] = "LR",
) -> None:
    """Export pipeline DAG topology to visual formats (Mermaid, DOT, Markdown)."""
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

    normalized_dir = direction.upper()
    if normalized_dir not in ("LR", "TD", "TB", "RL"):
        normalized_dir = "LR"

    try:
        doc = load_pipeline_document(target_file)
        # Validate topological consistency
        compute_document_execution_order(doc)
    except FinForgeError as exc:
        console.print(f"[bold red]Error:[/bold red] Failed to export pipeline: {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(
            f"[bold red]Error:[/bold red] Unexpected error reading pipeline: {exc}"
        )
        raise typer.Exit(code=1) from exc

    # Generate markup according to format
    if export_format == ExportFormat.MERMAID:
        rendered = generate_mermaid(doc, direction=normalized_dir)
    elif export_format == ExportFormat.DOT:
        rendered = generate_dot(doc, direction=normalized_dir)
    elif export_format == ExportFormat.MARKDOWN:
        rendered = generate_markdown(doc, direction=normalized_dir)
    elif export_format == ExportFormat.JSON:
        import json

        data = {
            "name": doc.name,
            "description": doc.description,
            "direction": normalized_dir,
            "nodes": [
                {"id": n.id, "component": n.component, "config": n.config}
                for n in doc.nodes
            ],
            "edges": [
                {
                    "source_node": e.source_node,
                    "source_port": e.source_port,
                    "destination_node": e.destination_node,
                    "destination_port": e.destination_port,
                }
                for e in doc.edges
            ],
        }
        rendered = json.dumps(data, indent=2)
    else:
        rendered = generate_mermaid(doc, direction=normalized_dir)

    if output is not None:
        out_file = output.resolve()
        try:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(rendered + "\n", encoding="utf-8")
            console.print(
                f"[green]✓[/green] Successfully exported pipeline to "
                f"[cyan]'{out_file}'[/cyan] "
                f"(format: [bold]{export_format.value}[/bold])."
            )
        except OSError as err:
            console.print(
                f"[bold red]Error:[/bold red] "
                f"Failed writing to output file '{out_file}': {err}"
            )
            raise typer.Exit(code=1) from err
    else:
        # Print directly to stdout
        typer.echo(rendered)
