"""Runtime input and output contract validation engine for FinForge AI.

This module provides validation of runtime dictionaries against component schemas
defined by `PortDefinition` specifications.
"""

from typing import Any

from finforge.exceptions import ContractValidationError
from finforge.manifest.models import ComponentManifest, PortDefinition


def _get_type_name(val: Any) -> str:
    """Return a readable type name for a value."""
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, int):
        return "integer"
    if isinstance(val, float):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, (list, tuple)):
        return "array"
    if isinstance(val, dict):
        return "object"
    return type(val).__name__


def _check_type(val: Any, port: PortDefinition, field_path: str) -> None:
    """Validate that a single value adheres to the port definition type rules."""
    target_type = port.type.lower()

    if target_type == "any":
        return

    if target_type == "string":
        if not isinstance(val, str):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'string', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="string",
                actual_type=actual,
            )
        return

    if target_type == "integer":
        if isinstance(val, bool) or not isinstance(val, int):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'integer', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="integer",
                actual_type=actual,
            )
        return

    if target_type in ("number", "float"):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected '{target_type}', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type=target_type,
                actual_type=actual,
            )
        return

    if target_type == "boolean":
        if not isinstance(val, bool):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'boolean', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="boolean",
                actual_type=actual,
            )
        return

    if target_type == "array":
        is_array = isinstance(val, (list, tuple)) or (
            hasattr(val, "__len__")
            and hasattr(val, "__iter__")
            and not isinstance(val, (str, bytes, bytearray, dict))
        )
        if not is_array:
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'array', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="array",
                actual_type=actual,
            )

        if port.items is not None:
            for idx, item in enumerate(val):
                _check_type(item, port.items, f"{field_path}[{idx}]")
        return

    if target_type == "object":
        if not isinstance(val, dict):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'object', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="object",
                actual_type=actual,
            )
        return

    if target_type == "binary":
        if not isinstance(val, (bytes, bytearray, memoryview)):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'binary', "
                f"got '{actual}' (value: {val!r}).",
                field_name=field_path,
                expected_type="binary",
                actual_type=actual,
            )
        return

    if target_type == "tensor":
        if not (hasattr(val, "shape") or isinstance(val, (list, tuple))):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'tensor', got '{actual}'.",
                field_name=field_path,
                expected_type="tensor",
                actual_type=actual,
            )
        return

    if target_type == "dataframe":
        if not (hasattr(val, "columns") or isinstance(val, (list, dict))):
            actual = _get_type_name(val)
            raise ContractValidationError(
                f"Invalid type for '{field_path}': expected 'dataframe', "
                f"got '{actual}'.",
                field_name=field_path,
                expected_type="dataframe",
                actual_type=actual,
            )
        return

    actual = _get_type_name(val)
    raise ContractValidationError(
        f"Unsupported schema port type '{target_type}' on '{field_path}'.",
        field_name=field_path,
        expected_type=target_type,
        actual_type=actual,
    )


def _resolve_schema(
    schema: dict[str, PortDefinition] | ComponentManifest,
    direction: str,
) -> dict[str, PortDefinition]:
    """Extract port definitions dictionary from schema or manifest."""
    if isinstance(schema, ComponentManifest):
        return schema.inputs if direction == "input" else schema.outputs

    if not isinstance(schema, dict):
        raise ContractValidationError(
            f"Schema must be a dictionary of PortDefinitions or a ComponentManifest, "
            f"got {type(schema).__name__}."
        )

    resolved: dict[str, PortDefinition] = {}
    for key, value in schema.items():
        if isinstance(value, PortDefinition):
            resolved[key] = value
        elif isinstance(value, dict):
            resolved[key] = PortDefinition.model_validate(value)
        else:
            raise ContractValidationError(
                f"Port '{key}' definition must be a PortDefinition or dict, "
                f"got {type(value).__name__}."
            )
    return resolved


def _validate_data(
    data: dict[str, Any],
    schema: dict[str, PortDefinition] | ComponentManifest,
    direction: str,
    allow_extra: bool = False,
) -> None:
    """Validate a runtime data dictionary against a port schema."""
    if not isinstance(data, dict):
        raise ContractValidationError(
            f"Expected {direction} data to be a dictionary, got {type(data).__name__}."
        )

    port_schema = _resolve_schema(schema, direction)

    # 1. Verify required ports are present
    for port_name, port_def in port_schema.items():
        if port_def.required and port_name not in data:
            raise ContractValidationError(
                f"Missing required {direction} '{port_name}'. "
                f"Expected type: '{port_def.type}'.",
                field_name=port_name,
                expected_type=port_def.type,
                actual_type=None,
            )

    # 2. Verify unexpected keys are rejected
    if not allow_extra:
        for key in data:
            if key not in port_schema:
                val = data[key]
                actual = _get_type_name(val)
                raise ContractValidationError(
                    f"Unexpected {direction} key '{key}' not declared in schema.",
                    field_name=key,
                    expected_type=None,
                    actual_type=actual,
                )

    # 3. Verify types of provided values
    for port_name, port_def in port_schema.items():
        if port_name in data:
            val = data[port_name]
            _check_type(val, port_def, port_name)


def validate_inputs(
    inputs: dict[str, Any],
    schema: dict[str, PortDefinition] | ComponentManifest,
    allow_extra: bool = False,
) -> None:
    """Validate component runtime inputs against declared input contract schema.

    Args:
        inputs: Input dictionary passed to component.run().
        schema: Mapping of port names to PortDefinition or a ComponentManifest.
        allow_extra: If True, allow keys not specified in schema. Defaults to False.

    Raises:
        ContractValidationError: If required inputs are missing, unexpected inputs
            are present, or data types do not conform to the schema.
    """
    _validate_data(inputs, schema, direction="input", allow_extra=allow_extra)


def validate_outputs(
    outputs: dict[str, Any],
    schema: dict[str, PortDefinition] | ComponentManifest,
    allow_extra: bool = False,
) -> None:
    """Validate component runtime outputs against declared output contract schema.

    Args:
        outputs: Output dictionary emitted by component.run().
        schema: Mapping of port names to PortDefinition or a ComponentManifest.
        allow_extra: If True, allow keys not specified in schema. Defaults to False.

    Raises:
        ContractValidationError: If required outputs are missing, unexpected outputs
            are present, or data types do not conform to the schema.
    """
    _validate_data(outputs, schema, direction="output", allow_extra=allow_extra)
