"""Scratch implementation of IDF and TF-IDF weighting.

The module is framework-independent: it only uses the Python standard library
so that every number can be traced back to a formula. The FinForge component in
``component.py`` wraps :class:`TfidfModel`.

Notation used below:

* ``N``      - number of documents in the fitted collection.
* ``df(t)``  - number of documents that contain term ``t`` at least once.
* ``tf(t,d)`` - number of times term ``t`` occurs in document ``d``.

IDF conventions (``idf_convention``):

* ``"smooth"``     - ``ln((1 + N) / (1 + df)) + 1``.
  Identical to scikit-learn ``TfidfVectorizer(smooth_idf=True)`` (its default).
* ``"unsmoothed"`` - ``ln(N / df) + 1``.
  Identical to scikit-learn ``TfidfVectorizer(smooth_idf=False)``.
* ``"textbook"``   - ``ln(N / df)`` (Manning, Raghavan and Schutze, ch. 6).
  A term present in every document receives weight 0.

TF variants:

* raw counts ``tf(t,d)`` (default, as in scikit-learn), or
* sublinear ``1 + ln(tf(t,d))`` for ``tf > 0`` (``sublinear_tf=True``).

Each document vector is ``tf * idf``, then optionally normalised (``"l2"``,
``"l1"`` or ``"none"``).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

IDF_CONVENTIONS: tuple[str, ...] = ("smooth", "unsmoothed", "textbook")
NORMS: tuple[str, ...] = ("l2", "l1", "none")

TokenizedDocuments = Sequence[Sequence[str]]


def validate_tokenized(documents: object, name: str) -> list[list[str]]:
    """Check that ``documents`` is a sequence of token sequences of strings.

    Returns a defensive copy as ``list[list[str]]``.

    Raises:
        TypeError: If the structure or a token has the wrong type.
    """
    if isinstance(documents, (str, bytes)) or not isinstance(documents, (list, tuple)):
        raise TypeError(
            f"'{name}' must be a list of token lists, got {type(documents).__name__}."
        )
    copied: list[list[str]] = []
    for i, doc in enumerate(documents):
        if isinstance(doc, (str, bytes)) or not isinstance(doc, (list, tuple)):
            raise TypeError(
                f"'{name}[{i}]' must be a list of string tokens, "
                f"got {type(doc).__name__}. Tokenise text before TF-IDF."
            )
        for j, token in enumerate(doc):
            if not isinstance(token, str):
                raise TypeError(
                    f"'{name}[{i}][{j}]' must be a string token, "
                    f"got {type(token).__name__}."
                )
        copied.append(list(doc))
    return copied


def document_frequency(documents: TokenizedDocuments) -> dict[str, int]:
    """Return ``df(t)``: the number of documents containing each term.

    A term counts at most once per document, however often it repeats.
    """
    df: Counter[str] = Counter()
    for doc in documents:
        df.update(set(doc))
    return dict(df)


def compute_idf(df: int, n_documents: int, convention: str) -> float:
    """Return the IDF weight of a term with document frequency ``df``.

    Raises:
        ValueError: If the convention is unknown or the counts are impossible.
    """
    if convention not in IDF_CONVENTIONS:
        raise ValueError(
            f"Unknown IDF convention '{convention}'. "
            f"Expected one of {', '.join(IDF_CONVENTIONS)}."
        )
    if n_documents < 1 or df < 1 or df > n_documents:
        raise ValueError(
            f"Invalid counts: df={df}, n_documents={n_documents}. "
            "Require 1 <= df <= n_documents."
        )
    if convention == "smooth":
        return math.log((1 + n_documents) / (1 + df)) + 1.0
    if convention == "unsmoothed":
        return math.log(n_documents / df) + 1.0
    return math.log(n_documents / df)


def _normalise(vector: list[float], norm: str) -> list[float]:
    """Normalise ``vector``; an all-zero vector is returned unchanged."""
    if norm == "none":
        return vector
    if norm == "l2":
        length = math.sqrt(math.fsum(v * v for v in vector))
    else:
        length = math.fsum(abs(v) for v in vector)
    if length == 0.0:
        return vector
    return [v / length for v in vector]


class TfidfModel:
    """TF-IDF model with separate ``fit`` and ``transform`` steps.

    ``fit`` learns the vocabulary and IDF weights from a document collection.
    ``transform`` maps any token lists (documents or queries) onto those same
    vocabulary dimensions. Terms not seen during ``fit`` are out-of-vocabulary
    (OOV): they are ignored and reported, never silently dropped.

    The vocabulary is sorted lexicographically, which matches the column order
    of scikit-learn's ``get_feature_names_out()``.
    """

    def __init__(
        self,
        idf_convention: str = "smooth",
        sublinear_tf: bool = False,
        norm: str = "l2",
    ) -> None:
        if idf_convention not in IDF_CONVENTIONS:
            raise ValueError(
                f"Unknown IDF convention '{idf_convention}'. "
                f"Expected one of {', '.join(IDF_CONVENTIONS)}."
            )
        if norm not in NORMS:
            raise ValueError(
                f"Unknown norm '{norm}'. Expected one of {', '.join(NORMS)}."
            )
        self.idf_convention = idf_convention
        self.sublinear_tf = sublinear_tf
        self.norm = norm
        self._vocabulary: list[str] = []
        self._index: dict[str, int] = {}
        self._idf: list[float] = []
        self._document_frequency: list[int] = []
        self._n_documents = 0

    @property
    def is_fitted(self) -> bool:
        """Whether :meth:`fit` has been called successfully."""
        return bool(self._vocabulary)

    @property
    def vocabulary(self) -> list[str]:
        """Sorted vocabulary learned by :meth:`fit`."""
        return list(self._vocabulary)

    @property
    def idf(self) -> list[float]:
        """IDF weight per vocabulary term, aligned with :attr:`vocabulary`."""
        return list(self._idf)

    @property
    def document_frequency(self) -> list[int]:
        """``df`` per vocabulary term, aligned with :attr:`vocabulary`."""
        return list(self._document_frequency)

    @property
    def n_documents(self) -> int:
        """Number of documents seen by :meth:`fit`."""
        return self._n_documents

    def fit(self, documents: TokenizedDocuments) -> TfidfModel:
        """Learn vocabulary, document frequencies and IDF weights.

        Raises:
            TypeError: If ``documents`` is not a list of string-token lists.
            ValueError: If there are no documents or no tokens at all.
        """
        docs = validate_tokenized(documents, "documents")
        if not docs:
            raise ValueError("Cannot fit TF-IDF on an empty document collection.")
        df = document_frequency(docs)
        if not df:
            raise ValueError(
                "Empty vocabulary: every document has zero tokens. "
                "Check the tokenisation / stop-word settings upstream."
            )
        n = len(docs)
        self._vocabulary = sorted(df)
        self._index = {term: i for i, term in enumerate(self._vocabulary)}
        self._document_frequency = [df[t] for t in self._vocabulary]
        self._idf = [
            compute_idf(d, n, self.idf_convention) for d in self._document_frequency
        ]
        self._n_documents = n
        return self

    def transform(
        self, documents: TokenizedDocuments
    ) -> tuple[list[list[float]], list[list[str]]]:
        """Map token lists to TF-IDF vectors using the fitted vocabulary.

        Returns:
            ``(vectors, oov_terms)`` where ``vectors[i]`` is the dense vector of
            ``documents[i]`` (length ``len(vocabulary)``) and ``oov_terms[i]``
            lists, sorted and de-duplicated, the terms of ``documents[i]`` that
            were ignored because they are not in the vocabulary.

        Raises:
            RuntimeError: If called before :meth:`fit`.
            TypeError: If ``documents`` is not a list of string-token lists.
        """
        if not self.is_fitted:
            raise RuntimeError("TfidfModel.transform() called before fit().")
        docs = validate_tokenized(documents, "documents")
        vectors: list[list[float]] = []
        oov: list[list[str]] = []
        size = len(self._vocabulary)
        for doc in docs:
            vector = [0.0] * size
            unknown: set[str] = set()
            for term, count in Counter(doc).items():
                idx = self._index.get(term)
                if idx is None:
                    unknown.add(term)
                    continue
                tf = 1.0 + math.log(count) if self.sublinear_tf else float(count)
                vector[idx] = tf * self._idf[idx]
            vectors.append(_normalise(vector, self.norm))
            oov.append(sorted(unknown))
        return vectors, oov

    def fit_transform(self, documents: TokenizedDocuments) -> list[list[float]]:
        """Fit on ``documents`` and return their TF-IDF vectors."""
        self.fit(documents)
        vectors, _ = self.transform(documents)
        return vectors
