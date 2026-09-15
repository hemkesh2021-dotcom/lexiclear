"""Single-origin hosting of the built web client.

In the container the compiled front end is copied to ``app/static`` and served
by the same process as the API, which is what keeps the Content-Security-Policy
at ``default-src 'self'``. These tests build that layout in a temporary
directory, so the behaviour is verified without needing a Docker build.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def built_app(tmp_path, monkeypatch):
    """An application with a stand-in built front end mounted."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>LexiClear</title>")
    (static / "assets" / "index.css").write_text(".panel{}")
    (tmp_path / "secret.txt").write_text("this file is outside the static root")

    monkeypatch.setattr("app.main.STATIC_DIRECTORY", static)
    app = create_app(Settings(environment="test", llm_provider="mock"))
    app.state.limiter.enabled = False
    return app


@pytest.fixture
async def built_client(built_app):
    async with (
        built_app.router.lifespan_context(built_app),
        AsyncClient(transport=ASGITransport(app=built_app), base_url="http://test") as client,
    ):
        yield client


class TestStaticHosting:
    async def test_the_shell_is_served_at_the_root(self, built_client):
        response = await built_client.get("/")
        assert response.status_code == 200
        assert "LexiClear" in response.text

    async def test_head_requests_succeed(self, built_client):
        # Uptime monitors and link checkers issue HEAD; a 405 there reads as an
        # outage even though the service is perfectly healthy.
        assert (await built_client.head("/")).status_code == 200

    async def test_a_built_asset_is_served(self, built_client):
        response = await built_client.get("/assets/index.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    async def test_an_unknown_route_falls_back_to_the_shell(self, built_client):
        response = await built_client.get("/results/doc-123")
        assert response.status_code == 200
        assert "LexiClear" in response.text

    @pytest.mark.parametrize(
        "path", ["/../secret.txt", "/..%2Fsecret.txt", "/assets/../../secret.txt"]
    )
    async def test_traversal_never_escapes_the_static_root(self, built_client, path):
        response = await built_client.get(path)
        assert "outside the static root" not in response.text

    async def test_the_api_still_takes_precedence_over_the_fallback(self, built_client):
        assert (await built_client.get("/api/v1/health")).json()["status"] == "ok"

    async def test_security_headers_apply_to_static_responses(self, built_client):
        response = await built_client.get("/")
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    async def test_an_unknown_api_path_is_a_json_404_not_the_shell(self, built_client):
        # Without an explicit guard the catch-all route would answer
        # `200 text/html`, which an API client reads as success and an uptime
        # monitor reads as healthy.
        response = await built_client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["code"] == "not_found"

    async def test_a_path_merely_starting_with_api_still_reaches_the_shell(self, built_client):
        # `/apiary` is a client-side route, not a mistyped endpoint.
        response = await built_client.get("/apiary")
        assert response.status_code == 200
        assert "LexiClear" in response.text
