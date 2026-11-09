"""Pipeline creation command for the FinForge AI CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from finforge.exceptions import FinForgeError
from finforge.sdk.generator import create_pipeline_project

console = Console()


def create_pipeline_cmd(
    name: Annotated[
        str | None,
        typer.Argument(
            help="Name of the pipeline to create (e.g. 'fraud-detection').",
            show_default=False,
        ),
    ] = None,
    destination: Annotated[
        Path,
        typer.Option(
            "--destination",
            "-d",
            help="Directory where the pipeline folder will be created.",
            show_default=True,
        ),
    ] = Path("./pipelines"),
    description: Annotated[
        str | None,
        typer.Option(
            "--description",
            help="Human summary of pipeline workflow.",
        ),
    ] = None,
    components: Annotated[
        str | None,
        typer.Option(
            "--components",
            "-c",
            help=(
                "Comma-separated names of initial components to scaffold inside "
                "the pipeline's components/ directory."
            ),
        ),
    ] = None,
) -> None:
    """Create a new FinForge AI pipeline project with local components directory."""
    if not name or not name.strip():
        try:
            prompted_name = typer.prompt("Pipeline name")
            name = prompted_name.strip() if prompted_name else None
        except Exception:
            console.print("[bold red]Error:[/bold red] Pipeline name is required.")
            raise typer.Exit(code=1) from None

        if not name:
            console.print("[bold red]Error:[/bold red] Pipeline name is required.")
            raise typer.Exit(code=1)

    component_list: list[str] = []
    if components:
        component_list = [c.strip() for c in components.split(",") if c.strip()]

    try:
        project_path = create_pipeline_project(
            name=name,
            destination=destination,
            description=description,
            components=component_list,
        )
    except FinForgeError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from err
    except Exception as err:
        console.print(f"[bold red]Unexpected error:[/bold red] {err}")
        raise typer.Exit(code=1) from err

    console.print(
        f"[bold green]✓[/bold green] Created pipeline project "
        f"[bold cyan]{project_path.name}[/bold cyan] at [green]{project_path}[/green]"
    )
    comps_dir = project_path / "components"
    if component_list:
        console.print(
            f"  [bold]Local components created in:[/bold] [cyan]{comps_dir}[/cyan]"
        )
        for comp in component_list:
            console.print(f"    • [green]{comp}[/green]")
    else:
        console.print(
            f"  [bold]Local components directory:[/bold] [cyan]{comps_dir}[/cyan]"
        )

    pipeline_yaml = project_path / "pipeline.yaml"
    runner_script = project_path / "run_pipeline.py"
    console.print(f"\n[dim]To inspect:[/dim] finforge inspect {pipeline_yaml}")
    console.print(
        f"[dim]To add a component:[/dim] finforge create <name> -p {project_path}"
    )
    console.print(f"[dim]To run:[/dim] python {runner_script}")
