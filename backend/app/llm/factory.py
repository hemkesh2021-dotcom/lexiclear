"""Construction of the configured :class:`app.llm.base.LlmProvider`."""

from __future__ import annotations

from app.core.config import Settings
from app.llm.base import LlmProvider
from app.llm.gemini import GeminiProvider
from app.llm.mock import MockLlmProvider


def build_llm_provider(settings: Settings) -> LlmProvider:
    """Instantiate the provider named in ``settings``.

    Args:
        settings: Application settings.

    Returns:
        A ready-to-use provider implementing :class:`LlmProvider`.
    """
    if settings.llm_provider == "mock":
        return MockLlmProvider(dimensions=settings.embedding_dimensions)
    return GeminiProvider(settings)
