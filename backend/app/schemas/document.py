"""Document upload and metadata schemas."""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import ApiModel


class DocumentSummary(ApiModel):
    """Metadata returned after a document has been indexed."""

    document_id: str = Field(description="Opaque handle used by later requests.")
    filename: str = Field(description="Sanitised display name of the upload.")
    character_count: int = Field(description="Characters retained after extraction.")
    page_count: int = Field(description="Source page count, where the format reports one.")
    chunk_count: int = Field(description="Number of retrievable passages indexed.")
    truncated: bool = Field(description="Whether the document exceeded the size ceiling.")
    expires_in_seconds: int = Field(
        description="Seconds until the document is automatically deleted from memory."
    )
