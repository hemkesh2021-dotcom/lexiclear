"""Upload-to-indexed-document orchestration.

One entry point ties together validation, extraction, chunking, embedding and
storage so the API layer stays a thin adapter with no pipeline logic in it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.base import EmbeddingTask, LlmProvider
from app.security.file_validation import validate_upload
from app.security.prompt_guard import neutralise_delimiters
from app.services.chunking import Chunk, chunk_document
from app.services.extraction import extract_document
from app.services.store import DocumentStore, StoredDocument, content_digest

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Prepared:
    """The CPU-bound half of ingestion: validated, extracted and chunked text."""

    safe_filename: str
    document_format: str
    size_bytes: int
    text: str
    chunks: list[Chunk]
    page_count: int
    truncated: bool


class IngestionService:
    """Turns a raw upload into an indexed, queryable document."""

    def __init__(self, *, settings: Settings, llm: LlmProvider, store: DocumentStore) -> None:
        """Wire the pipeline's collaborators."""
        self._settings = settings
        self._llm = llm
        self._store = store

    async def ingest(self, *, content: bytes, filename: str | None) -> StoredDocument:
        """Validate, extract, chunk, embed and store an uploaded document.

        Args:
            content: The raw uploaded bytes.
            filename: The client-supplied filename, used only for display.

        Returns:
            The indexed document.
        """
        # Parsing a PDF or DOCX and chunking it is synchronous, CPU-bound work.
        # Running it in a worker thread keeps the event loop free to serve other
        # requests (including streaming answers) while a large upload is parsed.
        prepared = await asyncio.to_thread(self._prepare, content, filename)

        # An identical document that is still held already has embeddings, an
        # index and possibly an analysis: reuse them rather than paying again.
        existing = await self._store.find_by_content(content_digest(prepared.text))
        if existing is not None:
            document = await self._store.add(
                filename=prepared.safe_filename,
                text=existing.text,
                chunks=existing.chunks,
                retriever=existing.retriever,
                analysis=existing.analysis,
                page_count=prepared.page_count,
                truncated=prepared.truncated,
            )
        else:
            vectors = await self._llm.embed(
                [chunk.text for chunk in prepared.chunks], task=EmbeddingTask.DOCUMENT
            )
            embeddings = (
                np.array(vectors, dtype=np.float32)
                if vectors
                else np.zeros((0, self._settings.embedding_dimensions), dtype=np.float32)
            )
            document = await self._store.add(
                filename=prepared.safe_filename,
                text=prepared.text,
                chunks=prepared.chunks,
                embeddings=embeddings,
                page_count=prepared.page_count,
                truncated=prepared.truncated,
            )

        _logger.info(
            "document_ingested",
            document_id=document.document_id,
            document_format=prepared.document_format,
            size_bytes=prepared.size_bytes,
            chunk_count=len(prepared.chunks),
            truncated=prepared.truncated,
            reused=existing is not None,
        )
        return document

    def _prepare(self, content: bytes, filename: str | None) -> _Prepared:
        """Validate, extract and chunk an upload. Synchronous; run off the event loop."""
        upload = validate_upload(
            content,
            raw_filename=filename,
            max_bytes=self._settings.max_upload_bytes,
        )
        extracted = extract_document(upload, max_characters=self._settings.max_document_characters)

        # Forged prompt delimiters are stripped once, at the boundary, so every
        # downstream consumer works with text that cannot break out of its block.
        safe_text = neutralise_delimiters(extracted.text)

        chunks = chunk_document(
            safe_text,
            target_characters=self._settings.chunk_target_characters,
            overlap_characters=self._settings.chunk_overlap_characters,
        )
        return _Prepared(
            safe_filename=upload.safe_filename,
            document_format=upload.document_format.value,
            size_bytes=upload.size_bytes,
            text=safe_text,
            chunks=chunks,
            page_count=extracted.page_count,
            truncated=extracted.truncated,
        )
