"""Document upload, metadata and explicit deletion."""

from typing import Annotated

from fastapi import APIRouter, File, Request, Response, UploadFile, status

from app.api.deps import IngestionDep, SettingsDep, StoreDep
from app.core.errors import FileTooLargeError
from app.core.security import limit_from_settings, limiter
from app.schemas.common import ErrorResponse
from app.schemas.document import DocumentSummary
from app.services.store import StoredDocument

router = APIRouter(prefix="/documents", tags=["documents"])

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    413: {"model": ErrorResponse, "description": "The file exceeds the size limit."},
    415: {"model": ErrorResponse, "description": "The file format is not supported."},
    422: {"model": ErrorResponse, "description": "No readable text could be extracted."},
    429: {"model": ErrorResponse, "description": "Too many uploads from this client."},
}


def _to_summary(document: StoredDocument, *, ttl_seconds: int) -> DocumentSummary:
    """Project a stored document onto its public metadata."""
    return DocumentSummary(
        document_id=document.document_id,
        filename=document.filename,
        character_count=document.character_count,
        page_count=document.page_count,
        chunk_count=len(document.chunks),
        truncated=document.truncated,
        expires_in_seconds=ttl_seconds,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    summary="Upload and index a legal document",
)
@limiter.limit(limit_from_settings("rate_limit_uploads"))
async def upload_document(
    request: Request,
    response: Response,
    settings: SettingsDep,
    ingestion: IngestionDep,
    file: Annotated[UploadFile, File(description="A PDF, DOCX or plain-text document.")],
) -> DocumentSummary:
    """Validate, extract, index and store an uploaded document.

    The document is held in memory only and is deleted automatically once its
    time-to-live elapses. It is never written to disk.
    """
    del response  # SlowAPI writes rate-limit headers onto it.

    # Read with a one-byte overshoot so an oversized upload is rejected without
    # ever materialising more than the limit plus one byte in memory.
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        raise FileTooLargeError(f"Documents must be smaller than {limit_mb:.0f} MB.")

    document = await ingestion.ingest(content=content, filename=file.filename)
    request.app.state.uploads_served += 1
    return _to_summary(document, ttl_seconds=settings.document_ttl_seconds)


@router.get(
    "/{document_id}",
    responses={404: {"model": ErrorResponse, "description": "The document has expired."}},
    summary="Fetch document metadata",
)
async def get_document(document_id: str, settings: SettingsDep, store: StoreDep) -> DocumentSummary:
    """Return metadata for a previously uploaded document."""
    document = await store.get(document_id)
    return _to_summary(document, ttl_seconds=settings.document_ttl_seconds)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document immediately",
)
async def delete_document(document_id: str, store: StoreDep) -> None:
    """Erase a document from memory before its time-to-live elapses."""
    await store.delete(document_id)
