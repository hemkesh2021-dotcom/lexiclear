"""Shared fixtures.

Every test runs against a real application instance with the deterministic mock
model provider substituted for Gemini. No test needs an API key, none makes a
network call, and the full request path - middleware, validation, services,
serialisation - is exercised rather than mocked out.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.llm.mock import MockLlmProvider
from app.main import create_app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def settings() -> Settings:
    """Test settings: mock provider, short TTL, redaction on."""
    return Settings(
        environment="test",
        llm_provider="mock",
        document_ttl_seconds=60,
        max_documents_in_memory=5,
        max_upload_bytes=1024 * 1024,
        redact_pii_before_llm=True,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An application instance with rate limiting disabled.

    Rate limiting is exercised by its own test, which re-enables it; leaving it
    on globally would make unrelated tests order-dependent and flaky.
    """
    application = create_app(settings)
    application.state.limiter.enabled = False
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the application, with lifespan run."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client,
    ):
        yield http_client


@pytest.fixture
def mock_llm() -> MockLlmProvider:
    """A standalone mock provider for unit tests of the service layer."""
    return MockLlmProvider(dimensions=768)


@pytest.fixture
def contract_text() -> str:
    """The sample rental agreement used across the suite."""
    return (SAMPLES / "sample-rental-agreement.txt").read_text(encoding="utf-8")


@pytest.fixture
def contract_bytes(contract_text: str) -> bytes:
    """The sample rental agreement as an uploadable payload."""
    return contract_text.encode("utf-8")


@pytest.fixture
def minimal_pdf() -> bytes:
    """A tiny but structurally valid PDF containing extractable text."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def minimal_docx() -> bytes:
    """A DOCX file containing a single clause of real text."""
    import docx

    document = docx.Document()
    document.add_paragraph(
        "1. TERMINATION. Either party may terminate this agreement by giving "
        "thirty (30) days written notice to the other party."
    )
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def zip_bomb_lookalike() -> bytes:
    """A ZIP file that is not a DOCX, used to prove format checks go deeper."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a word document")
    return buffer.getvalue()
