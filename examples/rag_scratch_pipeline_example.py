"""End-to-End Scratch-First RAG Pipeline Example in FinForge AI.

Demonstrates a first-principles Retrieval-Augmented Generation pipeline:
1. Document Chunker (scratch character/sentence splitter with overlap)
2. In-Memory BM25 Ranker / Retriever (scratch term frequency/inverse document frequency)
3. Prompt Grounding Synthesizer (scratch template context-assembler)

Zero heavy dependencies (pure Python + FinForge contracts).
"""

from __future__ import annotations

import math
import re
from typing import Any

from finforge.component import BaseComponent
from finforge.manifest.models import ComponentManifest, ConfigDefinition, PortDefinition
from finforge.pipeline.builder import Pipeline
from finforge.registry import ComponentRegistry


# ==============================================================================
# 1. Scratch Component: Recursive Text Chunker
# ==============================================================================
class ScratchChunkerComponent(BaseComponent):
    """Splits raw text documents into overlapping fixed-size chunks."""

    def __init__(self) -> None:
        self._chunk_size: int = 150
        self._overlap: int = 30
        self._configured: bool = False

    def setup(self, config: dict[str, Any]) -> None:
        self._chunk_size = config.get("chunk_size", 150)
        self._overlap = config.get("overlap", 30)
        self._configured = True

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        document = inputs["document"]
        words = document.split()
        chunks: list[str] = []
        step = max(1, self._chunk_size - self._overlap)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + self._chunk_size])
            if chunk:
                chunks.append(chunk)
        return {"chunks": chunks}

    def teardown(self) -> None:
        self._configured = False


# ==============================================================================
# 2. Scratch Component: In-Memory BM25 Retriever
# ==============================================================================
class ScratchBM25RetrieverComponent(BaseComponent):
    """Computes BM25 relevance scores over chunks from first principles."""

    def __init__(self) -> None:
        self._top_k: int = 2
        self._k1: float = 1.5
        self._b: float = 0.75
        self._configured: bool = False

    def setup(self, config: dict[str, Any]) -> None:
        self._top_k = config.get("top_k", 2)
        self._k1 = float(config.get("k1", 1.5))
        self._b = float(config.get("b", 0.75))
        self._configured = True

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        chunks: list[str] = inputs["chunks"]
        query: str = inputs["query"]
        q_tokens = self._tokenize(query)

        if not chunks or not q_tokens:
            return {"retrieved_chunks": []}

        # Document frequencies
        N = len(chunks)
        doc_tokens = [self._tokenize(c) for c in chunks]
        avgdl = sum(len(dt) for dt in doc_tokens) / max(1, N)

        df: dict[str, int] = {}
        for dt in doc_tokens:
            for token in set(dt):
                df[token] = df.get(token, 0) + 1

        scores: list[tuple[float, str]] = []
        for i, dt in enumerate(doc_tokens):
            score = 0.0
            doc_len = len(dt)
            tf_map: dict[str, int] = {}
            for t in dt:
                tf_map[t] = tf_map.get(t, 0) + 1

            for q in q_tokens:
                if q in df:
                    # Robertson-Spärck Jones IDF
                    idf = math.log((N - df[q] + 0.5) / (df[q] + 0.5) + 1.0)
                    tf = tf_map.get(q, 0)
                    numerator = tf * (self._k1 + 1)
                    denominator = tf + self._k1 * (1 - self._b + self._b * (doc_len / avgdl))
                    score += idf * (numerator / max(0.001, denominator))

            scores.append((score, chunks[i]))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for _, c in scores[: self._top_k]]
        return {"retrieved_chunks": top_chunks}

    def teardown(self) -> None:
        self._configured = False


# ==============================================================================
# 3. Scratch Component: Prompt Grounding Synthesizer
# ==============================================================================
class ScratchPromptSynthesizerComponent(BaseComponent):
    """Assembles retrieved context into a grounded reasoning prompt."""

    def __init__(self) -> None:
        self._system_role: str = "Financial Research Analyst"

    def setup(self, config: dict[str, Any]) -> None:
        self._system_role = config.get("system_role", "Financial Research Analyst")

    def run(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        query = inputs["query"]
        retrieved_chunks = inputs["retrieved_chunks"]
        context_block = "\n---\n".join(retrieved_chunks)

        prompt = (
            f"Role: {self._system_role}\n"
            f"Context Evidence:\n{context_block}\n\n"
            f"User Question: {query}\n\n"
            f"Answer based strictly on the evidence above:"
        )
        return {"grounded_prompt": prompt}

    def teardown(self) -> None:
        pass


def build_and_run_rag_pipeline() -> None:
    # 1. Setup Registry with explicit manifests
    registry = ComponentRegistry()

    chunker_manifest = ComponentManifest(
        name="scratch-chunker",
        version="0.1.0",
        description="Scratch text chunker component",
        category="rag",
        entrypoint="examples.rag_scratch_pipeline_example:ScratchChunkerComponent",
        inputs={"document": PortDefinition(type="string", description="Raw corpus")},
        outputs={"chunks": PortDefinition(type="array", description="List of string chunks")},
        config={"chunk_size": ConfigDefinition(type="integer", default=30)},
    )
    registry.register(ScratchChunkerComponent, manifest=chunker_manifest)

    bm25_manifest = ComponentManifest(
        name="scratch-bm25",
        version="0.1.0",
        description="Scratch BM25 keyword ranker component",
        category="rag",
        entrypoint="examples.rag_scratch_pipeline_example:ScratchBM25RetrieverComponent",
        inputs={
            "chunks": PortDefinition(type="array", description="Corpus chunks"),
            "query": PortDefinition(type="string", description="Search query"),
        },
        outputs={"retrieved_chunks": PortDefinition(type="array", description="Top chunks")},
        config={"top_k": ConfigDefinition(type="integer", default=2)},
    )
    registry.register(ScratchBM25RetrieverComponent, manifest=bm25_manifest)

    synth_manifest = ComponentManifest(
        name="scratch-synthesizer",
        version="0.1.0",
        description="Scratch prompt grounding synthesizer",
        category="rag",
        entrypoint="examples.rag_scratch_pipeline_example:ScratchPromptSynthesizerComponent",
        inputs={
            "query": PortDefinition(type="string", description="User question"),
            "retrieved_chunks": PortDefinition(type="array", description="Context passages"),
        },
        outputs={"grounded_prompt": PortDefinition(type="string", description="Final prompt")},
        config={"system_role": ConfigDefinition(type="string", default="Senior Equity Analyst")},
    )
    registry.register(ScratchPromptSynthesizerComponent, manifest=synth_manifest)

    # 2. Build Pipeline DAG
    pipeline = Pipeline("scratch-financial-rag", registry=registry)
    pipeline.add("chunker", "scratch-chunker", config={"chunk_size": 25})
    pipeline.add("retriever", "scratch-bm25", config={"top_k": 2})
    pipeline.add("synthesizer", "scratch-synthesizer")

    # Connect DAG Edges
    pipeline.connect("chunker", "chunks", "retriever", "chunks")
    pipeline.connect("retriever", "retrieved_chunks", "synthesizer", "retrieved_chunks")

    pipeline.validate()
    print("[Pipeline Validation] DAG validated successfully. Zero cycles detected.")
    print(f"[Execution Order] Deterministic order: {pipeline.execution_order()}")

    # 3. Execute Pipeline
    doc_text = (
        "Goldman Sachs declared quarterly earnings beating consensus estimates with $12.7B net revenue. "
        "However, management noted rising credit provision buffers for corporate debt defaults. "
        "Meanwhile, commercial real estate exposure showed signs of maturity pressure and refinancing drag. "
        "Asset and wealth management generated record management fees of $2.4B, balancing volatility."
    )
    user_query = "What risks and credit provision buffers did management report?"

    result = pipeline.run(
        inputs={
            "chunker": {"document": doc_text},
            "retriever": {"query": user_query},
            "synthesizer": {"query": user_query},
        },
    )

    print("\n--- Pipeline Execution Output ---")
    print(f"Status: {result.status.value}")
    print(f"Total Execution Time: {result.duration_ms:.2f}ms")
    synth_output = result.node_results["synthesizer"].outputs["grounded_prompt"]
    print("\n" + synth_output)


if __name__ == "__main__":
    build_and_run_rag_pipeline()
