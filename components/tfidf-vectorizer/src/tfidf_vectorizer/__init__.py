"""tfidf-vectorizer package (RET-07: IDF and TF-IDF weighting)."""

from tfidf_vectorizer.component import TfidfVectorizerComponent
from tfidf_vectorizer.tfidf import (
    IDF_CONVENTIONS,
    NORMS,
    TfidfModel,
    compute_idf,
    document_frequency,
)

__all__ = [
    "IDF_CONVENTIONS",
    "NORMS",
    "TfidfModel",
    "TfidfVectorizerComponent",
    "compute_idf",
    "document_frequency",
]
