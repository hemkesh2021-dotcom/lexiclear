"""Upload validation based on content, not on the client's claims.

A browser-supplied filename and ``Content-Type`` are attacker-controlled, so
both are treated as hints only.  The authoritative check is the file's magic
number, which is matched against a small allow-list of formats the extraction
layer can actually parse.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import FileTooLargeError, UnsupportedFileTypeError


class DocumentFormat(StrEnum):
    """A document format LexiClear is able to extract text from."""

    PDF = "pdf"
    DOCX = "docx"
    TEXT = "txt"


#: Magic-number prefixes for the binary formats we accept.
_MAGIC_PREFIXES: tuple[tuple[bytes, DocumentFormat], ...] = (
    (b"%PDF-", DocumentFormat.PDF),
    (b"PK\x03\x04", DocumentFormat.DOCX),
)

#: Bytes that never appear in a well-formed UTF-8 plain-text document.
_CONTROL_BYTES = frozenset(range(0, 9)) | frozenset(range(14, 32)) - {27}

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]")
_MAX_FILENAME_LENGTH = 120


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """An upload that has passed every structural check."""

    content: bytes
    document_format: DocumentFormat
    safe_filename: str
    size_bytes: int


def sanitise_filename(raw_name: str | None) -> str:
    """Reduce a client-supplied filename to a safe display label.

    Path separators, control characters and Unicode look-alikes are stripped so
    the value can never be used for traversal and is safe to render verbatim.

    Args:
        raw_name: The filename as supplied by the client, possibly ``None``.

    Returns:
        A short, printable, separator-free filename.
    """
    if not raw_name:
        return "document"
    normalised = unicodedata.normalize("NFKC", raw_name)
    basename = normalised.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", basename).strip(". ")
    return cleaned[:_MAX_FILENAME_LENGTH] or "document"


def _looks_like_utf8_text(content: bytes) -> bool:
    """Return ``True`` when ``content`` decodes as UTF-8 without control bytes."""
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(byte in _CONTROL_BYTES for byte in content[:4096])


def detect_format(content: bytes) -> DocumentFormat:
    """Identify the document format from its leading bytes.

    Args:
        content: The complete uploaded payload.

    Returns:
        The detected :class:`DocumentFormat`.

    Raises:
        UnsupportedFileTypeError: If the payload matches no supported format.
    """
    for prefix, document_format in _MAGIC_PREFIXES:
        if content.startswith(prefix):
            return document_format
    if _looks_like_utf8_text(content):
        return DocumentFormat.TEXT
    raise UnsupportedFileTypeError(
        "Only PDF, DOCX and plain-text documents can be analysed.",
        detail="The uploaded file's contents did not match a supported format.",
    )


def validate_upload(
    content: bytes,
    *,
    raw_filename: str | None,
    max_bytes: int,
) -> ValidatedUpload:
    """Validate an upload's size and true format.

    Args:
        content: The complete uploaded payload.
        raw_filename: The client-supplied filename, used only for display.
        max_bytes: The inclusive upper bound on payload size.

    Returns:
        A :class:`ValidatedUpload` describing the accepted file.

    Raises:
        FileTooLargeError: If the payload is empty or exceeds ``max_bytes``.
        UnsupportedFileTypeError: If the payload's format is not supported.
    """
    size = len(content)
    if size == 0:
        raise FileTooLargeError("The uploaded file is empty.")
    if size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise FileTooLargeError(f"Documents must be smaller than {limit_mb:.0f} MB.")

    return ValidatedUpload(
        content=content,
        document_format=detect_format(content),
        safe_filename=sanitise_filename(raw_filename),
        size_bytes=size,
    )
