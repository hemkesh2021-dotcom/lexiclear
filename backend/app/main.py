"""Application factory and process entry point.

The factory keeps construction explicit and side-effect free at import time,
which is what lets the test suite build isolated applications with substituted
settings and a mock model provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.types import Scope

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import LexiClearError
from app.core.logging import configure_logging, get_logger
from app.core.security import SecurityHeadersMiddleware, limiter
from app.llm.factory import build_llm_provider
from app.schemas.common import ErrorResponse
from app.services.clause_analysis import ClauseAnalysisService
from app.services.ingestion import IngestionService
from app.services.qa_service import QuestionAnsweringService
from app.services.store import DocumentStore

_logger = get_logger(__name__)

#: Directory the built single-page application is copied into by the Docker
#: build. Absent during local backend-only development, which is not an error.
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"

DESCRIPTION = """
LexiClear helps people without legal training understand documents they have
been asked to sign or comply with.

Upload a contract, policy or notice and the service returns a plain-language
summary, the clauses that deserve attention, the obligations they create, and
the questions worth putting to a lawyer. Questions about the document are
answered only from passages retrieved from that document, with citations.

**LexiClear provides information, not legal advice.** Documents are held in
memory for a limited time and are never written to disk.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct long-lived collaborators on start-up and release them on exit."""
    settings: Settings = app.state.settings
    llm_provider = build_llm_provider(settings)
    store = DocumentStore(
        ttl_seconds=settings.document_ttl_seconds,
        max_documents=settings.max_documents_in_memory,
    )

    app.state.llm_provider = llm_provider
    app.state.document_store = store
    app.state.ingestion_service = IngestionService(settings=settings, llm=llm_provider, store=store)
    app.state.analysis_service = ClauseAnalysisService(
        llm=llm_provider, redact_pii=settings.redact_pii_before_llm
    )
    app.state.qa_service = QuestionAnsweringService(settings=settings, llm=llm_provider)
    app.state.uploads_served = 0

    _logger.info(
        "application_started",
        environment=settings.environment,
        llm_provider=llm_provider.name,
    )
    yield
    _logger.info("application_stopping", uploads_served=app.state.uploads_served)


def _register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that keep internal details out of error responses."""

    @app.exception_handler(LexiClearError)
    async def _handle_known(request: Request, exc: LexiClearError) -> JSONResponse:
        _logger.info("handled_error", code=exc.code, path=request.url.path, detail=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                code="invalid_request",
                message="The request could not be processed. Please check the values you sent.",
            ).model_dump(),
        )

    @app.exception_handler(RateLimitExceeded)
    async def _handle_rate_limit(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                code="rate_limited",
                message="Too many requests. Please wait a moment and try again.",
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Logged with the traceback, returned without it: an unexpected failure
        # must never leak internals to an unauthenticated caller.
        _logger.error("unhandled_error", path=request.url.path, error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="internal_error",
                message="Something went wrong on our side. Please try again.",
            ).model_dump(),
        )


#: Vite fingerprints every file under ``/assets`` with a content hash, so a
#: given URL can never change: browsers and CDNs may keep it for a year.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
#: The HTML shell names the current asset hashes, so it must be revalidated.
REVALIDATE_CACHE = "no-cache"


class ImmutableStaticFiles(StaticFiles):
    """Static files served with a long-lived, immutable cache policy."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve the file and mark successful responses as immutable."""
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE_CACHE
        return response


def _mount_single_page_app(app: FastAPI, settings: Settings) -> None:
    """Serve the built front end, falling back to ``index.html`` for routes."""
    if not STATIC_DIRECTORY.is_dir():
        return

    api_prefix = settings.api_v1_prefix.rstrip("/")

    app.mount(
        "/assets",
        ImmutableStaticFiles(directory=STATIC_DIRECTORY / "assets", check_dir=False),
        name="assets",
    )
    index_file = STATIC_DIRECTORY / "index.html"

    # HEAD as well as GET: browsers, link checkers and uptime monitors issue
    # HEAD against the document root, and a 405 there reads as an outage.
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        """Return a static asset when it exists, otherwise the SPA shell.

        A path under the API prefix never falls through to the shell. Without
        that guard a misspelled endpoint would answer ``200 text/html``, which
        an API client reads as success and a monitor reads as healthy.
        """
        if f"/{full_path}".startswith(f"{api_prefix}/"):
            return JSONResponse(
                status_code=404,
                content=ErrorResponse(
                    code="not_found", message="This endpoint does not exist."
                ).model_dump(),
            )

        candidate = (STATIC_DIRECTORY / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(STATIC_DIRECTORY.resolve())
        ):
            return FileResponse(candidate, headers={"Cache-Control": REVALIDATE_CACHE})
        return FileResponse(index_file, headers={"Cache-Control": REVALIDATE_CACHE})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully configured application instance.

    Args:
        settings: Optional settings override, used by the test suite.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    configure_logging(resolved)

    app = FastAPI(
        title=f"{resolved.app_name} API",
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = resolved

    app.state.limiter = limiter

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=resolved.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    _register_exception_handlers(app)
    app.include_router(api_router, prefix=resolved.api_v1_prefix)
    _mount_single_page_app(app, resolved)
    return app


app = create_app()
