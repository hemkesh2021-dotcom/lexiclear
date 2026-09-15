"""Hybrid retrieval over a single document's chunks.

Legal questions mix two very different signals.  *"What is the notice period?"*
is semantic - the contract may say "terminate upon thirty (30) days' written
intimation" and never use the word *notice*.  *"What does clause 14.2 say?"* is
lexical - only an exact token match will do.

Neither dense nor sparse retrieval handles both well on its own, so a BM25 index
and a cosine-similarity index are run in parallel and their results combined.

The combination is a *weighted min-max score fusion* rather than Reciprocal Rank
Fusion.  RRF is the usual choice for web-scale corpora, where absolute scores
are incomparable and only order can be trusted.  Here the corpus is a few dozen
passages from one document, and the score magnitudes are exactly the signal that
matters: a query naming an operative term scores its clause several times higher
than anything else, while every other passage sits near zero.  Discarding that
gap - as RRF does, since rank 1 and rank 2 differ by a constant - lets an
incidental semantic match outrank a decisive lexical one.  Normalising each
modality to ``[0, 1]`` and taking a weighted sum keeps the gap and remains
scale-free across the two indexes.

Lexical evidence carries the larger weight because in legal drafting the
operative words are chosen deliberately, and a passage that literally contains
"indemnify" is more likely to be the indemnity clause than one that merely
resembles it.

BM25 is implemented here rather than pulled in as a dependency: the corpus is
one document, the algorithm is forty lines, and owning it keeps the container
small and the behaviour fully under test.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.services.chunking import Chunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: Okapi BM25 parameters; the Robertson/Sparck-Jones defaults.
_BM25_K1 = 1.5
_BM25_B = 0.75

#: Fusion weights, summing to one. Lexical evidence dominates because exact
#: terminology is operative in legal text; semantic evidence covers the cases
#: where the document words a concept differently from the question.
LEXICAL_WEIGHT = 0.6
SEMANTIC_WEIGHT = 0.4


def tokenise(text: str) -> list[str]:
    """Lower-case and split ``text`` into alphanumeric tokens."""
    return _TOKEN_PATTERN.findall(text.lower())


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk selected for a query, with the score that selected it."""

    chunk: Chunk
    score: float


class Bm25Index:
    """A compact Okapi BM25 index over a fixed set of chunks."""

    def __init__(self, chunks: list[Chunk]) -> None:
        """Build term frequencies and inverse document frequencies."""
        self._documents = [tokenise(chunk.text) for chunk in chunks]
        self._frequencies = [Counter(tokens) for tokens in self._documents]
        self._lengths = np.array([len(tokens) for tokens in self._documents], dtype=np.float64)
        self._average_length = float(self._lengths.mean()) if len(self._lengths) else 0.0

        document_count = len(self._documents)
        appearances: Counter[str] = Counter()
        for frequencies in self._frequencies:
            appearances.update(frequencies.keys())
        self._idf = {
            term: math.log(1.0 + (document_count - count + 0.5) / (count + 0.5))
            for term, count in appearances.items()
        }

    def score(self, query: str) -> npt.NDArray[np.float64]:
        """Score every chunk against ``query``.

        Args:
            query: The raw query text.

        Returns:
            One BM25 score per chunk, in chunk order.
        """
        scores = np.zeros(len(self._documents), dtype=np.float64)
        if self._average_length == 0.0:
            return scores

        for term in tokenise(query):
            idf = self._idf.get(term)
            if idf is None:
                continue
            for index, frequencies in enumerate(self._frequencies):
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                normaliser = _BM25_K1 * (
                    1 - _BM25_B + _BM25_B * self._lengths[index] / self._average_length
                )
                scores[index] += idf * frequency * (_BM25_K1 + 1) / (frequency + normaliser)
        return scores


class HybridRetriever:
    """Fuses BM25 and dense-vector rankings over one document."""

    def __init__(self, chunks: list[Chunk], embeddings: npt.NDArray[np.float32]) -> None:
        """Store the chunks and their L2-normalised embedding matrix.

        Args:
            chunks: The document's chunks, in order.
            embeddings: A ``(len(chunks), dimensions)`` matrix of vectors.
        """
        self._chunks = chunks
        self._embeddings = self._normalise(embeddings)
        self._bm25 = Bm25Index(chunks)

    @staticmethod
    def _normalise(matrix: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        """Return ``matrix`` with every row scaled to unit length."""
        if matrix.size == 0:
            return matrix
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        normalised: npt.NDArray[np.float32] = matrix / np.maximum(norms, 1e-9)
        return normalised

    @staticmethod
    def _min_max(scores: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Rescale ``scores`` to ``[0, 1]``, mapping a flat input to all zeros.

        Args:
            scores: Raw scores from one retrieval modality.

        Returns:
            The same scores on a common scale, so modalities can be summed.
        """
        if scores.size == 0:
            return scores
        lowest = float(scores.min())
        highest = float(scores.max())
        spread = highest - lowest
        if spread <= 1e-12:
            # Every passage scored alike: this modality has no opinion, and
            # contributing a constant would only dilute the other one.
            return np.zeros_like(scores)
        return (scores - lowest) / spread

    def search(
        self,
        *,
        query: str,
        query_embedding: npt.NDArray[np.float32],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Return the ``top_k`` chunks most relevant to ``query``.

        Args:
            query: The raw query text, used for the lexical ranking.
            query_embedding: The query's dense vector.
            top_k: Maximum number of chunks to return.

        Returns:
            The selected chunks with their fused scores, best first.
        """
        if not self._chunks:
            return []

        lexical = self._min_max(self._bm25.score(query))

        vector = query_embedding.astype(np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector = vector / norm
        semantic_raw = (
            (self._embeddings @ vector).astype(np.float64)
            if self._embeddings.size and norm > 0
            else np.zeros(len(self._chunks), dtype=np.float64)
        )
        semantic = self._min_max(semantic_raw)

        fused = LEXICAL_WEIGHT * lexical + SEMANTIC_WEIGHT * semantic

        # Ties break on chunk order, so the same query always returns the same
        # passages in the same order - a property the snapshot tests rely on.
        ordered = sorted(range(len(self._chunks)), key=lambda index: (-fused[index], index))
        return [
            RetrievedChunk(chunk=self._chunks[index], score=round(float(fused[index]), 6))
            for index in ordered[:top_k]
        ]
