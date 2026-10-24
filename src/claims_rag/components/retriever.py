"""Retriever protocol and an in-memory cosine-similarity implementation (LLD §4.8)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from claims_rag.components.chunker import Chunk
from claims_rag.errors import RetrieverError


@dataclass(frozen=True)
class RetrievedChunk:
    clause_id: str
    source: str
    section: str
    title: str
    text: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Retriever(Protocol):
    def index(self, chunks: Sequence[Chunk]) -> None: ...
    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]: ...


def _normalise(matrix: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    if np.any(norms == 0):
        raise RetrieverError("embedding is a zero vector")
    return matrix / norms


class InMemoryRetriever:
    """Knows nothing about Bedrock: embeddings come from an injected embed_fn.

    Production swap: a KnowledgeBaseRetriever over Bedrock Agent Runtime `retrieve` with the same protocol.
    """

    def __init__(self, embed_fn: Callable[[str], list[float]]) -> None:
        self._embed = embed_fn
        self._chunks: list[Chunk] = []
        self._matrix: npt.NDArray[np.float64] | None = None

    def index(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            raise RetrieverError("nothing to index")
        matrix = np.array([self._embed(c.text) for c in chunks], dtype=np.float64)
        self._matrix = _normalise(matrix)  # L2-normalised rows: dot product = cosine similarity
        self._chunks = list(chunks)

    def retrieve(self, query: str, k: int) -> list[RetrievedChunk]:
        if self._matrix is None:
            raise RetrieverError("retrieve called before index")
        if k < 1:
            raise RetrieverError(f"k must be >= 1, got {k}")
        scores = self._matrix @ _normalise(np.array(self._embed(query), dtype=np.float64))
        top = np.argsort(-scores, kind="stable")[:k]
        return [RetrievedChunk(**self._chunks[i].to_dict(), score=float(scores[i])) for i in top]
