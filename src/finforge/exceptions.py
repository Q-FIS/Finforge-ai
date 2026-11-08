"""Exception classes for FinForge AI.

This module defines a minimal, consistent exception hierarchy for component
lifecycle, configuration, execution, manifest parsing, contract validation,
and component registry operations.
"""


class FinForgeError(Exception):
    """Base exception for all FinForge AI framework errors."""


class ComponentError(FinForgeError):
    """Base exception for component-related failures."""


class ComponentConfigurationError(ComponentError):
    """Raised when component configuration is invalid or missing required parameters."""


class ComponentExecutionError(ComponentError):
    """Raised when a component encounters a failure during execution."""


class ComponentLifecycleError(ComponentError):
    """Raised when a component lifecycle method is invoked out of order or misused."""


class ManifestError(FinForgeError):
    """Base exception for all component manifest errors."""


class ManifestNotFoundError(ManifestError):
    """Raised when a component.yaml manifest file cannot be found."""


class ManifestParseError(ManifestError):
    """Raised when a manifest file contains malformed YAML or invalid structure."""


class ManifestValidationError(ManifestError):
    """Raised when manifest data violates schema validation rules."""


class ContractError(FinForgeError):
    """Base exception for all contract and schema validation errors."""


class ContractValidationError(ContractError):
    """Raised when runtime inputs or outputs violate contract specifications."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        expected_type: str | None = None,
        actual_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_type = actual_type


class PortIncompatibleError(ContractError):
    """Raised when component ports are statically incompatible."""

    def __init__(
        self,
        message: str,
        source_port: str | None = None,
        destination_port: str | None = None,
        source_type: str | None = None,
        destination_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source_port = source_port
        self.destination_port = destination_port
        self.source_type = source_type
        self.destination_type = destination_type


class RegistryError(FinForgeError):
    """Base exception for all component registry errors."""


class ComponentNotFoundError(RegistryError):
    """Raised when a requested component cannot be found in the registry."""


class ComponentRegistrationError(RegistryError):
    """Raised when a component cannot be registered due to validation failure."""


class DuplicateComponentError(ComponentRegistrationError):
    """Raised when registering a component under a name that already exists."""


class TemplateError(FinForgeError):
    """Base exception for all template loading and rendering errors."""


class TemplateNotFoundError(TemplateError):
    """Raised when a template file or directory cannot be found."""


class TemplateRenderError(TemplateError):
    """Raised when template variable substitution fails."""


class ProjectGenerationError(FinForgeError):
    """Base exception for project scaffolding and file generation errors."""


class DestinationExistsError(ProjectGenerationError):
    """Raised when the target destination directory already exists."""


class InvalidIdentifierError(ProjectGenerationError):
    """Raised when an identifier (name, package, or class) is invalid."""


class PathTraversalError(ProjectGenerationError):
    """Raised when a path escapes the allowed destination boundary."""


class TestingError(FinForgeError):
    """Base exception for component testing engine errors."""


class ComponentValidationError(TestingError):
    """Raised when component structure or contract verification fails."""


class TestExecutionError(TestingError):
    """Raised when test execution fails or encounters runner errors."""


class PipelineError(FinForgeError):
    """Base exception for all pipeline and graph errors."""


class PipelineValidationError(PipelineError):
    """Raised when pipeline-level configuration or initialization fails."""


class PipelineExecutionError(PipelineError):
    """Base exception for runtime execution failures in pipelines."""


class InputResolutionError(PipelineExecutionError):
    """Raised when input ports cannot be resolved or are invalid."""


class NodeExecutionError(PipelineExecutionError):
    """Raised when a specific component node encounters a runtime execution failure."""


class CleanupError(PipelineExecutionError):
    """Raised when one or more component instances fail during teardown."""


class GraphError(PipelineError):
    """Base exception for pipeline graph errors."""


class NodeNotFoundError(GraphError):
    """Raised when a referenced node ID is not found in the graph."""


class DuplicateNodeError(GraphError):
    """Raised when adding a node with an existing node ID."""


class PortNotFoundError(GraphError):
    """Raised when a referenced port is not found in a component manifest."""


class InvalidEdgeError(GraphError):
    """Raised when an edge specification is invalid."""


class DuplicateEdgeError(InvalidEdgeError):
    """Raised when adding an edge that already exists in the graph."""


class CycleDetectedError(GraphError):
    """Raised when a cycle or self-loop is detected in the graph."""


class SelfLoopError(CycleDetectedError, InvalidEdgeError):
    """Raised when an edge attempts to connect a node to itself."""


class GraphValidationError(GraphError):
    """Raised when graph structural validation fails."""


class PipelineSerializationError(PipelineError):
    """Base exception for pipeline serialization and saving errors."""


class PipelineDeserializationError(PipelineSerializationError):
    """Raised when deserializing or loading a pipeline definition fails."""


class SerializationFormatError(PipelineDeserializationError):
    """Raised when pipeline YAML format is invalid, unsupported, or malformed."""
