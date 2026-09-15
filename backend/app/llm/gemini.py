"""Google Gemini implementation of :class:`app.llm.base.LlmProvider`.

Uses the ``google-genai`` SDK against the Gemini Developer API.  Two model
families are used:

* ``gemini-2.5-flash`` for clause analysis, summarisation and grounded answers.
  Analysis calls use the SDK's *structured output* mode, so the schema is
  enforced by the decoding process rather than by parsing prose afterwards.
* ``gemini-embedding-001`` for passage and query embeddings, truncated to 768
  dimensions, which keeps the in-memory index small with negligible recall loss.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.core.config import Settings
from app.core.errors import LlmUnavailableError
from app.core.logging import get_logger
from app.llm.base import EmbeddingTask

_logger = get_logger(__name__)

#: Safety settings are left at the API defaults.  Legal documents legitimately
#: describe disputes, penalties and liabilities, so the thresholds are not
#: tightened further; the guardrail that matters here is the system instruction.
_MAX_RETRIES = 3
_RETRY_BASE_DELAY_SECONDS = 0.5


class GeminiProvider:
    """Generative and embedding calls backed by the Gemini Developer API."""

    def __init__(self, settings: Settings) -> None:
        """Create the async Gemini client from validated settings.

        Args:
            settings: Application settings holding the API key and model names.

        Raises:
            LlmUnavailableError: If no API key has been configured.
        """
        api_key = settings.google_api_key.get_secret_value()
        if not api_key:
            raise LlmUnavailableError(
                "The analysis service is not configured.",
                detail="LEXICLEAR_GOOGLE_API_KEY is empty.",
            )
        self._settings = settings
        self._client = genai.Client(api_key=api_key)

    @property
    def name(self) -> str:
        """Identify the provider and generation model in health output."""
        return f"gemini:{self._settings.generation_model}"

    # ------------------------------------------------------------------ JSON
    async def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate a schema-constrained JSON response. See the protocol docstring."""
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=self._settings.llm_max_output_tokens,
            response_mime_type="application/json",
            response_schema=response_schema,
        )
        raw = await self._call_with_retry(prompt=prompt, config=config)
        try:
            decoded: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LlmUnavailableError(
                "The analysis service returned an unreadable result. Please try again.",
                detail=f"JSON decode failed: {exc}",
            ) from exc
        if not isinstance(decoded, dict):
            raise LlmUnavailableError(
                "The analysis service returned an unexpected result. Please try again.",
                detail=f"Expected a JSON object, received {type(decoded).__name__}.",
            )
        return decoded

    async def _call_with_retry(
        self,
        *,
        prompt: str,
        config: genai_types.GenerateContentConfig,
    ) -> str:
        """Invoke the model with bounded exponential back-off.

        Args:
            prompt: The user-turn content.
            config: Generation configuration including the response schema.

        Returns:
            The raw text of the model reply.

        Raises:
            LlmUnavailableError: After the retry budget is exhausted.
        """
        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._settings.generation_model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self._settings.llm_timeout_seconds,
                )
                text = (response.text or "").strip()
                if text:
                    return text
                last_error = ValueError("Model returned an empty response.")
            except Exception as exc:
                # Transport errors, quota refusals and timeouts all surface as
                # different SDK exception classes; every one of them is worth
                # one more attempt, and none of them should reach the client.
                last_error = exc
                _logger.warning("gemini_call_failed", attempt=attempt + 1, error=str(exc))
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_BASE_DELAY_SECONDS * (2**attempt))

        raise LlmUnavailableError(
            "The analysis service is temporarily unavailable. Please try again shortly.",
            detail=str(last_error),
        )

    # ---------------------------------------------------------------- stream
    async def generate_stream(
        self,
        *,
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream a free-text reply. See the protocol docstring."""
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=self._settings.llm_max_output_tokens,
        )
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._settings.generation_model,
                contents=prompt,
                config=config,
            )
            async for chunk in stream:
                fragment = chunk.text
                if fragment:
                    yield fragment
        except Exception as exc:
            _logger.warning("gemini_stream_failed", error=str(exc))
            raise LlmUnavailableError(
                "The answer could not be completed. Please try again.",
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------- embedding
    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask,
    ) -> list[list[float]]:
        """Embed ``texts`` in batches. See the protocol docstring."""
        if not texts:
            return []

        config = genai_types.EmbedContentConfig(
            task_type=task.value,
            output_dimensionality=self._settings.embedding_dimensions,
        )
        batch_size = self._settings.embedding_batch_size
        batches = [list(texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]

        try:
            responses = await asyncio.gather(
                *(
                    self._client.aio.models.embed_content(
                        model=self._settings.embedding_model,
                        contents=batch,
                        config=config,
                    )
                    for batch in batches
                )
            )
        except Exception as exc:
            _logger.warning("gemini_embed_failed", error=str(exc))
            raise LlmUnavailableError(
                "The document could not be indexed. Please try again.",
                detail=str(exc),
            ) from exc

        vectors: list[list[float]] = []
        for response in responses:
            for embedding in response.embeddings or []:
                vectors.append(list(embedding.values or []))

        if len(vectors) != len(texts):
            raise LlmUnavailableError(
                "The document could not be indexed. Please try again.",
                detail=f"Expected {len(texts)} embeddings, received {len(vectors)}.",
            )
        return vectors
