"""Grounded question answering, delivered as a server-sent event stream.

The endpoint emits three event types:

``citations``
    Sent once, before generation begins, so the interface can render the
    passages the answer will be built from while the prose is still arriving.
``token``
    A fragment of the answer text.
``done`` / ``error``
    Terminal events carrying the disclaimer or a client-safe failure message.

Server-sent events are used rather than a WebSocket because the exchange is
one-directional, survives proxies without special configuration, and reconnects
on its own in every browser that supports ``EventSource``.
"""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import QaDep, StoreDep
from app.core.errors import LexiClearError
from app.core.logging import get_logger
from app.core.security import limit_from_settings, limiter
from app.schemas.qa import QuestionRequest
from app.services.prompts import DISCLAIMER

router = APIRouter(prefix="/documents", tags=["questions"])
_logger = get_logger(__name__)


def _event(name: str, payload: dict[str, object]) -> str:
    """Serialise one server-sent event frame."""
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "/{document_id}/questions",
    summary="Ask a question about a document (server-sent event stream)",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "The answer stream."},
        400: {"description": "The question attempted to change the assistant's behaviour."},
        404: {"description": "The document has expired."},
    },
)
@limiter.limit(limit_from_settings("rate_limit_questions"))
async def ask_question(
    request: Request,
    response: Response,
    document_id: str,
    payload: QuestionRequest,
    store: StoreDep,
    qa_service: QaDep,
) -> StreamingResponse:
    """Answer a question using only passages retrieved from the document."""
    del request, response  # Required by the rate limiter, unused by the handler.
    document = await store.get(document_id)
    citations = await qa_service.retrieve_citations(document=document, question=payload.question)

    async def stream() -> AsyncIterator[str]:
        """Emit citations, then answer fragments, then a terminal event."""
        yield _event(
            "citations",
            {"citations": [citation.model_dump() for citation in citations]},
        )
        try:
            async for fragment in qa_service.stream_answer(
                document=document, question=payload.question, citations=citations
            ):
                yield _event("token", {"text": fragment})
        except LexiClearError as exc:
            _logger.warning("qa_stream_failed", code=exc.code, detail=exc.detail)
            yield _event("error", {"code": exc.code, "message": exc.message})
            return
        yield _event("done", {"disclaimer": DISCLAIMER})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
