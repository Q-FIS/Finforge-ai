"""Unit tests for the FinForge AI package metadata and entry points."""

import re

import finforge
from finforge.cli import app


def test_package_version_defined() -> None:
    """Verify that package version is defined and follows PEP 440 format."""
    assert hasattr(finforge, "__version__")
    assert isinstance(finforge.__version__, str)
    # Check PEP 440-compliant semantic / pre-release format (e.g. 0.1.0.dev0)
    version_pattern = r"^\d+\.\d+\.\d+(\.(dev|a|b|rc)\d+)?$"
    assert re.match(version_pattern, finforge.__version__) is not None


def test_cli_app_metadata() -> None:
    """Verify CLI application configuration."""
    assert app.info.name == "finforge"


def test_package_exports() -> None:
    """Verify that core component interface and exceptions are exported at top level."""
    expected_exports = [
        "BaseComponent",
        "ExampleComponent",
        "ComponentManifest",
        "PortDefinition",
        "ConfigDefinition",
        "load_manifest",
        "parse_manifest",
        "validate_inputs",
        "validate_outputs",
        "check_port_compatibility",
        "is_port_compatible",
        "FinForgeError",
        "ComponentError",
        "ComponentConfigurationError",
        "ComponentExecutionError",
        "ComponentLifecycleError",
        "ManifestError",
        "ManifestNotFoundError",
        "ManifestParseError",
        "ManifestValidationError",
        "ContractError",
        "ContractValidationError",
        "PortIncompatibleError",
        "RegistryError",
        "ComponentNotFoundError",
        "ComponentRegistrationError",
        "DuplicateComponentError",
        "ComponentRegistry",
        "RegistryEntry",
        "create_component_project",
        "normalize_component_name",
        "to_package_name",
        "to_class_name",
        "TemplateError",
        "TemplateNotFoundError",
        "TemplateRenderError",
        "ProjectGenerationError",
        "DestinationExistsError",
        "InvalidIdentifierError",
        "PathTraversalError",
        "TestingError",
        "ComponentValidationError",
        "TestExecutionError",
        "ComponentTestResult",
        "DeveloperTestSummary",
        "TestStatus",
        "ValidationStageResult",
        "run_component_tests",
        "PipelineError",
        "PipelineValidationError",
        "PipelineSerializationError",
        "PipelineDeserializationError",
        "SerializationFormatError",
        "GraphError",
        "NodeNotFoundError",
        "DuplicateNodeError",
        "PortNotFoundError",
        "InvalidEdgeError",
        "DuplicateEdgeError",
        "CycleDetectedError",
        "SelfLoopError",
        "GraphValidationError",
        "Pipeline",
        "PipelineDocument",
        "PipelineNode",
        "PipelineEdge",
        "PipelineGraph",
        "SerializedNode",
        "SerializedEdge",
        "save_pipeline",
        "load_pipeline",
        "load_pipeline_document",
        "serialize_pipeline_to_yaml",
        "deserialize_pipeline",
        "deserialize_pipeline_document",
        "PipelineExecutionError",
        "InputResolutionError",
        "NodeExecutionError",
        "CleanupError",
        "ExecutionContext",
        "ExecutionStatus",
        "NodeExecutionResult",
        "PipelineExecutionResult",
        "LocalSynchronousExecutor",
        "__version__",
    ]
    for symbol in expected_exports:
        assert hasattr(finforge, symbol)
        assert symbol in finforge.__all__
