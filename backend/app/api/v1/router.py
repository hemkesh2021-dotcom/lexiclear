"""Aggregation of every version-1 route."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import analysis, documents, health, qa

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(analysis.router)
api_router.include_router(qa.router)
