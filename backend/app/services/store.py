"""Ephemeral, in-memory storage for uploaded documents.

LexiClear never writes an uploaded document to disk and never persists it to a
database.  A document lives in process memory for a bounded time-to-live and is
evicted automatically, which means an abandoned session leaves nothing behind
and a container restart wipes every trace.  For a tool handling potentially
privileged legal material, not storing the data is the strongest control
available; see ``SECURITY.md`` for the trade-offs this implies.

The store is a bounded LRU with TTL, guarded by an :class:`asyncio.Lock` so that
concurrent requests cannot corrupt the ordering.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from app.core.errors import CapacityError, DocumentNotFoundError
from app.schemas.analysis import DocumentAnalysis
from app.services.chunking import Chunk
from app.services.retrieval import HybridRetriever

_DOCUMENT_ID_BYTES = 16


@dataclass(slots=True)
class StoredDocument:
    """An indexed document held in memory for the length of its TTL."""

    document_id: str
    filename: str
    text: str
    chunks: list[Chunk]
    retriever: HybridRetriever
    page_count: int
    truncated: bool
    created_at: float
    #: Cached analysis, computed lazily on first request and reused for the
    #: document's lifetime so revisiting the results costs no model call.
    analysis: DocumentAnalysis | None = field(default=None)

    @property
    def character_count(self) -> int:
        """Number of characters retained from the source document."""
        return len(self.text)


class DocumentStore:
    """A bounded, TTL-expiring, in-memory document store."""

    def __init__(self, *, ttl_seconds: int, max_documents: int) -> None:
        """Configure retention and capacity limits.

        Args:
            ttl_seconds: Seconds a document remains retrievable after upload.
            max_documents: Hard ceiling on concurrently held documents.
        """
        self._ttl_seconds = ttl_seconds
        self._max_documents = max_documents
        self._documents: OrderedDict[str, StoredDocument] = OrderedDict()
        self._lock = asyncio.Lock()

    async def add(
        self,
        *,
        filename: str,
        text: str,
        chunks: list[Chunk],
        embeddings: npt.NDArray[np.float32],
        page_count: int,
        truncated: bool,
    ) -> StoredDocument:
        """Index and store a document, returning its handle.

        Args:
            filename: Sanitised display name.
            text: The normalised document text.
            chunks: The document's chunks.
            embeddings: Embedding matrix aligned with ``chunks``.
            page_count: Source page count, where the format reports one.
            truncated: Whether the text was truncated at the character ceiling.

        Returns:
            The stored document, including its generated identifier.

        Raises:
            CapacityError: If the store is full of unexpired documents.
        """
        document = StoredDocument(
            document_id=secrets.token_urlsafe(_DOCUMENT_ID_BYTES),
            filename=filename,
            text=text,
            chunks=chunks,
            retriever=HybridRetriever(chunks, embeddings),
            page_count=page_count,
            truncated=truncated,
            created_at=time.monotonic(),
        )

        async with self._lock:
            self._evict_expired()
            if len(self._documents) >= self._max_documents:
                self._documents.popitem(last=False)
            if len(self._documents) >= self._max_documents:  # pragma: no cover - defensive
                raise CapacityError("The service is at capacity. Please try again shortly.")
            self._documents[document.document_id] = document

        return document

    async def get(self, document_id: str) -> StoredDocument:
        """Retrieve a document by identifier, refreshing its LRU position.

        Args:
            document_id: The identifier returned at upload time.

        Returns:
            The stored document.

        Raises:
            DocumentNotFoundError: If the document has expired or never existed.
        """
        async with self._lock:
            self._evict_expired()
            document = self._documents.get(document_id)
            if document is None:
                raise DocumentNotFoundError(
                    "This document is no longer available. Documents are kept for a "
                    "limited time and are never stored permanently. Please upload it again."
                )
            self._documents.move_to_end(document_id)
            return document

    async def delete(self, document_id: str) -> None:
        """Remove a document immediately, if present."""
        async with self._lock:
            self._documents.pop(document_id, None)

    async def size(self) -> int:
        """Return the number of unexpired documents currently held."""
        async with self._lock:
            self._evict_expired()
            return len(self._documents)

    def _evict_expired(self) -> None:
        """Drop every document whose TTL has elapsed. Caller must hold the lock."""
        cutoff = time.monotonic() - self._ttl_seconds
        expired = [
            document_id
            for document_id, document in self._documents.items()
            if document.created_at < cutoff
        ]
        for document_id in expired:
            del self._documents[document_id]
