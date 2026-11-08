"""Pydantic v2 data models and validation rules for component manifests.

This module defines typed schemas for component.yaml files, ensuring
strict verification of metadata, I/O ports, configuration options, and dependencies.
"""

from __future__ import annotations

import re
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_API_VERSIONS: frozenset[str] = frozenset({"1", "1.0"})

SUPPORTED_CATEGORIES: frozenset[str] = frozenset(
    {
        "machine-learning",
        "classical-ml",
        "deep-learning",
        "llm",
        "rag",
        "agentic",
        "agents",
        "multimodal",
        "data-processing",
        "evaluation",
    }
)

SUPPORTED_PORT_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "integer",
        "number",
        "float",
        "boolean",
        "array",
        "object",
        "any",
        "binary",
        "tensor",
        "dataframe",
    }
)

SUPPORTED_CONFIG_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "integer",
        "float",
        "boolean",
        "list",
        "array",
        "dict",
        "object",
        "any",
    }
)

_COMPONENT_NAME_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


class PortDefinition(BaseModel):
    """Schema for an input or output port of a component."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(description="Data type accepted or emitted by this port.")
    required: bool = Field(
        default=True,
        description="Whether this port must be provided during execution.",
    )
    description: str | None = Field(
        default=None,
        description="Optional human-readable description of the port.",
    )
    items: PortDefinition | None = Field(
        default=None,
        description="Optional item type definition for array ports.",
    )

    @field_validator("type")
    @classmethod
    def validate_port_type(cls, value: str) -> str:
        """Ensure port type is supported."""
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PORT_TYPES:
            valid_list = ", ".join(sorted(SUPPORTED_PORT_TYPES))
            raise ValueError(
                f"Unsupported port type '{value}'. Supported types are: {valid_list}."
            )
        return normalized

    @model_validator(mode="after")
    def validate_items_only_on_array(self) -> PortDefinition:
        """Ensure 'items' metadata is only declared on array ports."""
        if self.items is not None and self.type != "array":
            msg = (
                f"The 'items' specification is only supported for ports of "
                f"type 'array', not '{self.type}'."
            )
            raise ValueError(msg)
        return self


class ConfigDefinition(BaseModel):
    """Schema for a configuration parameter of a component."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        description="Data type expected for this configuration parameter."
    )
    required: bool = Field(
        default=False,
        description="Whether this configuration parameter is mandatory.",
    )
    default: Any = Field(
        default=None,
        description="Default value used if parameter is not supplied.",
    )
    description: str | None = Field(
        default=None,
        description="Optional human-readable description of the parameter.",
    )

    @field_validator("type")
    @classmethod
    def validate_config_type(cls, value: str) -> str:
        """Ensure configuration type is supported."""
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_CONFIG_TYPES:
            valid_list = ", ".join(sorted(SUPPORTED_CONFIG_TYPES))
            raise ValueError(
                f"Unsupported config type '{value}'. Supported types are: {valid_list}."
            )
        return normalized

    @model_validator(mode="after")
    def validate_default_matches_type(self) -> ConfigDefinition:
        """Verify that default value is compatible with the declared config type."""
        if self.default is None:
            return self

        cfg_type = self.type
        val = self.default

        if cfg_type == "integer" and (
            isinstance(val, bool) or not isinstance(val, int)
        ):
            raise ValueError(
                f"Default value '{val}' is not an integer for config type 'integer'."
            )
        if cfg_type == "float" and (
            isinstance(val, bool) or not isinstance(val, (int, float))
        ):
            raise ValueError(
                f"Default value '{val}' is not a float for config type 'float'."
            )
        if cfg_type == "boolean" and not isinstance(val, bool):
            raise ValueError(
                f"Default value '{val}' is not a boolean for config type 'boolean'."
            )
        if cfg_type == "string" and not isinstance(val, str):
            raise ValueError(
                f"Default value '{val}' is not a string for config type 'string'."
            )
        if cfg_type in ("list", "array") and not isinstance(val, list):
            raise ValueError(
                f"Default value '{val}' is not a list for config type '{cfg_type}'."
            )
        if cfg_type in ("dict", "object") and not isinstance(val, dict):
            raise ValueError(
                f"Default value '{val}' is not a dict for config type '{cfg_type}'."
            )

        return self


class ComponentManifest(BaseModel):
    """Declarative specification for a FinForge AI component."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique, slug-like name of the component.")
    version: str = Field(description="PEP 440 / SemVer compliant version string.")
    description: str = Field(description="Human summary of component function.")
    api_version: str = Field(
        default="1",
        description="Manifest schema specification version.",
    )
    category: str = Field(description="Target AI/ML discipline.")
    entrypoint: str = Field(
        description="Import path to component class in '<module>:<class>' format."
    )
    inputs: dict[str, PortDefinition] = Field(
        default_factory=dict,
        description="Input ports consumed by the component.",
    )
    outputs: dict[str, PortDefinition] = Field(
        default_factory=dict,
        description="Output ports produced by the component.",
    )
    config: dict[str, ConfigDefinition] = Field(
        default_factory=dict,
        description="Configuration parameters accepted in setup().",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="PEP 508 dependency specifiers required by this component.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate component name format (lowercase alphanumeric with dashes)."""
        trimmed = value.strip()
        if not trimmed or not _COMPONENT_NAME_REGEX.match(trimmed):
            raise ValueError(
                f"Invalid component name '{value}'. Must be non-empty, lowercase "
                "alphanumeric, and can contain single hyphens or underscores."
            )
        return trimmed

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        """Validate version string against PEP 440 standards using packaging."""
        trimmed = str(value).strip()
        if not trimmed:
            raise ValueError("Version string cannot be empty.")
        try:
            Version(trimmed)
        except InvalidVersion as err:
            raise ValueError(
                f"Invalid version format '{value}'. Must follow PEP 440 standards."
            ) from err
        return trimmed

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """Ensure description is a non-empty string."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Description cannot be empty.")
        return trimmed

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        """Validate that api_version is currently supported."""
        trimmed = str(value).strip()
        if trimmed not in SUPPORTED_API_VERSIONS:
            valid_list = ", ".join(sorted(SUPPORTED_API_VERSIONS))
            raise ValueError(
                f"Unsupported api_version '{value}'. Supported versions: {valid_list}."
            )
        return trimmed

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Validate that category is a recognized AI/ML domain."""
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_CATEGORIES:
            valid = ", ".join(sorted(SUPPORTED_CATEGORIES))
            raise ValueError(
                f"Unsupported category '{value}'. Supported categories are: {valid}."
            )
        return normalized

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint_syntax(cls, value: str) -> str:
        """Validate entrypoint syntax ('<module_path>:<class_name>')."""
        trimmed = value.strip()
        if ":" not in trimmed:
            raise ValueError(
                f"Invalid entrypoint format '{value}'. "
                "Must be formatted as '<module_path>:<class_name>'."
            )

        parts = trimmed.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid entrypoint format '{value}'. "
                "Must contain exactly one ':' separating module and class."
            )

        module_path, class_name = parts[0].strip(), parts[1].strip()
        if not module_path:
            raise ValueError(f"Entrypoint '{value}' is missing the module path.")
        if not class_name:
            raise ValueError(f"Entrypoint '{value}' is missing the class name.")

        module_segments = module_path.split(".")
        for segment in module_segments:
            if not segment.isidentifier():
                raise ValueError(
                    f"Invalid module identifier '{segment}' in entrypoint '{value}'."
                )

        if not class_name.isidentifier():
            raise ValueError(
                f"Invalid class identifier '{class_name}' in entrypoint '{value}'."
            )

        return trimmed

    @field_validator("inputs", "outputs")
    @classmethod
    def validate_port_names(
        cls, value: dict[str, PortDefinition]
    ) -> dict[str, PortDefinition]:
        """Ensure port identifiers are valid alphanumeric/underscore names."""
        for port_name in value:
            if not port_name.isidentifier():
                raise ValueError(
                    f"Invalid port name '{port_name}'. Must be a valid identifier."
                )
        return value

    @field_validator("config")
    @classmethod
    def validate_config_keys(
        cls, value: dict[str, ConfigDefinition]
    ) -> dict[str, ConfigDefinition]:
        """Ensure config parameter keys are valid identifier names."""
        for config_key in value:
            if not config_key.isidentifier():
                raise ValueError(
                    f"Invalid config key '{config_key}'. Must be a valid identifier."
                )
        return value

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, value: list[str]) -> list[str]:
        """Validate PEP 508 dependency strings using packaging."""
        validated: list[str] = []
        for dep in value:
            trimmed = str(dep).strip()
            if not trimmed:
                raise ValueError("Empty dependency string encountered.")
            try:
                Requirement(trimmed)
            except InvalidRequirement as err:
                raise ValueError(
                    f"Invalid dependency specification '{dep}'. Must follow PEP 508."
                ) from err
            validated.append(trimmed)
        return validated


PortDefinition.model_rebuild()
ComponentManifest.model_rebuild()
