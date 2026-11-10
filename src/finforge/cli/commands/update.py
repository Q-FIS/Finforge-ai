"""Manifest update command for the FinForge AI CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from finforge.exceptions import FinForgeError
from finforge.sdk.updater import auto_update

console = Console()


def update_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help=(
                "Target path or type ('component' | 'pipeline'). "
                "Defaults to current directory."
            ),
            show_default=True,
        ),
    ] = ".",
    subtarget: Annotated[
        str | None,
        typer.Argument(
            help=(
                "Optional subtarget path when first argument is "
                "'component' or 'pipeline'."
            ),
            show_default=False,
        ),
    ] = None,
    component: Annotated[
        bool,
        typer.Option(
            "--component",
            "-c",
            help="Force updating target as a component.",
        ),
    ] = False,
    pipeline: Annotated[
        bool,
        typer.Option(
            "--pipeline",
            "-p",
            help="Force updating target as a pipeline.",
        ),
    ] = False,
    all_targets: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Recursively search and update all components and pipelines found.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Simulate updates and preview changes without modifying files.",
        ),
    ] = False,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Check if manifests match code; exit code 1 if diffs exist.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Display detailed field changes.",
        ),
    ] = False,
) -> None:
    """Automatically synchronize FinForge AI manifests with code."""
    # Handle `finforge update component <path>` and `finforge update pipeline <path>`
    effective_target = target
    force_component = component
    force_pipeline = pipeline

    lower_target = target.strip().lower()
    if lower_target in ("component", "components"):
        force_component = True
        effective_target = subtarget or "."
    elif lower_target in ("pipeline", "pipelines"):
        force_pipeline = True
        effective_target = subtarget or "."
    elif subtarget:
        effective_target = subtarget

    resolved_path = Path(effective_target).resolve()
    if not resolved_path.exists():
        console.print(
            f"[bold red]Error:[/bold red] Target path '{resolved_path}' does not exist."
        )
        raise typer.Exit(code=1)

    if dry_run:
        console.print(
            Panel(
                "[bold yellow]DRY RUN MODE[/bold yellow]: "
                "Previewing manifest changes without writing to disk.",
                border_style="yellow",
                expand=False,
            )
        )
    elif check:
        console.print(
            Panel(
                "[bold blue]CHECK MODE[/bold blue]: "
                "Verifying whether declarative manifests match code.",
                border_style="blue",
                expand=False,
            )
        )

    try:
        comp_results, pipe_results = auto_update(
            target_path=resolved_path,
            force_component=force_component,
            force_pipeline=force_pipeline,
            recursive=all_targets,
            dry_run=dry_run,
            check=check,
        )
    except FinForgeError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from err
    except Exception as err:
        console.print(f"[bold red]Unexpected error:[/bold red] {err}")
        raise typer.Exit(code=1) from err

    total_results = len(comp_results) + len(pipe_results)
    if total_results == 0:
        console.print(
            "[yellow]No FinForge AI components or pipelines found to update.[/yellow]"
        )
        return

    table = Table(title="FinForge AI Manifest Synchronization Summary", expand=False)
    table.add_column("Type", style="bold cyan")
    table.add_column("Name", style="bold", overflow="fold")
    table.add_column("Manifest File", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Modifications", style="green")

    has_errors = False
    has_diffs = False

    for cr in comp_results:
        rel_path = _rel_manifest_path(cr.manifest_path)
        if cr.error:
            has_errors = True
            table.add_row(
                "Component",
                cr.component_name,
                rel_path,
                "[bold red]Error[/bold red]",
                f"[red]{cr.error}[/red]",
            )
        elif cr.is_new:
            has_diffs = True
            change_desc = (
                "; ".join(c.summary() for c in cr.changes)
                or "+ Generated new manifest"
            )
            table.add_row(
                "Component",
                cr.component_name,
                rel_path,
                "[bold cyan]Created[/bold cyan]"
                if not dry_run and not check
                else "[cyan]New[/cyan]",
                change_desc,
            )
        elif cr.is_updated:
            has_diffs = True
            change_desc = (
                "; ".join(c.summary() for c in cr.changes)
                or "~ Updated to match code"
            )
            table.add_row(
                "Component",
                cr.component_name,
                rel_path,
                "[bold green]Updated[/bold green]"
                if not dry_run and not check
                else "[yellow]Out of Sync[/yellow]",
                change_desc,
            )
        else:
            table.add_row(
                "Component",
                cr.component_name,
                rel_path,
                "[dim green]Up-to-date[/dim green]",
                "[dim]Matches code[/dim]",
            )

    for pr in pipe_results:
        rel_path = _rel_manifest_path(pr.manifest_path)
        if pr.error:
            has_errors = True
            table.add_row(
                "Pipeline",
                pr.pipeline_name,
                rel_path,
                "[bold red]Error[/bold red]",
                f"[red]{pr.error}[/red]",
            )
        elif pr.is_new:
            has_diffs = True
            change_desc = (
                "; ".join(c.summary() for c in pr.changes)
                or "+ Generated new manifest"
            )
            table.add_row(
                "Pipeline",
                pr.pipeline_name,
                rel_path,
                "[bold cyan]Created[/bold cyan]"
                if not dry_run and not check
                else "[cyan]New[/cyan]",
                change_desc,
            )
        elif pr.is_updated:
            has_diffs = True
            change_desc = (
                "; ".join(c.summary() for c in pr.changes)
                or "~ Synchronized topology"
            )
            table.add_row(
                "Pipeline",
                pr.pipeline_name,
                rel_path,
                "[bold green]Updated[/bold green]"
                if not dry_run and not check
                else "[yellow]Out of Sync[/yellow]",
                change_desc,
            )
        else:
            table.add_row(
                "Pipeline",
                pr.pipeline_name,
                rel_path,
                "[dim green]Up-to-date[/dim green]",
                "[dim]Matches code[/dim]",
            )

    console.print(table)

    if has_errors:
        console.print(
            "\n[bold red]✖ Manifest synchronization encountered errors.[/bold red]"
        )
        raise typer.Exit(code=1)

    if check and has_diffs:
        console.print(
            "\n[bold red]✖ Manifest check failed:[/bold red] "
            "Declarative manifests are out of date with code."
        )
        console.print("Run [bold cyan]finforge update[/bold cyan] to synchronize them.")
        raise typer.Exit(code=1)

    if check:
        console.print(
            "\n[bold green]✓ All FinForge manifests match code perfectly.[/bold green]"
        )
        return

    if dry_run:
        console.print(
            "\n[bold yellow]Preview complete. No files were modified.[/bold yellow]"
        )
        return

    if has_diffs:
        console.print(
            "\n[bold green]✓ FinForge AI manifests successfully updated.[/bold green]"
        )
    else:
        console.print(
            "\n[bold green]✓ FinForge AI manifests are already up to date.[/bold green]"
        )


def update_component_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help="Path to component directory or component.yaml file.",
            show_default=True,
        ),
    ] = ".",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Simulate updates and preview changes without modifying files.",
        ),
    ] = False,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Check if manifest is up to date; exit code 1 if diffs exist.",
        ),
    ] = False,
) -> None:
    """Update component.yaml manifest according to component Python code."""
    update_cmd(target=target, component=True, dry_run=dry_run, check=check)


def update_pipeline_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help="Path to pipeline directory or pipeline.yaml file.",
            show_default=True,
        ),
    ] = ".",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Simulate updates and preview changes without modifying files.",
        ),
    ] = False,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Check if manifest is up to date; exit code 1 if diffs exist.",
        ),
    ] = False,
) -> None:
    """Update pipeline.yaml manifest according to code and components."""
    update_cmd(target=target, pipeline=True, dry_run=dry_run, check=check)


def _rel_manifest_path(path: Path) -> str:
    """Format path relative to current working directory if possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
