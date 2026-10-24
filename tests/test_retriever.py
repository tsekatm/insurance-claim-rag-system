"""LLD §4.8: in-memory cosine retrieval over an injected embedding function."""

import pytest

from claims_rag.components.chunker import Chunk
from claims_rag.components.retriever import InMemoryRetriever, Retriever
from claims_rag.errors import RetrieverError

VECTORS = {"storm": [1.0, 0.0, 0.0], "leak": [0.0, 1.0, 0.0], "theft": [0.0, 0.0, 1.0]}


def fake_embed(text: str) -> list[float]:
    """Deterministic: sums one axis per keyword; unnormalised on purpose."""
    vec = [0.0, 0.0, 0.0]
    for word, axis in VECTORS.items():
        if word in text:
            vec = [a + 3 * b for a, b in zip(vec, axis, strict=True)]
    return vec


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(clause_id=cid, source="p.txt", section=cid, title=cid, text=text)


CHUNKS = [
    _chunk("1", "storm damage is covered"),
    _chunk("2", "gradual leak is excluded"),
    _chunk("3", "theft"),
]


def test_retrieves_top_k_by_cosine_descending() -> None:
    retriever = InMemoryRetriever(fake_embed)
    retriever.index(CHUNKS)

    results = retriever.retrieve("a slow leak and some storm", k=2)
    assert {r.clause_id for r in results} == {"1", "2"}
    assert results[0].score >= results[1].score
    assert results[0].score == pytest.approx(2**-0.5)

    (best,) = retriever.retrieve("pipe leak", k=1)
    assert best.clause_id == "2"
    assert best.score == pytest.approx(1.0)
    assert best.text == "gradual leak is excluded"
    assert best.to_dict()["clause_id"] == "2"


def test_k_larger_than_index_returns_everything() -> None:
    retriever = InMemoryRetriever(fake_embed)
    retriever.index(CHUNKS)
    assert len(retriever.retrieve("storm", k=10)) == 3


def test_satisfies_protocol() -> None:
    retriever: Retriever = InMemoryRetriever(fake_embed)
    assert retriever is not None


def test_retrieve_before_index() -> None:
    with pytest.raises(RetrieverError, match="index"):
        InMemoryRetriever(fake_embed).retrieve("storm", k=1)


def test_k_must_be_positive() -> None:
    retriever = InMemoryRetriever(fake_embed)
    retriever.index(CHUNKS)
    with pytest.raises(RetrieverError, match="k"):
        retriever.retrieve("storm", k=0)


def test_empty_index_and_zero_vectors_are_errors() -> None:
    with pytest.raises(RetrieverError):
        InMemoryRetriever(fake_embed).index([])
    with pytest.raises(RetrieverError, match="zero"):
        InMemoryRetriever(fake_embed).index([_chunk("9", "nothing matches")])
