"""Component execution command for the FinForge AI CLI."""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from finforge.component import BaseComponent
from finforge.contracts import validate_inputs, validate_outputs
from finforge.exceptions import FinForgeError
from finforge.manifest import PortDefinition, load_manifest

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
            raise FileNotFoundError(
                f"{payload_name.capitalize()} file '{resolved_file}' does not exist."
            )
        content = resolved_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise ValueError(
                f"Content in '{resolved_file}' must be a JSON/YAML mapping/dict, "
                f"got {type(parsed).__name__}."
            )
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

    # Try parsing as key=value pairs (e.g. "param1=val1,param2=val2")
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
        "Expected JSON string, YAML, key=value pairs, or path to an existing file."
    )


def _synthesize_sample_value(port: PortDefinition) -> Any:
    """Generate a sensible sample value for a port based on its declared type."""
    port_type = port.type.lower()
    if port_type == "string":
        return "FinForge sample input"
    if port_type == "integer":
        return 1
    if port_type in ("number", "float"):
        return 1.0
    if port_type == "boolean":
        return True
    if port_type == "array":
        if port.items:
            item_val = _synthesize_sample_value(port.items)
            return [item_val, item_val]
        return [1.0, 2.0, 3.0]
    if port_type == "object":
        return {"sample_key": "sample_val"}
    if port_type in ("tensor", "dataframe", "binary"):
        return [[1.0, 2.0], [3.0, 4.0]]
    if port_type == "any":
        return "sample_data"
    return "sample"


def _synthesize_sample_inputs(inputs_def: dict[str, PortDefinition]) -> dict[str, Any]:
    """Generate default test inputs matching the component's declared input ports."""
    sample: dict[str, Any] = {}
    for port_name, port_def in inputs_def.items():
        sample[port_name] = _synthesize_sample_value(port_def)
    return sample


def run_component_cmd(
    component_path: Annotated[
        Path,
        typer.Argument(
            help="Path to component project directory (or component.yaml).",
            show_default=False,
        ),
    ] = Path("."),
    input_data: Annotated[
        str | None,
        typer.Option(
            "--input",
            "-i",
            help="Input data as JSON string, key=val pairs, or file path.",
        ),
    ] = None,
    input_file: Annotated[
        Path | None,
        typer.Option(
            "--input-file",
            help="Path to JSON or YAML file containing component inputs.",
        ),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            help="Component configuration as JSON string, key=val pairs, or file path.",
        ),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config-file",
            help="Path to JSON or YAML file containing component configuration.",
        ),
    ] = None,
    context: Annotated[
        str | None,
        typer.Option(
            "--context",
            help="Execution context metadata as JSON string.",
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output structured execution result as machine-readable JSON.",
        ),
    ] = False,
) -> None:
    """Execute a FinForge AI component standalone with inputs and configuration."""
    target = component_path.resolve()

    if target.is_file():
        manifest_file = target
        comp_dir = target.parent
    elif target.is_dir():
        comp_dir = target
        manifest_file = target / "component.yaml"
    else:
        console.print(
            f"[bold red]Error:[/bold red] Component path '{target}' does not exist."
        )
        raise typer.Exit(code=1)

    if not manifest_file.is_file():
        console.print(
            f"[bold red]Error:[/bold red] Component manifest 'component.yaml' "
            f"not found in '{comp_dir}'."
        )
        raise typer.Exit(code=1)

    try:
        manifest = load_manifest(manifest_file)
    except Exception as exc:
        console.print(
            f"[bold red]Error:[/bold red] Failed to load component manifest: {exc}"
        )
        raise typer.Exit(code=1) from exc

    if ":" not in manifest.entrypoint:
        console.print(
            f"[bold red]Error:[/bold red] Invalid entrypoint '{manifest.entrypoint}'. "
            "Expected format '<module>:<class>'."
        )
        raise typer.Exit(code=1)

    module_name, class_name = manifest.entrypoint.split(":", 1)
    src_dir = comp_dir / "src"
    candidate_path = src_dir if src_dir.is_dir() else comp_dir
    cand_str = str(candidate_path.resolve())
    if cand_str not in sys.path:
        sys.path.insert(0, cand_str)

    try:
        importlib.invalidate_caches()
        sys.modules.pop(module_name, None)
        sys.modules.pop(module_name.split(".")[0], None)
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
    except Exception as exc:
        console.print(
            f"[bold red]Error:[/bold red] "
            f"Failed to import entrypoint '{manifest.entrypoint}': {exc}"
        )
        raise typer.Exit(code=1) from exc

    if not isinstance(cls, type) or not issubclass(cls, BaseComponent):
        console.print(
            f"[bold red]Error:[/bold red] "
            f"Class '{class_name}' must inherit from BaseComponent."
        )
        raise typer.Exit(code=1)

    # 1. Resolve configuration
    resolved_config: dict[str, Any] = {}
    for cfg_name, cfg_def in manifest.config.items():
        if cfg_def.default is not None:
            resolved_config[cfg_name] = cfg_def.default

    try:
        if config or config_file:
            user_config = _parse_payload(config, config_file, "config")
            resolved_config.update(user_config)
    except Exception as exc:
        console.print(f"[bold red]Error parsing config:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 2. Resolve inputs
    try:
        if input_data or input_file:
            resolved_inputs = _parse_payload(input_data, input_file, "input")
        else:
            resolved_inputs = _synthesize_sample_inputs(manifest.inputs)
    except Exception as exc:
        console.print(f"[bold red]Error parsing inputs:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 3. Resolve context
    resolved_context: dict[str, Any] = {
        "execution_mode": "cli",
        "component": manifest.name,
    }
    try:
        if context:
            user_context = _parse_payload(context, None, "context")
            resolved_context.update(user_context)
    except Exception as exc:
        console.print(f"[bold red]Error parsing context:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 4. Execute component lifecycle
    instance = cls()
    duration_ms: float = 0.0
    try:
        instance.setup(resolved_config)
        validate_inputs(resolved_inputs, manifest.inputs)

        t0 = time.perf_counter()
        outputs = instance.run(resolved_inputs, resolved_context)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        if not isinstance(outputs, dict):
            raise TypeError(
                f"Component run() must return dict, got {type(outputs).__name__}."
            )

        validate_outputs(outputs, manifest.outputs)
    except (FinForgeError, Exception) as exc:
        if as_json:
            error_payload = {
                "status": "failed",
                "component": manifest.name,
                "version": manifest.version,
                "duration_ms": round(duration_ms, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            console.print(json.dumps(error_payload, indent=2))
        else:
            console.print(
                f"\n[bold red]Execution Failure:[/bold red] "
                f"Component '{manifest.name}' failed during run."
            )
            console.print(f"  [red]✗[/red] {type(exc).__name__}: {exc}\n")
        raise typer.Exit(code=1) from exc
    finally:
        with contextlib.suppress(Exception):
            instance.teardown()

    # 5. Output results
    if as_json:
        result_payload = {
            "status": "succeeded",
            "component": manifest.name,
            "version": manifest.version,
            "category": manifest.category,
            "duration_ms": round(duration_ms, 3),
            "config": resolved_config,
            "inputs": resolved_inputs,
            "outputs": outputs,
        }
        console.print(json.dumps(result_payload, indent=2, default=str))
        return

    # Rich formatting
    console.print(
        Panel(
            f"[bold]Component:[/bold] [cyan]{manifest.name}[/cyan]  "
            f"[dim](v{manifest.version or '0.1.0'})[/dim]\n"
            f"[bold]Category:[/bold]  [yellow]{manifest.category}[/yellow]\n"
            f"[bold]Entrypoint:[/bold] [dim]{manifest.entrypoint}[/dim]\n"
            f"[bold]Description:[/bold] {manifest.description or '[dim]None[/dim]'}",
            title="FinForge Component Execution",
            expand=False,
        )
    )

    if resolved_config:
        cfg_table = Table(title="Configuration", show_lines=False)
        cfg_table.add_column("Key", style="bold cyan")
        cfg_table.add_column("Value")
        for k, v in resolved_config.items():
            cfg_table.add_row(k, str(v))
        console.print(cfg_table)

    in_table = Table(title="Input Ports", show_lines=False)
    in_table.add_column("Port", style="bold green")
    in_table.add_column("Type", style="dim")
    in_table.add_column("Supplied Value")
    for port_name in manifest.inputs:
        val = resolved_inputs.get(port_name, "<missing>")
        is_composite = isinstance(val, (dict, list))
        val_str = json.dumps(val, default=str) if is_composite else str(val)
        if len(val_str) > 80:
            val_str = val_str[:77] + "..."
        in_table.add_row(port_name, manifest.inputs[port_name].type, val_str)
    console.print(in_table)

    out_table = Table(title="Output Ports Produced", show_lines=False)
    out_table.add_column("Port", style="bold magenta")
    out_table.add_column("Type", style="dim")
    out_table.add_column("Output Value")
    for port_name in manifest.outputs:
        val = outputs.get(port_name, "<missing>")
        is_composite = isinstance(val, (dict, list))
        val_str = json.dumps(val, default=str) if is_composite else str(val)
        if len(val_str) > 100:
            val_str = val_str[:97] + "..."
        out_table.add_row(port_name, manifest.outputs[port_name].type, val_str)
    console.print(out_table)

    console.print(
        f"\n[bold green]✓ Component Execution Succeeded[/bold green] "
        f"(Duration: [bold cyan]{duration_ms:.2f}ms[/bold cyan])\n"
    )
