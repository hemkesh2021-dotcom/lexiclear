"""Hybrid retrieval combines lexical and semantic evidence."""

import numpy as np
import pytest

from app.llm.base import EmbeddingTask
from app.llm.mock import MockLlmProvider
from app.services.chunking import chunk_document
from app.services.retrieval import Bm25Index, HybridRetriever, tokenise


@pytest.fixture
def chunks(contract_text):
    return chunk_document(contract_text, target_characters=1600, overlap_characters=200)


@pytest.fixture
async def retriever(chunks, mock_llm: MockLlmProvider):
    vectors = await mock_llm.embed([c.text for c in chunks], task=EmbeddingTask.DOCUMENT)
    return HybridRetriever(chunks, np.array(vectors, dtype=np.float32))


async def search(retriever, mock_llm, query, top_k=5):
    vectors = await mock_llm.embed([query], task=EmbeddingTask.QUERY)
    return retriever.search(
        query=query, query_embedding=np.array(vectors[0], dtype=np.float32), top_k=top_k
    )


class TestTokenisation:
    def test_case_and_punctuation_are_folded(self):
        assert tokenise("Thirty (30) DAYS' notice.") == ["thirty", "30", "days", "notice"]


class TestBm25:
    def test_a_rare_term_outranks_a_common_one(self, chunks):
        index = Bm25Index(chunks)
        scores = index.score("indemnify")
        best = chunks[int(np.argmax(scores))]
        assert "indemnif" in best.text.lower()

    def test_an_unseen_term_scores_nothing(self, chunks):
        assert Bm25Index(chunks).score("cryptocurrency").sum() == 0.0

    def test_an_empty_corpus_is_safe(self):
        assert Bm25Index([]).score("anything").size == 0


class TestHybridRetrieval:
    @pytest.mark.parametrize(
        ("query", "expected_phrase"),
        [
            ("How much notice must the tenant give to terminate?", "three (3) months"),
            ("What happens if the rent is paid late?", "three per cent"),
            ("Who chooses the arbitrator?", "sole arbitrator"),
            ("Is there an automatic renewal?", "renew automatically"),
        ],
    )
    async def test_relevant_clauses_are_retrieved(
        self, retriever, mock_llm, query, expected_phrase
    ):
        results = await search(retriever, mock_llm, query)
        assert any(expected_phrase in result.chunk.text for result in results)

    async def test_exact_clause_references_are_found_lexically(self, retriever, mock_llm):
        results = await search(retriever, mock_llm, "indemnify and keep indemnified")
        assert "indemnify and keep indemnified" in results[0].chunk.text

    async def test_results_are_ordered_by_descending_score(self, retriever, mock_llm):
        results = await search(retriever, mock_llm, "termination notice period")
        scores = [result.score for result in results]
        assert scores == sorted(scores, reverse=True)

    async def test_top_k_is_respected(self, retriever, mock_llm):
        assert len(await search(retriever, mock_llm, "rent", top_k=3)) == 3

    async def test_an_empty_document_returns_nothing(self, mock_llm):
        empty = HybridRetriever([], np.zeros((0, 768), dtype=np.float32))
        assert await search(empty, mock_llm, "anything") == []

    async def test_a_zero_query_vector_does_not_divide_by_zero(self, retriever):
        results = retriever.search(
            query="rent", query_embedding=np.zeros(768, dtype=np.float32), top_k=3
        )
        assert len(results) == 3
