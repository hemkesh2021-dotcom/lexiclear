"""Grounded question answering over a single indexed document.

The answer is streamed rather than buffered: a legal answer is often several
sentences long, and streaming turns a six-second wait into a response that
begins in under a second.  Citations are resolved *before* generation starts and
sent as the first event, so the interface can render the passages the answer
will draw on while the prose is still arriving.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from app.core.config import Settings
from app.llm.base import EmbeddingTask, LlmProvider
from app.schemas.qa import Citation
from app.security.prompt_guard import assert_no_injection
from app.security.redaction import redact
from app.services.prompts import QA_SYSTEM_INSTRUCTION, build_qa_prompt
from app.services.store import StoredDocument

#: Citations are trimmed for display; the full passage stays addressable through
#: the returned character offsets.
_CITATION_PREVIEW_CHARACTERS = 420

#: Sentinel used to keep passage boundaries intact across redaction.
_PASSAGE_SEPARATOR = "\n<<PASSAGE_BREAK>>\n"


class QuestionAnsweringService:
    """Answers questions using only passages retrieved from one document."""

    def __init__(self, *, settings: Settings, llm: LlmProvider) -> None:
        """Wire retrieval settings and the model provider."""
        self._settings = settings
        self._llm = llm

    async def retrieve_citations(
        self, *, document: StoredDocument, question: str
    ) -> list[Citation]:
        """Retrieve the passages most relevant to ``question``.

        Args:
            document: The indexed document to search.
            question: The user's question.

        Returns:
            The selected passages as citations, best first.

        Raises:
            PromptInjectionError: If the question tries to redefine the assistant.
        """
        assert_no_injection(question)

        vectors = await self._llm.embed([question], task=EmbeddingTask.QUERY)
        query_embedding = (
            np.array(vectors[0], dtype=np.float32)
            if vectors
            else np.zeros(self._settings.embedding_dimensions, dtype=np.float32)
        )

        results = document.retriever.search(
            query=question,
            query_embedding=query_embedding,
            top_k=self._settings.retrieval_top_k,
        )
        return [
            Citation(
                label=result.chunk.citation_label,
                quote=_preview(result.chunk.text),
                start=result.chunk.start_offset,
                end=result.chunk.end_offset,
                score=result.score,
            )
            for result in results
        ]

    async def stream_answer(
        self, *, document: StoredDocument, question: str, citations: list[Citation]
    ) -> AsyncIterator[str]:
        """Stream a grounded answer built from ``citations``.

        Args:
            document: The document the citations came from.
            question: The user's question.
            citations: Passages retrieved by :meth:`retrieve_citations`.

        Yields:
            Successive fragments of the answer, with redaction reversed.
        """
        passages = [
            (citation.label, document.text[citation.start : citation.end]) for citation in citations
        ]

        # Redact the passages as a single body so one identifier appearing in
        # two passages maps to one placeholder, then split them apart again on a
        # sentinel that no redaction pattern can match.
        redaction = redact(
            _PASSAGE_SEPARATOR.join(text for _, text in passages),
            enabled=self._settings.redact_pii_before_llm,
        )
        redacted_bodies = redaction.text.split(_PASSAGE_SEPARATOR)
        redacted_passages = [
            (label, body) for (label, _), body in zip(passages, redacted_bodies, strict=False)
        ]

        prompt = build_qa_prompt(question=question, passages=redacted_passages)
        async for fragment in self._llm.generate_stream(
            system_instruction=QA_SYSTEM_INSTRUCTION, prompt=prompt
        ):
            yield redaction.restore(fragment)


def _preview(text: str) -> str:
    """Trim a passage to a readable preview length on a word boundary."""
    if len(text) <= _CITATION_PREVIEW_CHARACTERS:
        return text
    trimmed = text[:_CITATION_PREVIEW_CHARACTERS]
    head, separator, _ = trimmed.rpartition(" ")
    return f"{head if separator else trimmed}…"
