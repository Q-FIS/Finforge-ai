"""Demonstration of FinForge AI contract validation and port compatibility.

This example shows:
  1. Defining a preprocessing component's output contract.
  2. Defining a K-Means component's input contract.
  3. Verifying static compatibility between matching ports.
  4. Detecting and rejecting an incompatible connection.
  5. Validating runtime data against port schemas.
"""

from finforge.contracts import (
    check_port_compatibility,
    is_port_compatible,
    validate_inputs,
    validate_outputs,
)
from finforge.exceptions import ContractValidationError, PortIncompatibleError
from finforge.manifest import PortDefinition


def main() -> None:
    print("--- 1. Define Component Contracts ---")

    # Preprocessing component outputs
    preprocessor_outputs = {
        "features": PortDefinition(
            type="array",
            required=True,
            items=PortDefinition(type="number"),
            description="Normalized feature array.",
        ),
        "status_code": PortDefinition(
            type="string",
            required=False,
            description="Preprocessing status code.",
        ),
    }

    # K-Means clustering component inputs
    kmeans_inputs = {
        "data": PortDefinition(
            type="array",
            required=True,
            items=PortDefinition(type="number"),
            description="Input feature matrix for clustering.",
        ),
        "max_clusters": PortDefinition(
            type="integer",
            required=False,
            description="Cluster count ceiling.",
        ),
    }

    print("--- 2. Static Compatibility Validation ---")

    # Connect preprocessor['features'] -> kmeans['data']
    source_port = preprocessor_outputs["features"]
    target_port = kmeans_inputs["data"]

    compatible = is_port_compatible(source_port, target_port)
    print(f"Connection 'features' -> 'data' compatible? {compatible}")
    assert compatible is True
    check_port_compatibility(
        source_port, target_port, source_name="features", destination_name="data"
    )
    print("✓ Successful compatibility check verified.")

    # Try connecting preprocessor['status_code'] (string) -> kmeans['data'] (array)
    invalid_source = preprocessor_outputs["status_code"]
    is_compat = is_port_compatible(invalid_source, target_port)
    print(f"Connection 'status_code' -> 'data' compatible? {is_compat}")

    try:
        check_port_compatibility(
            invalid_source,
            target_port,
            source_name="status_code",
            destination_name="data",
        )
    except PortIncompatibleError as err:
        print(f"✓ Correctly rejected incompatible connection: {err}")

    print("\n--- 3. Runtime Data Validation ---")

    # Valid preprocessor output data
    valid_output_data = {
        "features": [0.12, 0.45, 0.98, 0.33],
        "status_code": "OK",
    }
    validate_outputs(valid_output_data, preprocessor_outputs)
    print("✓ Preprocessor outputs validated successfully.")

    # Valid K-Means input data
    valid_input_data = {
        "data": [0.12, 0.45, 0.98, 0.33],
        # max_clusters is optional, so omitted here
    }
    validate_inputs(valid_input_data, kmeans_inputs)
    print("✓ K-Means inputs validated successfully.")

    # Invalid K-Means input data (boolean passed as integer)
    invalid_input_data = {
        "data": [0.12, 0.45, 0.98, 0.33],
        "max_clusters": True,  # booleans must NOT be accepted as integers
    }
    try:
        validate_inputs(invalid_input_data, kmeans_inputs)
    except ContractValidationError as err:
        print(f"✓ Correctly caught invalid input type: {err}")


if __name__ == "__main__":
    main()
