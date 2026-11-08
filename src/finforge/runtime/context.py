"""Runtime execution context for FinForge AI component execution.

This module provides `ExecutionContext`, which encapsulates the contextual
metadata passed to a component's `run(inputs, context)` method.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionContext:
    """Minimal runtime execution context provided to component nodes.

    Attributes:
        pipeline_name: Name of the executing pipeline.
        node_id: Identifier of the executing node.
        component_name: Registered name of the executing component.
        metadata: Optional arbitrary user-supplied execution metadata.
    """

    pipeline_name: str
    node_id: str
    component_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the context to a safe, independent dictionary."""
        return {
            "pipeline_name": self.pipeline_name,
            "node_id": self.node_id,
            "component_name": self.component_name,
            "metadata": copy.deepcopy(self.metadata),
        }
