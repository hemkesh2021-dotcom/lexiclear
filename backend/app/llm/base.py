"""Provider-agnostic contract for the generative model layer.

Every service in the application depends on :class:`LlmProvider` rather than on
a concrete SDK.  That inversion keeps vendor code confined to ``app/llm`` and
lets the whole pipeline be tested deterministically against
:class:`app.llm.mock.MockLlmProvider` with no network access and no API key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class EmbeddingTask(StrEnum):
    """Retrieval role of the text being embedded.

    Gemini's embedding models are asymmetric: encoding a passage and encoding
    the query that should retrieve it use different task types, and mixing them
    measurably degrades recall.
    """

    DOCUMENT = "RETRIEVAL_DOCUMENT"
    QUERY = "RETRIEVAL_QUERY"


@runtime_checkable
class LlmProvider(Protocol):
    """The generative capabilities the application depends on."""

    @property
    def name(self) -> str:
        """Human-readable provider identifier, surfaced on the health endpoint."""
        ...

    async def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate a response constrained to ``response_schema``.

        Args:
            system_instruction: Role and safety framing for the model.
            prompt: The user-turn content, with untrusted text already delimited.
            response_schema: A JSON Schema object the reply must conform to.
            temperature: Sampling temperature; analysis paths keep this low.

        Returns:
            The decoded JSON object returned by the model.

        Raises:
            LlmUnavailableError: If the model is unreachable or returns a reply
                that cannot be decoded as the requested schema.
        """
        ...

    def generate_stream(
        self,
        *,
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream a free-text response token group by token group.

        Args:
            system_instruction: Role and safety framing for the model.
            prompt: The user-turn content, with untrusted text already delimited.
            temperature: Sampling temperature.

        Yields:
            Successive text fragments of the reply.
        """
        ...

    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask,
    ) -> list[list[float]]:
        """Embed ``texts`` for semantic retrieval.

        Args:
            texts: The texts to embed, in order.
            task: Whether these are passages or queries.

        Returns:
            One embedding vector per input, in the same order.
        """
        ...
