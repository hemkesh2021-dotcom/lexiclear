"""Typed application errors and their HTTP representation.

Every failure the client can legitimately encounter is modelled as a
:class:`LexiClearError` subclass carrying a stable machine-readable ``code``.
Unexpected exceptions are deliberately *not* echoed back to the caller, so that
stack traces and internal identifiers never leak through the API surface.
"""

from __future__ import annotations

from http import HTTPStatus


class LexiClearError(Exception):
    """Base class for all errors that are safe to surface to API clients."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        """Store the client-safe message and optional supporting detail."""
        super().__init__(message)
        self.message = message
        self.detail = detail


class DocumentNotFoundError(LexiClearError):
    """The requested document has expired or never existed."""

    status_code = HTTPStatus.NOT_FOUND
    code = "document_not_found"


class UnsupportedFileTypeError(LexiClearError):
    """The uploaded file is not a supported legal-document format."""

    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_file_type"


class FileTooLargeError(LexiClearError):
    """The uploaded file exceeds the configured size ceiling."""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "file_too_large"


class DocumentExtractionError(LexiClearError):
    """The file could be read but contained no usable text."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "extraction_failed"


class PromptInjectionError(LexiClearError):
    """The request was rejected because it tried to override system behaviour."""

    status_code = HTTPStatus.BAD_REQUEST
    code = "prompt_injection_detected"


class LlmUnavailableError(LexiClearError):
    """The upstream model could not be reached or returned an unusable reply."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "llm_unavailable"


class CapacityError(LexiClearError):
    """The in-memory document store is full."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "capacity_exceeded"
