"""Documents expire, are capacity-bounded, and never outlive their TTL."""

import time
from unittest.mock import patch

import numpy as np
import pytest

from app.core.errors import DocumentNotFoundError
from app.services.chunking import Chunk
from app.services.store import DocumentStore


def make_chunks(n: int = 2) -> list[Chunk]:
    return [
        Chunk(
            index=i,
            text=f"Clause {i} text body.",
            start_offset=i * 20,
            end_offset=i * 20 + 20,
            heading=f"Clause {i}",
        )
        for i in range(n)
    ]


async def add(store: DocumentStore, name: str = "a.txt"):
    chunks = make_chunks()
    return await store.add(
        filename=name,
        text="Clause 0 text body.Clause 1 text body.",
        chunks=chunks,
        embeddings=np.zeros((len(chunks), 8), dtype=np.float32),
        page_count=1,
        truncated=False,
    )


class TestLifecycle:
    async def test_a_stored_document_is_retrievable(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        stored = await add(store)
        assert (await store.get(stored.document_id)).filename == "a.txt"

    async def test_identifiers_are_unguessable_and_unique(self):
        store = DocumentStore(ttl_seconds=60, max_documents=10)
        ids = {(await add(store)).document_id for _ in range(8)}
        assert len(ids) == 8
        assert all(len(identifier) >= 20 for identifier in ids)

    async def test_an_unknown_identifier_is_rejected(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        with pytest.raises(DocumentNotFoundError):
            await store.get("does-not-exist")

    async def test_deletion_is_immediate(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        stored = await add(store)
        await store.delete(stored.document_id)
        with pytest.raises(DocumentNotFoundError):
            await store.get(stored.document_id)

    async def test_deleting_twice_is_harmless(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        stored = await add(store)
        await store.delete(stored.document_id)
        await store.delete(stored.document_id)


class TestExpiry:
    async def test_a_document_is_unreachable_once_its_ttl_elapses(self):
        store = DocumentStore(ttl_seconds=30, max_documents=5)
        stored = await add(store)
        with (
            patch("app.services.store.time.monotonic", return_value=time.monotonic() + 31),
            pytest.raises(DocumentNotFoundError, match="no longer available"),
        ):
            await store.get(stored.document_id)

    async def test_expired_documents_are_evicted_from_memory(self):
        store = DocumentStore(ttl_seconds=30, max_documents=5)
        await add(store)
        assert await store.size() == 1
        with patch("app.services.store.time.monotonic", return_value=time.monotonic() + 31):
            assert await store.size() == 0

    async def test_a_document_survives_within_its_ttl(self):
        store = DocumentStore(ttl_seconds=300, max_documents=5)
        stored = await add(store)
        with patch("app.services.store.time.monotonic", return_value=time.monotonic() + 100):
            assert await store.get(stored.document_id) is not None


class TestCapacity:
    async def test_the_oldest_document_is_evicted_when_full(self):
        store = DocumentStore(ttl_seconds=600, max_documents=3)
        first = await add(store, "first.txt")
        for name in ("b.txt", "c.txt", "d.txt"):
            await add(store, name)
        assert await store.size() == 3
        with pytest.raises(DocumentNotFoundError):
            await store.get(first.document_id)

    async def test_reading_a_document_protects_it_from_eviction(self):
        store = DocumentStore(ttl_seconds=600, max_documents=3)
        first = await add(store, "first.txt")
        await add(store, "b.txt")
        await store.get(first.document_id)  # refreshes its position
        await add(store, "c.txt")
        await add(store, "d.txt")
        assert (await store.get(first.document_id)).filename == "first.txt"


class TestContentAddressing:
    async def test_identical_content_is_found_by_its_digest(self):
        from app.services.store import content_digest

        store = DocumentStore(ttl_seconds=60, max_documents=5)
        document = await add(store)
        assert await store.find_by_content(content_digest(document.text)) is document

    async def test_unknown_content_is_not_found(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        await add(store)
        assert await store.find_by_content("0" * 64) is None

    async def test_expired_content_is_never_reused(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        document = await add(store)
        with patch("app.services.store.time.monotonic", return_value=time.monotonic() + 61):
            assert await store.find_by_content(document.content_hash) is None

    async def test_a_document_needs_embeddings_or_a_retriever(self):
        store = DocumentStore(ttl_seconds=60, max_documents=5)
        with pytest.raises(ValueError, match="embeddings or a retriever"):
            await store.add(filename="a.txt", text="x", chunks=[], page_count=1, truncated=False)
