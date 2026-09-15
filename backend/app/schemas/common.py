"""Shared response primitives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base model with the project's serialisation conventions."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ErrorResponse(ApiModel):
    """The single error shape returned by every failing endpoint."""

    code: str = Field(description="Stable machine-readable error identifier.")
    message: str = Field(description="Message safe to display to an end user.")
