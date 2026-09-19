"""Ephemeral, in-memory storage for uploaded documents.

LexiClear never writes an uploaded document to disk and never persists it to a
database.  A document lives in process memory for a bounded time-to-live and is
evicted automatically, which means an abandoned session leaves nothing behind
and a container restart wipes every trace.  For a tool handling potentially
privileged legal material, not storing the data is the strongest control
available; see ``SECURITY.md`` for the trade-offs this implies.

The store is a bounded LRU with TTL, guarded by an :class:`asyncio.Lock` so that
concurrent requests cannot corrupt the ordering.

Documents are also *content-addressed*: each carries a SHA-256 digest of its
normalised text. Re-uploading a document that is still held (which the front
end does automatically when a session expires, and which users do when they
refresh) reuses the existing chunks, embeddings and analysis instead of paying
for them again. Reuse happens only while an identical document is still held,
and every upload still receives its own unguessable identifier, so one client can
never read or delete another client's handle.
"""

from __future__ import annotations

import asyncio
import hashlib
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
    #: SHA-256 of the normalised text; the key for reusing expensive work.
    content_hash: str = ""
    #: Cached analysis, computed lazily on first request and reused for the
    #: document's lifetime so revisiting the results costs no model call.
    analysis: DocumentAnalysis | None = field(default=None)
    #: Serialises analysis so concurrent requests for one document share a
    #: single model call instead of each starting their own.
    analysis_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def character_count(self) -> int:
        """Number of characters retained from the source document."""
        return len(self.text)


def rebind_analysis(analysis: DocumentAnalysis, document_id: str) -> DocumentAnalysis:
    """Return a copy of ``analysis`` addressed to ``document_id``.

    Reused work must never carry the identifier of the document it came from:
    that handle belongs to another client and would let them be tracked or
    their document deleted.
    """
    return analysis.model_copy(update={"document_id": document_id})


def content_digest(text: str) -> str:
    """Return the SHA-256 hex digest that identifies a document's content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        embeddings: npt.NDArray[np.float32] | None = None,
        page_count: int,
        truncated: bool,
        retriever: HybridRetriever | None = None,
        analysis: DocumentAnalysis | None = None,
    ) -> StoredDocument:
        """Index and store a document, returning its handle.

        Args:
            filename: Sanitised display name.
            text: The normalised document text.
            chunks: The document's chunks.
            embeddings: Embedding matrix aligned with ``chunks``. Required
                unless an existing ``retriever`` is supplied for reuse.
            page_count: Source page count, where the format reports one.
            truncated: Whether the text was truncated at the character ceiling.
            retriever: An already-built index over identical content, reused
                so the embeddings are neither recomputed nor re-indexed.
            analysis: An analysis of identical content, reused as-is.

        Returns:
            The stored document, including its generated identifier.

        Raises:
            CapacityError: If the store is full of unexpired documents.
            ValueError: If neither ``embeddings`` nor ``retriever`` is given.
        """
        if retriever is None:
            if embeddings is None:
                raise ValueError("Either embeddings or a retriever must be supplied.")
            retriever = HybridRetriever(chunks, embeddings)
        document_id = secrets.token_urlsafe(_DOCUMENT_ID_BYTES)
        document = StoredDocument(
            document_id=document_id,
            filename=filename,
            text=text,
            chunks=chunks,
            retriever=retriever,
            page_count=page_count,
            truncated=truncated,
            created_at=time.monotonic(),
            content_hash=content_digest(text),
            analysis=rebind_analysis(analysis, document_id) if analysis else None,
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

    async def find_by_content(self, content_hash: str) -> StoredDocument | None:
        """Return a live document with identical content, preferring one already analysed.

        Args:
            content_hash: The :func:`content_digest` of the normalised text.

        Returns:
            A matching unexpired document, or ``None`` when there is none.
        """
        async with self._lock:
            self._evict_expired()
            matches = [
                document
                for document in self._documents.values()
                if document.content_hash == content_hash
            ]
        for document in reversed(matches):
            if document.analysis is not None:
                return document
        return matches[-1] if matches else None

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
