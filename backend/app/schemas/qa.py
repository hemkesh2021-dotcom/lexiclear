"""Grounded question-answering schemas."""

from __future__ import annotations

from pydantic import Field, field_validator

from app.schemas.common import ApiModel

MAX_QUESTION_LENGTH = 1000


class QuestionRequest(ApiModel):
    """A user question about an already-indexed document."""

    question: str = Field(
        min_length=3,
        max_length=MAX_QUESTION_LENGTH,
        description="The question to answer using only the uploaded document.",
    )

    @field_validator("question")
    @classmethod
    def _require_content(cls, value: str) -> str:
        """Reject whitespace-only questions."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("The question cannot be empty.")
        return stripped


class Citation(ApiModel):
    """A passage the answer was drawn from."""

    label: str = Field(description="Clause heading or passage number.")
    quote: str = Field(description="The passage text, trimmed for display.")
    start: int = Field(ge=0, description="Inclusive start offset in the document text.")
    end: int = Field(ge=0, description="Exclusive end offset in the document text.")
    score: float = Field(description="Fused retrieval score that selected this passage.")
