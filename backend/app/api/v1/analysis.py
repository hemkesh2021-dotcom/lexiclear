"""Clause analysis endpoint."""

from fastapi import APIRouter, Request, Response

from app.api.deps import AnalysisDep, StoreDep
from app.core.security import limit_from_settings, limiter
from app.schemas.analysis import DocumentAnalysis
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/documents", tags=["analysis"])


@router.post(
    "/{document_id}/analysis",
    responses={
        404: {"model": ErrorResponse, "description": "The document has expired."},
        429: {"model": ErrorResponse, "description": "Too many analyses from this client."},
        503: {"model": ErrorResponse, "description": "The model is temporarily unavailable."},
    },
    summary="Analyse a document's clauses, obligations and risks",
)
@limiter.limit(limit_from_settings("rate_limit_analysis"))
async def analyse_document(
    request: Request,
    response: Response,
    document_id: str,
    store: StoreDep,
    analysis_service: AnalysisDep,
) -> DocumentAnalysis:
    """Produce a plain-language analysis of an indexed document.

    Every finding is verified against the document text before it is returned;
    findings the model could not ground in a verbatim quotation are discarded
    and counted in ``unverified_finding_count``. The result is cached for the
    lifetime of the document so repeated views cost nothing.
    """
    del request, response  # Required by the rate limiter, unused by the handler.
    document = await store.get(document_id)
    if document.analysis is not None:
        return document.analysis

    result = await analysis_service.analyse(document)
    document.analysis = result
    return result
