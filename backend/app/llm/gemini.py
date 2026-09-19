"""Google Gemini implementation of :class:`app.llm.base.LlmProvider`.

Uses the ``google-genai`` SDK against the Gemini Developer API.  Two model
families are used:

* ``gemini-3.6-flash`` for clause analysis, summarisation and grounded answers.
  Analysis calls use the SDK's *structured output* mode, so the schema is
  enforced by the decoding process rather than by parsing prose afterwards.
* ``gemini-embedding-001`` for passage and query embeddings, truncated to 768
  dimensions, which keeps the in-memory index small with negligible recall loss.

Resilience matters more here than in most services, because a demand spike on
a hosted model is indistinguishable, to the person waiting, from the product
being broken. Every generation call therefore:

* retries only *transient* failures (rate limits, overload, timeouts) with
  exponential back-off and jitter, and fails fast on permanent ones such as a
  retired model name, so a misconfiguration surfaces in one second rather than
  after a long silent retry loop;
* falls through an ordered list of models (``generation_model`` then
  ``fallback_models``), so one overloaded model degrades the answer's source
  rather than the user's experience.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Sequence
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import Settings
from app.core.errors import LlmUnavailableError
from app.core.logging import get_logger
from app.llm.base import EmbeddingTask

_logger = get_logger(__name__)

#: Safety settings are left at the API defaults.  Legal documents legitimately
#: describe disputes, penalties and liabilities, so the thresholds are not
#: tightened further; the guardrail that matters here is the system instruction.

#: HTTP statuses worth retrying: rate limiting and server-side overload.
_TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

#: Automatic function calling is on by default in the SDK. LexiClear declares
#: no tools, so leaving it on only adds a logged warning and per-call overhead.
_NO_TOOL_CALLING = genai_types.AutomaticFunctionCallingConfig(disable=True)
_RETRY_BASE_DELAY_SECONDS = 1.0
_RETRY_MAX_DELAY_SECONDS = 8.0


def is_transient(error: BaseException) -> bool:
    """Return whether ``error`` is worth retrying against the same model.

    Args:
        error: The exception raised by the SDK or by the timeout guard.

    Returns:
        ``True`` for rate limits, overload and timeouts; ``False`` for failures
        that will recur on every attempt, such as an unknown model or a
        malformed request.
    """
    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, genai_errors.APIError):
        return error.code in _TRANSIENT_STATUS_CODES
    # Transport-level failures (reset connections, DNS hiccups) surface as
    # assorted exception types and are worth one more attempt.
    return not isinstance(error, ValueError | TypeError | KeyError)


def backoff_delay(attempt: int) -> float:
    """Exponential back-off with full jitter, capped.

    Jitter spreads retries from many clients apart, which is what stops a
    demand spike from being prolonged by everyone retrying in lock-step.
    """
    ceiling = min(_RETRY_MAX_DELAY_SECONDS, _RETRY_BASE_DELAY_SECONDS * (2**attempt))
    # Jitter only spaces retries apart; it has no security role.
    return random.uniform(ceiling / 2, ceiling)  # noqa: S311  # nosec B311


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

    @property
    def models(self) -> tuple[str, ...]:
        """Generation models to try, in order of preference, without duplicates."""
        ordered = (self._settings.generation_model, *self._settings.fallback_models)
        return tuple(dict.fromkeys(model for model in ordered if model))

    def _base_config(self, *, system_instruction: str, temperature: float) -> dict[str, object]:
        """Settings shared by every generation call."""
        return {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "max_output_tokens": self._settings.llm_max_output_tokens,
            "automatic_function_calling": _NO_TOOL_CALLING,
            "thinking_config": genai_types.ThinkingConfig(
                thinking_level=genai_types.ThinkingLevel(self._settings.llm_thinking_level.upper())
            ),
        }

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
            **self._base_config(system_instruction=system_instruction, temperature=temperature),
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
        """Invoke the model chain with retries and fallback.

        Args:
            prompt: The user-turn content.
            config: Generation configuration including the response schema.

        Returns:
            The raw text of the first successful model reply.

        Raises:
            LlmUnavailableError: When every model in the chain has failed.
        """
        last_error: BaseException | None = None
        for model in self.models:
            for attempt in range(self._settings.llm_max_retries):
                try:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=model, contents=prompt, config=config
                        ),
                        timeout=self._settings.llm_timeout_seconds,
                    )
                    text = (response.text or "").strip()
                    if text:
                        if model != self._settings.generation_model:
                            _logger.info("gemini_fallback_used", model=model)
                        return text
                    last_error = ValueError("Model returned an empty response.")
                except Exception as exc:
                    last_error = exc
                    _logger.warning(
                        "gemini_call_failed", model=model, attempt=attempt + 1, error=str(exc)
                    )
                    if not is_transient(exc):
                        break  # a permanent failure: try the next model at once
                if attempt < self._settings.llm_max_retries - 1:
                    await asyncio.sleep(backoff_delay(attempt))

        raise LlmUnavailableError(
            "The analysis service is busy right now. Please try again in a minute.",
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
        """Stream a free-text reply. See the protocol docstring.

        Falls back to the next model only while nothing has been yielded; once
        text has reached the user, switching models would splice two answers.
        """
        config = genai_types.GenerateContentConfig(
            **self._base_config(system_instruction=system_instruction, temperature=temperature)
        )
        last_error: BaseException | None = None
        for model in self.models:
            started = False
            try:
                stream = await self._client.aio.models.generate_content_stream(
                    model=model, contents=prompt, config=config
                )
                async for chunk in stream:
                    fragment = chunk.text
                    if fragment:
                        started = True
                        yield fragment
                if started:
                    return
                last_error = ValueError("Model returned an empty stream.")
            except Exception as exc:
                last_error = exc
                _logger.warning("gemini_stream_failed", model=model, error=str(exc))
                if started:
                    break

        raise LlmUnavailableError(
            "The answer could not be completed. Please try again.",
            detail=str(last_error),
        )

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
