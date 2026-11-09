"""FinForge component wrapping the scratch TF-IDF model (RET-07)."""

from __future__ import annotations

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)
from tfidf_vectorizer.tfidf import IDF_CONVENTIONS, NORMS, TfidfModel

_CONFIG_KEYS = frozenset({"idf_convention", "sublinear_tf", "norm"})


class TfidfVectorizerComponent(BaseComponent):
    """Fit IDF on tokenised passages and emit TF-IDF vectors.

    Inputs:
        documents: list of token lists (one per passage) used to fit the model.
        queries: optional list of token lists transformed with the fitted model.

    Outputs:
        vocabulary, idf, document_frequency, document_vectors, query_vectors,
        query_oov_terms. ``document_vectors[i]`` belongs to ``documents[i]``;
        callers keep passage IDs aligned by position.
    """

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._idf_convention: str = "smooth"
        self._sublinear_tf: bool = False
        self._norm: str = "l2"

    def setup(self, config: dict[str, Any]) -> None:
        """Validate and store TF-IDF configuration."""
        unknown = set(config) - _CONFIG_KEYS
        if unknown:
            raise ComponentConfigurationError(
                f"Unknown config key(s): {', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(sorted(_CONFIG_KEYS))}."
            )

        idf_convention = config.get("idf_convention", "smooth")
        if idf_convention not in IDF_CONVENTIONS:
            raise ComponentConfigurationError(
                f"'idf_convention' must be one of {', '.join(IDF_CONVENTIONS)}, "
                f"got {idf_convention!r}."
            )

        sublinear_tf = config.get("sublinear_tf", False)
        if not isinstance(sublinear_tf, bool):
            raise ComponentConfigurationError("'sublinear_tf' must be a boolean.")

        norm = config.get("norm", "l2")
        if norm not in NORMS:
            raise ComponentConfigurationError(
                f"'norm' must be one of {', '.join(NORMS)}, got {norm!r}."
            )

        self._idf_convention = idf_convention
        self._sublinear_tf = sublinear_tf
        self._norm = norm
        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Fit on ``documents``; transform ``documents`` and optional ``queries``."""
        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )
        if "documents" not in inputs:
            raise ComponentExecutionError("Missing required input port: 'documents'.")

        queries = inputs.get("queries")
        if queries is None:
            queries = []

        model = TfidfModel(
            idf_convention=self._idf_convention,
            sublinear_tf=self._sublinear_tf,
            norm=self._norm,
        )
        try:
            model.fit(inputs["documents"])
            document_vectors, _ = model.transform(inputs["documents"])
            query_vectors, query_oov = model.transform(queries)
        except (TypeError, ValueError) as err:
            raise ComponentExecutionError(f"TF-IDF failed: {err}") from err

        return {
            "vocabulary": model.vocabulary,
            "idf": model.idf,
            "document_frequency": model.document_frequency,
            "document_vectors": document_vectors,
            "query_vectors": query_vectors,
            "query_oov_terms": query_oov,
        }

    def teardown(self) -> None:
        """Reset configuration. Safe to call multiple times."""
        self._is_configured = False
        self._idf_convention = "smooth"
        self._sublinear_tf = False
        self._norm = "l2"
