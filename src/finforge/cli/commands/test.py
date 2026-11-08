"""Component testing command for the FinForge AI CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from finforge.testing import TestStatus, run_component_tests

console = Console()


def test_cmd(
    component_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the component project directory to test.",
            show_default=False,
        ),
    ] = Path("."),
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured test outcomes as machine-readable JSON.",
        ),
    ] = False,
    skip_developer_tests: Annotated[
        bool,
        typer.Option(
            "--skip-developer-tests",
            help="Skip running developer pytest tests.",
        ),
    ] = False,
) -> None:
    """Run architectural validation and developer tests on a component project."""
    target_dir = component_path.resolve()
    if not target_dir.is_dir():
        console.print(
            f"[bold red]Error:[/bold red] Component path '{target_dir}' "
            "is not a directory."
        )
        raise typer.Exit(code=1)

    result = run_component_tests(
        component_path=target_dir,
        run_developer_tests=not skip_developer_tests,
    )

    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        if not result.is_success:
            raise typer.Exit(code=1)
        return

    # Rich terminal display
    status_style = "green" if result.is_success else "red"
    console.print(
        f"\n[bold]Testing Component:[/bold] [cyan]{result.component_name}[/cyan] "
        f"(v{result.component_version or 'unknown'})\n"
    )

    table = Table(title="Framework Validation Stages", show_lines=True)
    table.add_column("Stage", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    def _fmt_status(st: TestStatus) -> str:
        if st == TestStatus.PASSED:
            return "[green]PASSED[/green]"
        if st == TestStatus.FAILED:
            return "[red]FAILED[/red]"
        if st == TestStatus.SKIPPED:
            return "[yellow]SKIPPED[/yellow]"
        return "[dim]NOT RUN[/dim]"

    table.add_row(
        "Manifest Schema",
        _fmt_status(result.manifest_validation.status),
        result.manifest_validation.message or "",
    )
    table.add_row(
        "Class Structure",
        _fmt_status(result.structure_validation.status),
        result.structure_validation.message or "",
    )
    table.add_row(
        "Contracts & Ports",
        _fmt_status(result.contract_validation.status),
        result.contract_validation.message or "",
    )
    table.add_row(
        "Lifecycle Execution",
        _fmt_status(result.lifecycle_test.status),
        result.lifecycle_test.message or "",
    )
    table.add_row(
        "Developer Tests",
        _fmt_status(result.developer_tests.status),
        result.developer_tests.message or "",
    )

    console.print(table)

    if result.all_errors:
        console.print("\n[bold red]Failures Encountered:[/bold red]")
        for err in result.all_errors:
            console.print(f"  [red]✗[/red] {err}")

    console.print(
        f"\n[bold {status_style}]Outcome:[/bold {status_style}] "
        f"{result.summary_message}\n"
    )

    if not result.is_success:
        raise typer.Exit(code=1)
