"""Upload-to-indexed-document orchestration.

One entry point ties together validation, extraction, chunking, embedding and
storage so the API layer stays a thin adapter with no pipeline logic in it.
"""

from __future__ import annotations

import numpy as np

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.base import EmbeddingTask, LlmProvider
from app.security.file_validation import validate_upload
from app.security.prompt_guard import neutralise_delimiters
from app.services.chunking import chunk_document
from app.services.extraction import extract_document
from app.services.store import DocumentStore, StoredDocument

_logger = get_logger(__name__)


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
        vectors = await self._llm.embed(
            [chunk.text for chunk in chunks], task=EmbeddingTask.DOCUMENT
        )
        embeddings = (
            np.array(vectors, dtype=np.float32)
            if vectors
            else np.zeros((0, self._settings.embedding_dimensions), dtype=np.float32)
        )

        document = await self._store.add(
            filename=upload.safe_filename,
            text=safe_text,
            chunks=chunks,
            embeddings=embeddings,
            page_count=extracted.page_count,
            truncated=extracted.truncated,
        )

        _logger.info(
            "document_ingested",
            document_id=document.document_id,
            document_format=upload.document_format.value,
            size_bytes=upload.size_bytes,
            chunk_count=len(chunks),
            truncated=extracted.truncated,
        )
        return document
