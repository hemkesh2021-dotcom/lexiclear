"""Request-scoped dependency wiring.

Long-lived collaborators (the model client, the document store, the services)
are constructed once during application start-up and held on ``app.state``.  The
functions here expose them to routes through FastAPI's dependency system, which
is also the seam tests use to substitute the mock model provider.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.llm.base import LlmProvider
from app.services.clause_analysis import ClauseAnalysisService
from app.services.ingestion import IngestionService
from app.services.qa_service import QuestionAnsweringService
from app.services.store import DocumentStore


def get_request_settings(request: Request) -> Settings:
    """Return the settings this application instance was built with.

    Reading from ``app.state`` rather than from the cached module-level
    singleton is what lets a test build an application with different limits
    and have the routes actually honour them.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_llm_provider(request: Request) -> LlmProvider:
    """Return the process-wide model provider."""
    provider: LlmProvider = request.app.state.llm_provider
    return provider


def get_document_store(request: Request) -> DocumentStore:
    """Return the process-wide in-memory document store."""
    store: DocumentStore = request.app.state.document_store
    return store


def get_ingestion_service(request: Request) -> IngestionService:
    """Return the upload ingestion pipeline."""
    service: IngestionService = request.app.state.ingestion_service
    return service


def get_analysis_service(request: Request) -> ClauseAnalysisService:
    """Return the clause-analysis service."""
    service: ClauseAnalysisService = request.app.state.analysis_service
    return service


def get_qa_service(request: Request) -> QuestionAnsweringService:
    """Return the grounded question-answering service."""
    service: QuestionAnsweringService = request.app.state.qa_service
    return service


SettingsDep = Annotated[Settings, Depends(get_request_settings)]
LlmDep = Annotated[LlmProvider, Depends(get_llm_provider)]
StoreDep = Annotated[DocumentStore, Depends(get_document_store)]
IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]
AnalysisDep = Annotated[ClauseAnalysisService, Depends(get_analysis_service)]
QaDep = Annotated[QuestionAnsweringService, Depends(get_qa_service)]
