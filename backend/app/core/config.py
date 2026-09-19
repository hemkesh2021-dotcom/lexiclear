"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file) and
validated at import time, so a misconfigured deployment fails fast at start-up
rather than at the first request.  No secret is ever hard-coded in the source
tree; see ``SECURITY.md``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LlmProviderName = Literal["gemini", "mock"]
ThinkingLevel = Literal["minimal", "low", "medium", "high"]

#: ``.env`` locations, resolved from this file rather than the working
#: directory, so settings load the same whether the server is started from the
#: repository root, from ``backend/``, or by ``make dev``. Later files win.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILES: tuple[Path, ...] = (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    """Validated runtime configuration for the LexiClear API."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        env_prefix="LEXICLEAR_",
        extra="ignore",
        frozen=True,
    )

    # -- Application -------------------------------------------------------
    app_name: str = "LexiClear"
    environment: Environment = "development"
    api_v1_prefix: str = "/api/v1"

    # -- Large language model ---------------------------------------------
    llm_provider: LlmProviderName = "gemini"
    google_api_key: SecretStr = SecretStr("")
    generation_model: str = "gemini-3.6-flash"
    # Tried in order when the primary model is overloaded or unavailable.
    fallback_models: Annotated[tuple[str, ...], NoDecode] = ()
    llm_max_retries: int = Field(default=3, ge=1, le=6)
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 8192
    # Gemini 3 models reason before answering, and those thinking tokens count
    # against the output budget. Clause extraction is reading, not puzzle
    # solving, so a low level keeps latency down without hurting quality.
    llm_thinking_level: ThinkingLevel = "low"

    # -- Document handling -------------------------------------------------
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_document_characters: int = Field(default=400_000, ge=1_000)
    document_ttl_seconds: int = Field(default=1800, ge=60)
    max_documents_in_memory: int = Field(default=50, ge=1)

    # -- Retrieval ---------------------------------------------------------
    chunk_target_characters: int = Field(default=1_600, ge=200)
    chunk_overlap_characters: int = Field(default=200, ge=0)
    retrieval_top_k: int = Field(default=6, ge=1, le=50)
    embedding_batch_size: int = Field(default=32, ge=1, le=100)

    # -- Security ----------------------------------------------------------
    # ``NoDecode`` hands the raw environment string to the validator below.
    # Without it pydantic-settings tries to JSON-decode any collection-typed
    # variable first, so a plain "http://a,http://b" fails before it can be split.
    cors_allow_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:5173",)
    rate_limit_uploads: str = "10/minute"
    rate_limit_analysis: str = "20/minute"
    rate_limit_questions: str = "40/minute"
    redact_pii_before_llm: bool = True

    @field_validator("cors_allow_origins", "fallback_models", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow a comma-separated string for list-valued settings."""
        if isinstance(value, str):
            return tuple(origin.strip() for origin in value.split(",") if origin.strip())
        return value

    @property
    def chunk_stride(self) -> int:
        """Characters advanced per chunk, guaranteed to be positive."""
        return max(1, self.chunk_target_characters - self.chunk_overlap_characters)

    @property
    def is_production(self) -> bool:
        """Whether the API is running with production hardening enabled."""
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
