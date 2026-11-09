"""Main Typer application entry point for the FinForge AI CLI."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer
from rich.console import Console

from finforge.cli.commands.create import create_cmd
from finforge.cli.commands.create_pipeline import create_pipeline_cmd
from finforge.cli.commands.export_pipeline import export_cmd
from finforge.cli.commands.inspect_pipeline import inspect_cmd
from finforge.cli.commands.run_component import run_component_cmd
from finforge.cli.commands.run_pipeline import run_pipeline_cmd
from finforge.cli.commands.test import test_cmd

console = Console()

app = typer.Typer(
    name="finforge",
    help="FinForge AI CLI: A scratch-first, modular, open-source AI framework.",
    add_completion=False,
    no_args_is_help=True,
)

# Run subcommand group: `finforge run component` and `finforge run pipeline`
run_app = typer.Typer(
    name="run",
    help="Execute FinForge AI components and pipelines.",
    add_completion=False,
    no_args_is_help=True,
)
run_app.command(name="component")(run_component_cmd)
run_app.command(name="pipeline")(run_pipeline_cmd)


def get_version() -> str:
    """Retrieve the installed package version dynamically."""
    try:
        return version("finforge-ai")
    except PackageNotFoundError:
        try:
            from finforge import __version__

            return __version__
        except Exception:
            return "0.1.0.dev0"


def version_callback(value: bool) -> None:
    """Display the FinForge AI framework version and exit."""
    if value:
        pkg_version = get_version()
        console.print(
            f"[bold cyan]FinForge AI[/bold cyan] version [green]{pkg_version}[/green]"
        )
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show FinForge AI version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """FinForge AI command-line interface entry point."""


# Register modular subcommands
app.command(name="create")(create_cmd)
app.command(name="create-pipeline")(create_pipeline_cmd)
app.command(name="export")(export_cmd)
app.command(name="inspect")(inspect_cmd)
app.add_typer(run_app, name="run")
app.command(name="run-component")(run_component_cmd)
app.command(name="run-pipeline")(run_pipeline_cmd)
app.command(name="test")(test_cmd)


if __name__ == "__main__":
    app()
