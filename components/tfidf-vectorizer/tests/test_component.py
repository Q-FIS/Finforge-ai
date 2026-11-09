"""Tests for the tfidf-vectorizer component (RET-07)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from tfidf_vectorizer.component import TfidfVectorizerComponent
from tfidf_vectorizer.tfidf import TfidfModel, compute_idf, document_frequency

from finforge.component import BaseComponent
from finforge.contracts import validate_inputs, validate_outputs
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)
from finforge.manifest import load_manifest
from finforge.pipeline import Pipeline
from finforge.registry import ComponentRegistry

COMPONENT_DIR = Path(__file__).resolve().parents[1]
MANIFEST = load_manifest(COMPONENT_DIR / "component.yaml")
TOL = 1e-9

# Small tokenised annual-report passages (tokens as a financial tokenizer
# would emit them; RET-02 owns tokenisation).
PASSAGES: list[list[str]] = [
    ["revenue", "rose", "12.5%", "to", "₹1,45,000", "crore", "in", "fy2025"],
    ["net", "profit", "rose", "in", "fy2025", "profit", "margin", "improved"],
    ["the", "board", "declared", "a", "dividend", "of", "₹12", "per", "share"],
    ["revenue", "from", "operations", "in", "fy2024", "was", "₹1,28,900", "crore"],
]
QUERIES: list[list[str]] = [
    ["revenue", "fy2025"],
    ["dividend", "per", "share", "ebitda"],
    ["unseen", "terms"],
]


def _run(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    comp = TfidfVectorizerComponent()
    comp.setup(config)
    try:
        return comp.run(inputs, context={})
    finally:
        comp.teardown()


def _max_abs_diff(a: list[list[float]], b: list[list[float]]) -> float:
    assert len(a) == len(b)
    diffs = [
        abs(x - y)
        for row_a, row_b in zip(a, b, strict=True)
        for x, y in zip(row_a, row_b, strict=True)
    ]
    return max(diffs, default=0.0)


# --------------------------------------------------------------------------
# Lifecycle and configuration
# --------------------------------------------------------------------------


def test_inherits_base_component() -> None:
    assert isinstance(TfidfVectorizerComponent(), BaseComponent)


def test_lifecycle() -> None:
    comp = TfidfVectorizerComponent()
    with pytest.raises(ComponentLifecycleError):
        comp.run({"documents": PASSAGES}, context={})
    comp.setup({})
    assert comp.run({"documents": PASSAGES}, context={})["vocabulary"]
    comp.teardown()
    comp.teardown()  # idempotent
    with pytest.raises(ComponentLifecycleError):
        comp.run({"documents": PASSAGES}, context={})


@pytest.mark.parametrize(
    "config",
    [
        {"idf_convention": "bm25"},
        {"norm": "l3"},
        {"sublinear_tf": "yes"},
        {"lowercase": True},
    ],
)
def test_invalid_config(config: dict[str, Any]) -> None:
    with pytest.raises(ComponentConfigurationError):
        TfidfVectorizerComponent().setup(config)


# --------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------


def test_outputs_satisfy_manifest_contract() -> None:
    inputs = {"documents": PASSAGES, "queries": QUERIES}
    validate_inputs(inputs, MANIFEST.inputs)
    outputs = _run({}, inputs)
    validate_outputs(outputs, MANIFEST.outputs)
    assert set(outputs) == set(MANIFEST.outputs)


def test_shapes_and_alignment() -> None:
    out = _run({}, {"documents": PASSAGES, "queries": QUERIES})
    v = len(out["vocabulary"])
    assert out["vocabulary"] == sorted(out["vocabulary"])
    assert len(out["idf"]) == v == len(out["document_frequency"])
    assert len(out["document_vectors"]) == len(PASSAGES)
    assert len(out["query_vectors"]) == len(QUERIES)
    assert all(len(row) == v for row in out["document_vectors"])
    assert all(len(row) == v for row in out["query_vectors"])


def test_queries_optional() -> None:
    out = _run({}, {"documents": PASSAGES})
    assert out["query_vectors"] == []
    assert out["query_oov_terms"] == []


# --------------------------------------------------------------------------
# Hand-computed values
# --------------------------------------------------------------------------


def test_document_frequency_counts_once_per_document() -> None:
    assert document_frequency([["a", "a", "b"], ["a"]]) == {"a": 2, "b": 1}


def test_idf_conventions_hand_computed() -> None:
    # N = 4, df = 1
    assert compute_idf(1, 4, "smooth") == pytest.approx(math.log(5 / 2) + 1, abs=TOL)
    assert compute_idf(1, 4, "unsmoothed") == pytest.approx(math.log(4) + 1, abs=TOL)
    assert compute_idf(1, 4, "textbook") == pytest.approx(math.log(4), abs=TOL)
    # A term in every document: smooth/unsmoothed keep weight 1, textbook gives 0.
    assert compute_idf(4, 4, "smooth") == pytest.approx(1.0, abs=TOL)
    assert compute_idf(4, 4, "textbook") == pytest.approx(0.0, abs=TOL)


def test_idf_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        compute_idf(0, 4, "smooth")
    with pytest.raises(ValueError):
        compute_idf(5, 4, "smooth")


def test_tfidf_vector_hand_computed() -> None:
    # docs: [a, b], [a, c]   N=2   df(a)=2 df(b)=1 df(c)=1   (smooth IDF)
    out = _run({}, {"documents": [["a", "b"], ["a", "c"]]})
    assert out["vocabulary"] == ["a", "b", "c"]
    idf_b = math.log(3 / 2) + 1
    assert out["idf"] == pytest.approx([1.0, idf_b, idf_b], abs=TOL)
    length = math.sqrt(1.0 + idf_b**2)
    expected = [1.0 / length, idf_b / length, 0.0]
    assert out["document_vectors"][0] == pytest.approx(expected, abs=TOL)


def test_sublinear_tf_and_no_norm() -> None:
    out = _run(
        {"sublinear_tf": True, "norm": "none"},
        {"documents": [["a", "a", "a", "b"], ["b"]]},
    )
    idf_a = math.log(3 / 2) + 1
    assert out["document_vectors"][0][0] == pytest.approx(
        (1 + math.log(3)) * idf_a, abs=TOL
    )
    assert out["document_vectors"][0][1] == pytest.approx(1.0, abs=TOL)


def test_l1_and_l2_norms() -> None:
    l2 = _run({"norm": "l2"}, {"documents": PASSAGES})["document_vectors"]
    l1 = _run({"norm": "l1"}, {"documents": PASSAGES})["document_vectors"]
    for row in l2:
        assert math.fsum(x * x for x in row) == pytest.approx(1.0, abs=TOL)
    for row in l1:
        assert math.fsum(abs(x) for x in row) == pytest.approx(1.0, abs=TOL)


# --------------------------------------------------------------------------
# Fit / transform behaviour and edge cases
# --------------------------------------------------------------------------


def test_out_of_vocabulary_terms_reported_not_silent() -> None:
    out = _run({}, {"documents": PASSAGES, "queries": QUERIES})
    assert out["query_oov_terms"][0] == []
    assert out["query_oov_terms"][1] == ["ebitda"]
    assert out["query_oov_terms"][2] == ["terms", "unseen"]
    assert all(x == 0.0 for x in out["query_vectors"][2])


def test_queries_do_not_change_fitted_idf() -> None:
    without = _run({}, {"documents": PASSAGES})
    with_q = _run({}, {"documents": PASSAGES, "queries": QUERIES})
    assert without["vocabulary"] == with_q["vocabulary"]
    assert without["idf"] == with_q["idf"]


def test_empty_passage_gives_zero_vector() -> None:
    out = _run({}, {"documents": [["revenue"], []]})
    assert out["document_vectors"][1] == [0.0]


def test_deterministic() -> None:
    first = _run({}, {"documents": PASSAGES, "queries": QUERIES})
    second = _run({}, {"documents": PASSAGES, "queries": QUERIES})
    assert first == second


@pytest.mark.parametrize(
    "documents",
    [
        [],  # no passages
        [[], []],  # empty vocabulary
        "revenue rose",  # raw text instead of tokens
        ["revenue rose"],  # passage not tokenised
        [["revenue", 12.5]],  # non-string token
    ],
)
def test_malformed_documents_raise_execution_error(documents: Any) -> None:
    with pytest.raises(ComponentExecutionError):
        _run({}, {"documents": documents})


def test_missing_documents_port() -> None:
    with pytest.raises(ComponentExecutionError):
        _run({}, {"queries": QUERIES})


def test_model_transform_before_fit() -> None:
    with pytest.raises(RuntimeError):
        TfidfModel().transform([["a"]])


# --------------------------------------------------------------------------
# scikit-learn parity (tolerance 1e-9)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("convention", ["smooth", "unsmoothed"])
@pytest.mark.parametrize("sublinear_tf", [False, True])
@pytest.mark.parametrize("norm", ["l2", "l1", "none"])
def test_parity_with_scikit_learn(
    convention: str, sublinear_tf: bool, norm: str
) -> None:
    sklearn_text = pytest.importorskip("sklearn.feature_extraction.text")

    def identity(tokens: list[str]) -> list[str]:
        return tokens

    vectorizer = sklearn_text.TfidfVectorizer(
        analyzer=identity,
        smooth_idf=(convention == "smooth"),
        sublinear_tf=sublinear_tf,
        norm=None if norm == "none" else norm,
    )
    sk_docs = vectorizer.fit_transform(PASSAGES).toarray().tolist()
    sk_queries = vectorizer.transform(QUERIES).toarray().tolist()

    out = _run(
        {"idf_convention": convention, "sublinear_tf": sublinear_tf, "norm": norm},
        {"documents": PASSAGES, "queries": QUERIES},
    )

    assert out["vocabulary"] == list(vectorizer.get_feature_names_out())
    assert (
        max(
            abs(a - b)
            for a, b in zip(out["idf"], vectorizer.idf_.tolist(), strict=True)
        )
        <= TOL
    )
    assert _max_abs_diff(out["document_vectors"], sk_docs) <= TOL
    assert _max_abs_diff(out["query_vectors"], sk_queries) <= TOL


# --------------------------------------------------------------------------
# FinForge registry and pipeline integration
# --------------------------------------------------------------------------


def test_registers_and_runs_in_pipeline() -> None:
    registry = ComponentRegistry()
    registry.register(TfidfVectorizerComponent, MANIFEST)
    assert registry.get("tfidf-vectorizer") is TfidfVectorizerComponent

    pipeline = Pipeline("ret07-test", registry=registry)
    pipeline.add("tfidf", "tfidf-vectorizer", config={"idf_convention": "smooth"})
    result = pipeline.run(inputs={"tfidf": {"documents": PASSAGES, "queries": QUERIES}})

    assert result.success, result.execution_errors
    assert (
        result.outputs["tfidf"]["vocabulary"]
        == _run({}, {"documents": PASSAGES})["vocabulary"]
    )
