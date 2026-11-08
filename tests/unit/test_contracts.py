"""Unit tests for input/output contract validation and static port compatibility."""

import copy

import pytest

from finforge.contracts import (
    check_port_compatibility,
    is_port_compatible,
    validate_inputs,
    validate_outputs,
)
from finforge.exceptions import ContractValidationError, PortIncompatibleError
from finforge.manifest import ComponentManifest, PortDefinition

# ==============================================================================
# 1. Runtime Input Validation Tests
# ==============================================================================


def test_valid_input_accepted() -> None:
    """1. Valid inputs matching the declared schema are accepted without error."""
    schema = {
        "text": PortDefinition(type="string", required=True),
        "count": PortDefinition(type="integer", required=True),
        "scores": PortDefinition(
            type="array", required=True, items=PortDefinition(type="number")
        ),
        "metadata": PortDefinition(type="object", required=False),
    }
    inputs = {
        "text": "hello",
        "count": 5,
        "scores": [1.0, 2.5, 3.14],
        "metadata": {"source": "api"},
    }
    # Should not raise
    validate_inputs(inputs, schema)


def test_missing_required_input_rejected() -> None:
    """2. Missing required inputs are rejected with ContractValidationError."""
    schema = {
        "data": PortDefinition(type="array", required=True),
        "optional_flag": PortDefinition(type="boolean", required=False),
    }
    inputs = {"optional_flag": True}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs(inputs, schema)
    assert "Missing required input 'data'" in str(excinfo.value)
    assert excinfo.value.field_name == "data"


def test_optional_input_can_be_omitted() -> None:
    """3. Optional inputs can be safely omitted from the input dictionary."""
    schema = {
        "required_field": PortDefinition(type="string", required=True),
        "optional_field": PortDefinition(type="integer", required=False),
    }
    inputs = {"required_field": "present"}
    validate_inputs(inputs, schema)


def test_unexpected_input_rejected() -> None:
    """4. Unexpected input keys not in schema are rejected by default."""
    schema = {"text": PortDefinition(type="string", required=True)}
    inputs = {"text": "hello", "unexpected_extra": 123}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs(inputs, schema)
    assert "Unexpected input key 'unexpected_extra'" in str(excinfo.value)
    assert excinfo.value.field_name == "unexpected_extra"


def test_incorrect_string_type_rejected() -> None:
    """5. Incorrect type for string port is rejected."""
    schema = {"name": PortDefinition(type="string", required=True)}
    inputs = {"name": 12345}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs(inputs, schema)
    assert "expected 'string', got 'integer'" in str(excinfo.value)


def test_incorrect_integer_type_rejected() -> None:
    """6. Incorrect type for integer port (e.g. float or string) is rejected."""
    schema = {"epochs": PortDefinition(type="integer", required=True)}
    inputs = {"epochs": 10.5}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs(inputs, schema)
    assert "expected 'integer', got 'number'" in str(excinfo.value)


def test_boolean_is_not_accepted_as_integer() -> None:
    """7. Boolean True/False must not be accepted as an integer."""
    schema = {"count": PortDefinition(type="integer", required=True)}
    with pytest.raises(ContractValidationError) as exc_true:
        validate_inputs({"count": True}, schema)
    assert "expected 'integer', got 'boolean'" in str(exc_true.value)

    with pytest.raises(ContractValidationError) as exc_false:
        validate_inputs({"count": False}, schema)
    assert "expected 'integer', got 'boolean'" in str(exc_false.value)


def test_number_accepts_integer_values() -> None:
    """8. Number/float port accepts both integers and floats, but rejects booleans."""
    schema = {"rate": PortDefinition(type="number", required=True)}

    # Accept float
    validate_inputs({"rate": 0.05}, schema)

    # Accept integer (widening promotion)
    validate_inputs({"rate": 2}, schema)

    # Reject boolean
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs({"rate": True}, schema)
    assert "expected 'number', got 'boolean'" in str(excinfo.value)


def test_array_accepts_valid_array_values() -> None:
    """9. Array port accepts valid lists or tuples, including empty lists."""
    schema = {"items": PortDefinition(type="array", required=True)}

    validate_inputs({"items": [1, 2, 3]}, schema)
    validate_inputs({"items": ("a", "b")}, schema)
    validate_inputs({"items": []}, schema)


def test_array_rejects_invalid_values() -> None:
    """10. Array port rejects non-array values (strings, numbers, objects)."""
    schema = {"items": PortDefinition(type="array", required=True)}

    for invalid in ["not a list", 123, {"key": "val"}, True]:
        with pytest.raises(ContractValidationError) as excinfo:
            validate_inputs({"items": invalid}, schema)
        assert "expected 'array'" in str(excinfo.value)


def test_nested_item_types_are_checked() -> None:
    """11. Nested array item types are verified against the items specification."""
    schema = {
        "matrix": PortDefinition(
            type="array",
            required=True,
            items=PortDefinition(type="number"),
        )
    }

    # All numbers: passes
    validate_inputs({"matrix": [1.0, 2.5, 3]}, schema)

    # Empty array with item type: passes
    validate_inputs({"matrix": []}, schema)

    # Array containing invalid item type: fails with exact index location
    with pytest.raises(ContractValidationError) as excinfo:
        validate_inputs({"matrix": [1.0, "bad_item", 3.0]}, schema)
    assert "matrix[1]" in str(excinfo.value)
    assert "expected 'number', got 'string'" in str(excinfo.value)


def test_original_input_data_is_not_mutated() -> None:
    """12. Original input dictionary and nested structures are not modified."""
    schema = {
        "text": PortDefinition(type="string", required=True),
        "scores": PortDefinition(
            type="array", required=True, items=PortDefinition(type="number")
        ),
        "opts": PortDefinition(type="object", required=False),
    }
    inputs = {
        "text": "original",
        "scores": [1.0, 2.0],
        "opts": {"nested": "value"},
    }
    cloned = copy.deepcopy(inputs)

    validate_inputs(inputs, schema)

    assert inputs == cloned
    assert inputs["scores"] is not cloned["scores"]  # separate object
    assert inputs["scores"] == cloned["scores"]


# ==============================================================================
# 2. Runtime Output Validation Tests
# ==============================================================================


def test_valid_output_accepted() -> None:
    """13. Valid outputs conforming to output schema pass validation."""
    schema = {
        "predictions": PortDefinition(type="array", required=True),
        "loss": PortDefinition(type="number", required=True),
    }
    outputs = {"predictions": [0, 1, 0], "loss": 0.042}
    validate_outputs(outputs, schema)


def test_missing_required_output_rejected() -> None:
    """14. Missing required output key is rejected with ContractValidationError."""
    schema = {
        "labels": PortDefinition(type="array", required=True),
        "score": PortDefinition(type="float", required=True),
    }
    outputs = {"labels": [1, 2, 3]}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_outputs(outputs, schema)
    assert "Missing required output 'score'" in str(excinfo.value)


def test_unexpected_output_rejected() -> None:
    """15. Unexpected output key not declared in schema is rejected."""
    schema = {"result": PortDefinition(type="string", required=True)}
    outputs = {"result": "done", "leaked_secret": "abc"}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_outputs(outputs, schema)
    assert "Unexpected output key 'leaked_secret'" in str(excinfo.value)


def test_incorrect_output_type_rejected() -> None:
    """16. Output value with incorrect type is rejected."""
    schema = {"active": PortDefinition(type="boolean", required=True)}
    outputs = {"active": "yes"}
    with pytest.raises(ContractValidationError) as excinfo:
        validate_outputs(outputs, schema)
    assert "expected 'boolean', got 'string'" in str(excinfo.value)


def test_original_output_data_is_not_mutated() -> None:
    """17. Original output dictionary and nested data are not modified."""
    schema = {
        "labels": PortDefinition(type="array", required=True),
        "meta": PortDefinition(type="object", required=True),
    }
    outputs = {"labels": [1, 2, 3], "meta": {"model": "kmeans"}}
    cloned = copy.deepcopy(outputs)

    validate_outputs(outputs, schema)

    assert outputs == cloned


# ==============================================================================
# 3. Static Port Compatibility Tests
# ==============================================================================


def test_exact_type_compatibility_accepted() -> None:
    """18. Exact matching types are compatible."""
    for p_type in ["string", "integer", "number", "boolean", "array", "object"]:
        src = PortDefinition(type=p_type)
        dst = PortDefinition(type=p_type)
        assert is_port_compatible(src, dst) is True
        check_port_compatibility(src, dst)


def test_integer_to_number_compatibility_accepted() -> None:
    """19. Integer output can legally connect to a number or float input."""
    src = PortDefinition(type="integer")
    dst_num = PortDefinition(type="number")
    dst_flt = PortDefinition(type="float")

    assert is_port_compatible(src, dst_num) is True
    check_port_compatibility(src, dst_num)

    assert is_port_compatible(src, dst_flt) is True
    check_port_compatibility(src, dst_flt)


def test_number_to_integer_compatibility_rejected() -> None:
    """20. Number or float output cannot be narrowed to integer."""
    src_num = PortDefinition(type="number")
    src_flt = PortDefinition(type="float")
    dst_int = PortDefinition(type="integer")

    assert is_port_compatible(src_num, dst_int) is False
    with pytest.raises(PortIncompatibleError) as exc_num:
        check_port_compatibility(src_num, dst_int)
    assert "loss of precision" in str(exc_num.value)

    assert is_port_compatible(src_flt, dst_int) is False
    with pytest.raises(PortIncompatibleError) as exc_flt:
        check_port_compatibility(src_flt, dst_int)
    assert "loss of precision" in str(exc_flt.value)


def test_string_to_array_compatibility_rejected() -> None:
    """21. Incompatible primitive types (e.g. string to array) are rejected."""
    src = PortDefinition(type="string")
    dst = PortDefinition(type="array")

    assert is_port_compatible(src, dst) is False
    with pytest.raises(PortIncompatibleError) as excinfo:
        check_port_compatibility(
            src, dst, source_name="text", destination_name="tokens"
        )
    assert "Incompatible port connection" in str(excinfo.value)
    assert "'text'" in str(excinfo.value)
    assert "'tokens'" in str(excinfo.value)


def test_array_item_type_incompatibility_rejected() -> None:
    """22. Array item types are checked and rejected when incompatible."""
    src_arr_str = PortDefinition(type="array", items=PortDefinition(type="string"))
    dst_arr_num = PortDefinition(type="array", items=PortDefinition(type="number"))
    dst_arr_int = PortDefinition(type="array", items=PortDefinition(type="integer"))
    src_arr_int = PortDefinition(type="array", items=PortDefinition(type="integer"))

    # string items -> number items: rejected
    assert is_port_compatible(src_arr_str, dst_arr_num) is False
    with pytest.raises(PortIncompatibleError) as excinfo:
        check_port_compatibility(src_arr_str, dst_arr_num)
    assert "Incompatible array item types" in str(excinfo.value)

    # integer items -> number items: accepted (promotion within items)
    assert is_port_compatible(src_arr_int, dst_arr_num) is True
    check_port_compatibility(src_arr_int, dst_arr_num)

    # number items -> integer items: rejected
    assert is_port_compatible(dst_arr_num, dst_arr_int) is False


def test_unknown_types_rejected() -> None:
    """23. Unknown port types are rejected as incompatible."""
    with pytest.raises(ValueError):
        PortDefinition(type="magic_crystal")  # rejected at model creation

    # Dict bypass test
    bad_dict = {"type": "magic_crystal"}
    good_dict = {"type": "string"}
    with pytest.raises(PortIncompatibleError) as excinfo:
        check_port_compatibility(bad_dict, good_dict)
    assert "unsupported port type" in str(excinfo.value).lower()


def test_compatibility_checking_does_not_execute_components() -> None:
    """24. Port compatibility checking operates strictly on schema metadata."""
    # Create fake port definitions that reference unimported/fictional entrypoints
    manifest_a = ComponentManifest(
        name="producer-component",
        version="1.0.0",
        description="Fictional producer",
        category="data-processing",
        entrypoint="fake_module_a.deep.path:FakeProducer",
        outputs={
            "embeddings": PortDefinition(
                type="array", items=PortDefinition(type="number")
            )
        },
    )
    manifest_b = ComponentManifest(
        name="consumer-component",
        version="1.0.0",
        description="Fictional consumer",
        category="machine-learning",
        entrypoint="fake_module_b.deep.path:FakeConsumer",
        inputs={
            "features": PortDefinition(
                type="array", items=PortDefinition(type="number")
            )
        },
    )

    # Compatible ports
    check_port_compatibility(
        manifest_a.outputs["embeddings"],
        manifest_b.inputs["features"],
        source_name="embeddings",
        destination_name="features",
    )
    assert (
        is_port_compatible(
            manifest_a.outputs["embeddings"], manifest_b.inputs["features"]
        )
        is True
    )


def test_validation_with_component_manifest_object() -> None:
    """Verify validate_inputs and validate_outputs accept ComponentManifest."""
    manifest = ComponentManifest(
        name="text-analyzer",
        version="0.1.0",
        description="Analyze text",
        category="llm",
        entrypoint="analyzer:TextAnalyzer",
        inputs={"prompt": PortDefinition(type="string", required=True)},
        outputs={
            "tokens": PortDefinition(type="integer", required=True),
            "summary": PortDefinition(type="string", required=False),
        },
    )

    # Inputs with manifest
    validate_inputs({"prompt": "Hello world"}, manifest)

    # Outputs with manifest (summary omitted since optional)
    validate_outputs({"tokens": 42}, manifest)
