"""Component creation command for the FinForge AI CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from finforge.exceptions import FinForgeError
from finforge.sdk import create_component_project

console = Console()


def create_cmd(
    name: Annotated[
        str | None,
        typer.Argument(
            help="Name of the component to create (e.g. 'custom-kmeans').",
            show_default=False,
        ),
    ] = None,
    destination: Annotated[
        Path,
        typer.Option(
            "--destination",
            "-d",
            help="Directory where the component folder will be created.",
            show_default=True,
        ),
    ] = Path("./components"),
    description: Annotated[
        str | None,
        typer.Option(
            "--description",
            help="Human summary of component functionality.",
        ),
    ] = None,
    category: Annotated[
        str,
        typer.Option(
            "--category",
            "-c",
            help="AI/ML domain category (e.g. 'machine-learning', 'rag').",
            show_default=True,
        ),
    ] = "machine-learning",
    version: Annotated[
        str,
        typer.Option(
            "--version",
            help="Initial component package version.",
            show_default=True,
        ),
    ] = "0.1.0",
    author: Annotated[
        str | None,
        typer.Option(
            "--author",
            "-a",
            help="Author name or credit.",
        ),
    ] = None,
) -> None:
    """Create a new FinForge AI component project from the standard template."""
    if not name or not name.strip():
        try:
            prompted_name = typer.prompt("Component name")
            name = prompted_name.strip() if prompted_name else None
        except Exception:
            console.print("[bold red]Error:[/bold red] Component name is required.")
            raise typer.Exit(code=1) from None

        if not name:
            console.print("[bold red]Error:[/bold red] Component name is required.")
            raise typer.Exit(code=1)

    try:
        project_path = create_component_project(
            name=name,
            destination=destination,
            description=description,
            category=category,
            version=version,
            author=author,
        )
    except FinForgeError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from err
    except Exception as err:
        console.print(f"[bold red]Unexpected error:[/bold red] {err}")
        raise typer.Exit(code=1) from err

    console.print(
        f"[bold green]✓[/bold green] Created component "
        f"[bold cyan]{project_path.name}[/bold cyan] at [green]{project_path}[/green]"
    )
