"""Liveness and readiness reporting."""

from fastapi import APIRouter

from app.api.deps import LlmDep, SettingsDep, StoreDep
from app.schemas.common import ApiModel

router = APIRouter(tags=["health"])


class HealthResponse(ApiModel):
    """Service health, safe to expose publicly."""

    status: str
    version: str
    llm_provider: str
    documents_in_memory: int
    document_ttl_seconds: int


@router.get("/health", summary="Service health")
async def health(settings: SettingsDep, llm: LlmDep, store: StoreDep) -> HealthResponse:
    """Report service health without revealing configuration secrets."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_provider=llm.name,
        documents_in_memory=await store.size(),
        document_ttl_seconds=settings.document_ttl_seconds,
    )
