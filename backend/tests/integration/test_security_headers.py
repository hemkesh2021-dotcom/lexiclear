"""Transport-level hardening applied by the middleware stack."""

import pytest

from app.core.config import Settings
from app.core.security import CONTENT_SECURITY_POLICY
from app.main import create_app


class TestSecurityHeaders:
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Opener-Policy", "same-origin"),
            ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
        ],
    )
    async def test_headers_are_present_on_every_response(self, client, header, expected):
        response = await client.get("/api/v1/health")
        assert response.headers[header] == expected

    async def test_the_policy_forbids_framing_and_inline_script(self):
        assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
        assert "script-src 'self'" in CONTENT_SECURITY_POLICY
        assert "unsafe-eval" not in CONTENT_SECURITY_POLICY
        assert "unsafe-inline" not in CONTENT_SECURITY_POLICY.split("style-src")[0]

    async def test_headers_are_present_on_error_responses_too(self, client):
        response = await client.get("/api/v1/documents/nope")
        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    async def test_hsts_is_advertised_only_in_production(self, client):
        assert "Strict-Transport-Security" not in (await client.get("/api/v1/health")).headers

        from httpx import ASGITransport, AsyncClient

        production = create_app(Settings(environment="production", llm_provider="mock"))
        production.state.limiter.enabled = False
        async with (
            production.router.lifespan_context(production),
            AsyncClient(transport=ASGITransport(app=production), base_url="http://test") as http,
        ):
            response = await http.get("/api/v1/health")
            assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


class TestErrorDisclosure:
    async def test_an_unexpected_failure_reveals_nothing_internal(self, app):
        from fastapi import APIRouter
        from httpx import ASGITransport, AsyncClient

        router = APIRouter()

        @router.get("/api/v1/boom")
        async def boom() -> None:
            raise RuntimeError("secret connection string postgres://user:pw@host/db")

        app.include_router(router)

        # `raise_app_exceptions=False` makes the transport behave like a real
        # ASGI server, which serves the handler's response and logs the
        # exception rather than propagating it to the client.
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as http,
        ):
            response = await http.get("/api/v1/boom")

            assert response.status_code == 500
            body = response.text
            assert "postgres://" not in body
            assert "RuntimeError" not in body
            assert "Traceback" not in body
            assert response.json()["code"] == "internal_error"


class TestOpenApi:
    async def test_the_schema_is_published_and_documents_every_route(self, client):
        schema = (await client.get("/api/openapi.json")).json()
        paths = schema["paths"]
        assert "/api/v1/documents" in paths
        assert "/api/v1/documents/{document_id}/analysis" in paths
        assert "/api/v1/documents/{document_id}/questions" in paths

    async def test_no_secret_leaks_into_the_published_schema(self, client):
        rendered = (await client.get("/api/openapi.json")).text.lower()
        assert "api_key" not in rendered
        assert "google_api_key" not in rendered
