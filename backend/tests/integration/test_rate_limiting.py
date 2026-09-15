"""Model-backed endpoints are capped per client address."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def limited_client(contract_bytes):
    """A client with rate limiting enabled and a deliberately tiny budget."""
    settings = Settings(
        environment="test",
        llm_provider="mock",
        rate_limit_uploads="3/minute",
        max_upload_bytes=1024 * 1024,
    )
    app = create_app(settings)
    app.state.limiter.enabled = True
    app.state.limiter.reset()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client
    app.state.limiter.reset()


class TestRateLimiting:
    async def test_uploads_beyond_the_budget_are_refused(
        self, limited_client, contract_bytes, monkeypatch
    ):
        monkeypatch.setenv("LEXICLEAR_RATE_LIMIT_UPLOADS", "3/minute")
        from app.core.config import get_settings

        get_settings.cache_clear()

        statuses = []
        for _ in range(5):
            response = await limited_client.post(
                "/api/v1/documents",
                files={"file": ("lease.txt", contract_bytes, "text/plain")},
            )
            statuses.append(response.status_code)
        get_settings.cache_clear()

        assert 429 in statuses, f"expected a refusal among {statuses}"
        assert statuses[0] == 201

    async def test_the_refusal_is_a_clean_json_envelope(
        self, limited_client, contract_bytes, monkeypatch
    ):
        monkeypatch.setenv("LEXICLEAR_RATE_LIMIT_UPLOADS", "1/minute")
        from app.core.config import get_settings

        get_settings.cache_clear()
        for _ in range(3):
            response = await limited_client.post(
                "/api/v1/documents",
                files={"file": ("lease.txt", contract_bytes, "text/plain")},
            )
            if response.status_code == 429:
                assert response.json() == {
                    "code": "rate_limited",
                    "message": "Too many requests. Please wait a moment and try again.",
                }
                get_settings.cache_clear()
                return
        get_settings.cache_clear()
        pytest.fail("the limiter never engaged")

    async def test_health_is_not_rate_limited(self, limited_client):
        for _ in range(20):
            assert (await limited_client.get("/api/v1/health")).status_code == 200
