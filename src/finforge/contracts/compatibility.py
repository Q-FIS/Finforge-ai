"""Static port compatibility verification for FinForge AI.

This module validates whether a source output port can legally connect to
a destination input port according to strict type rules and promotion hierarchies.
"""

from typing import Any

from pydantic import ValidationError

from finforge.exceptions import PortIncompatibleError
from finforge.manifest.models import SUPPORTED_PORT_TYPES, PortDefinition


def _coerce_port_def(port: PortDefinition | dict[str, Any]) -> PortDefinition:
    """Coerce port argument into a PortDefinition instance."""
    if isinstance(port, PortDefinition):
        return port
    if isinstance(port, dict):
        try:
            return PortDefinition.model_validate(port)
        except (ValidationError, ValueError) as err:
            raise PortIncompatibleError(f"Invalid port specification: {err}") from err
    raise PortIncompatibleError(
        f"Invalid port specification: expected PortDefinition or dict, "
        f"got {type(port).__name__}."
    )


def check_port_compatibility(
    source_port: PortDefinition | dict[str, Any],
    destination_port: PortDefinition | dict[str, Any],
    source_name: str | None = None,
    destination_name: str | None = None,
) -> None:
    """Statically verify if source output port can connect to destination input.

    Type Compatibility Rules:
      1. Supported Types: Both source and destination must be recognized port types.
      2. Universality: If destination is 'any', any source type is compatible.
      3. Exact Match: Matching types are compatible.
      4. Arrays: If both source and destination are 'array' and declare 'items',
         item specifications are checked recursively. Incompatible items fail.
      5. Promotion: 'integer' output is compatible with 'number' or 'float' input.
         However, 'number'/'float' output cannot be narrowed to 'integer'.
      6. Incompatibility: Incompatible primitive types are rejected.

    Args:
        source_port: Port definition for the producer output.
        destination_port: Port definition for the consumer input.
        source_name: Optional human-readable name of the source port.
        destination_name: Optional human-readable name of the destination port.

    Raises:
        PortIncompatibleError: If the ports cannot be connected safely.
    """
    src = _coerce_port_def(source_port)
    dst = _coerce_port_def(destination_port)

    src_label = f"'{source_name}' " if source_name else ""
    dst_label = f"'{destination_name}' " if destination_name else ""

    src_type = src.type.lower()
    dst_type = dst.type.lower()

    if src_type not in SUPPORTED_PORT_TYPES:
        raise PortIncompatibleError(
            f"Source port {src_label}has unsupported type '{src_type}'.",
            source_port=source_name,
            destination_port=destination_name,
            source_type=src_type,
            destination_type=dst_type,
        )

    if dst_type not in SUPPORTED_PORT_TYPES:
        raise PortIncompatibleError(
            f"Destination port {dst_label}has unsupported type '{dst_type}'.",
            source_port=source_name,
            destination_port=destination_name,
            source_type=src_type,
            destination_type=dst_type,
        )

    # 1. Any destination accepts any source
    if dst_type == "any":
        return

    # 2. Array item-type checking
    if src_type == "array" and dst_type == "array":
        if src.items is not None and dst.items is not None:
            try:
                check_port_compatibility(
                    src.items,
                    dst.items,
                    source_name=f"{source_name or 'source'}.items",
                    destination_name=f"{destination_name or 'destination'}.items",
                )
            except PortIncompatibleError as err:
                raise PortIncompatibleError(
                    f"Incompatible array item types between source {src_label}and "
                    f"destination {dst_label}: {err}",
                    source_port=source_name,
                    destination_port=destination_name,
                    source_type=src_type,
                    destination_type=dst_type,
                ) from err
        return

    # 3. Exact matching types
    if src_type == dst_type:
        return

    # 4. Numeric type promotion (integer -> number/float, float <-> number)
    if src_type == "integer" and dst_type in ("number", "float"):
        return

    if src_type in ("number", "float") and dst_type in ("number", "float"):
        return

    if src_type in ("number", "float") and dst_type == "integer":
        raise PortIncompatibleError(
            f"Cannot connect numeric source {src_label}(type '{src_type}') to integer "
            f"destination {dst_label}(type 'integer'): loss of precision.",
            source_port=source_name,
            destination_port=destination_name,
            source_type=src_type,
            destination_type=dst_type,
        )

    # 5. Incompatible types
    raise PortIncompatibleError(
        f"Incompatible port connection: source {src_label}(type '{src_type}') cannot "
        f"connect to destination {dst_label}(type '{dst_type}').",
        source_port=source_name,
        destination_port=destination_name,
        source_type=src_type,
        destination_type=dst_type,
    )


def is_port_compatible(
    source_port: PortDefinition | dict[str, Any],
    destination_port: PortDefinition | dict[str, Any],
) -> bool:
    """Return True if ports are compatible, False otherwise."""
    try:
        check_port_compatibility(source_port, destination_port)
        return True
    except PortIncompatibleError:
        return False
