"""Universal BaseComponent interface for FinForge AI.

This module defines the foundational abstract class that all FinForge AI
components must implement, providing a consistent lifecycle and contract
across Classical ML, Deep Learning, LLMs, RAG, Agentic, and Multimodal components.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseComponent(ABC):
    """Abstract base class for all FinForge AI components.

    Every FinForge AI component adheres to a three-stage lifecycle:
      1. `setup(config)`: Prepares internal state, validates configuration, and
         initializes resources (e.g. weights, indices, scratch buffers).
      2. `run(inputs, context)`: Executes the core operation on input data,
         leveraging runtime context, and returning structured outputs.
      3. `teardown()`: Releases acquired resources, file handles, or buffers.

    The interface is strictly framework-agnostic and relies on dictionary-based
    data contracts for inputs, outputs, configuration, and context.
    """

    @abstractmethod
    def setup(self, config: dict[str, Any]) -> None:
        """Initialize the component and prepare its internal state.

        This method is invoked prior to execution. It receives the component's
        configuration parameters and is responsible for setting up internal state,
        allocating memory, or preparing resources.

        Args:
            config: A dictionary containing component-specific configuration options.

        Raises:
            ComponentConfigurationError: If required configuration parameters are
                missing, malformed, or incompatible.
        """

    @abstractmethod
    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the primary operation of the component.

        Processes the given input dictionary within the provided runtime context
        and returns the resulting outputs as a dictionary.

        Args:
            inputs: A dictionary containing input data conforming to the component's
                input contract.
            context: A dictionary containing runtime execution context (e.g. metadata,
                shared pipeline state, execution trace IDs).

        Returns:
            A dictionary containing the component's execution results conforming to
            its output contract.

        Raises:
            ComponentLifecycleError: If the component has not been initialized via
                `setup()` prior to invocation.
            ComponentExecutionError: If input data is invalid, required keys are
                missing, or an error occurs during computation.
        """

    def teardown(self) -> None:  # noqa: B027
        """Release resources acquired by the component.

        Optional lifecycle hook called when component execution is complete or
        during cleanup. Subclasses should override this method to close file handles,
        release memory buffers, or clean up temporary files.

        The default implementation is a safe no-op. Subclass implementations
        should be idempotent (safe to call multiple times).
        """

    def __repr__(self) -> str:
        """Return a string representation of the component."""
        return f"<{self.__class__.__name__}>"
