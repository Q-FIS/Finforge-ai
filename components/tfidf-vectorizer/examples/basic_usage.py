"""Run the tfidf-vectorizer component through the real FinForge APIs.

Usage (from the repository root, with finforge-ai installed):

    PYTHONPATH=components/tfidf-vectorizer/src \
        python components/tfidf-vectorizer/examples/basic_usage.py
"""

from __future__ import annotations

from pathlib import Path

from tfidf_vectorizer.component import TfidfVectorizerComponent

from finforge.manifest import load_manifest
from finforge.pipeline import Pipeline
from finforge.registry import ComponentRegistry

# Tokenised passages from annual reports. Passage IDs stay aligned by position.
PASSAGE_IDS = ["AR2025-p12", "AR2025-p14", "AR2025-p40", "AR2024-p11"]
PASSAGES = [
    ["revenue", "rose", "12.5%", "to", "₹1,45,000", "crore", "in", "fy2025"],
    ["net", "profit", "rose", "in", "fy2025", "profit", "margin", "improved"],
    ["the", "board", "declared", "a", "dividend", "of", "₹12", "per", "share"],
    ["revenue", "from", "operations", "in", "fy2024", "was", "₹1,28,900", "crore"],
]
QUERIES = [["revenue", "fy2025"], ["dividend", "per", "share", "ebitda"]]


def main() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "component.yaml"

    # 1. Register the component with its validated manifest.
    registry = ComponentRegistry()
    registry.register(TfidfVectorizerComponent, load_manifest(manifest_path))

    # 2. Compose it into a pipeline and run it (contracts validated by FinForge).
    pipeline = Pipeline("ret07-tfidf-demo", registry=registry)
    pipeline.add("tfidf", "tfidf-vectorizer", config={"idf_convention": "smooth"})
    result = pipeline.run(inputs={"tfidf": {"documents": PASSAGES, "queries": QUERIES}})
    if not result.success:
        raise SystemExit(f"Pipeline failed: {result.execution_errors}")

    out = result.outputs["tfidf"]
    vocab = out["vocabulary"]
    print(f"Vocabulary size: {len(vocab)}")
    print("Rarest terms (highest IDF):")
    ranked = sorted(zip(vocab, out["idf"], strict=True), key=lambda t: -t[1])
    for term, idf in ranked[:5]:
        print(f"  {term:<12} idf={idf:.4f}")

    print("\nTop weighted terms per passage:")
    for pid, vector in zip(PASSAGE_IDS, out["document_vectors"], strict=True):
        top = sorted(zip(vocab, vector, strict=True), key=lambda t: -t[1])[:3]
        print(f"  {pid}: " + ", ".join(f"{t}={w:.3f}" for t, w in top))

    for query, oov in zip(QUERIES, out["query_oov_terms"], strict=True):
        print(f"\nQuery {query}: ignored out-of-vocabulary terms = {oov}")


if __name__ == "__main__":
    main()
