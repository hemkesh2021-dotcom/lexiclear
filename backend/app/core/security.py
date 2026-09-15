"""HTTP-level security hardening.

Two concerns live here:

* :class:`SecurityHeadersMiddleware` attaches the response headers that defend
  the single-page application against clickjacking, MIME sniffing, referrer
  leakage and injected third-party scripts.
* :func:`build_rate_limiter` produces the shared SlowAPI limiter used to cap
  expensive, model-backed endpoints per client address.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import get_settings

#: Content-Security-Policy for the bundled SPA.  ``'self'`` only: no CDN, no
#: inline script, no remote font.  ``style-src`` permits inline styles because
#: the bundler injects a single critical-CSS block at build time.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

STATIC_SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardened security headers to every response."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool) -> None:
        """Store whether HSTS should be advertised (production over TLS only)."""
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Delegate to the route handler and decorate the outgoing response."""
        response = await call_next(request)
        for header, value in STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


#: Per-client-address limiter shared by every router.  Declared at module
#: level because SlowAPI applies limits through decorators, which are evaluated
#: at import time.  The limits themselves are resolved lazily from settings by
#: :func:`limit_from_settings`, so configuration still drives the values.
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)


def limit_from_settings(attribute: str) -> Callable[[], str]:
    """Return a callable resolving a named rate limit from current settings.

    Args:
        attribute: Name of the ``Settings`` field holding the limit expression,
            for example ``"rate_limit_uploads"``.

    Returns:
        A zero-argument callable SlowAPI evaluates per request.

    Note:
        SlowAPI evaluates the callable without the request, so this reads the
        process-wide settings rather than the instance's. The two differ only
        under test, where the limiter is disabled outright.
    """

    def _resolve() -> str:
        value: str = getattr(get_settings(), attribute)
        return value

    return _resolve
