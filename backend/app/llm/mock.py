"""Deterministic in-process stand-in for a hosted model.

The mock is not a no-op stub.  It is a working implementation with two
properties that make the rest of the suite meaningful:

* **Embeddings are hashed bag-of-words vectors**, so texts that share vocabulary
  land near each other.  Retrieval tests therefore assert real ranking
  behaviour rather than a fixed ordering.
* **JSON generation is schema-driven**, and any field whose name marks it as a
  verbatim quotation is filled with a real sentence lifted from the document in
  the prompt.  The quote-verification stage in
  :mod:`app.services.clause_analysis` is genuinely exercised, and a test can
  flip ``fabricate_quotes`` on to prove that unverifiable findings are dropped.

It runs without an API key, which is what lets continuous integration execute
the full pipeline on every push.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.llm.base import EmbeddingTask
from app.security.prompt_guard import UNTRUSTED_CLOSE, UNTRUSTED_OPEN

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_SENTENCE_PATTERN = re.compile(r"[^.!?\n]{40,400}[.!?]")
_QUOTE_FIELD_NAMES = frozenset({"quote", "source_text", "excerpt", "evidence"})


class MockLlmProvider:
    """A deterministic provider used by tests and by offline demo mode."""

    def __init__(self, *, dimensions: int = 768, fabricate_quotes: bool = False) -> None:
        """Configure vector width and whether to emit unverifiable quotes.

        Args:
            dimensions: Width of the generated embedding vectors.
            fabricate_quotes: When ``True``, quote fields are filled with text
                that does not appear in the source document, which lets tests
                assert that hallucinated findings are rejected.
        """
        self._dimensions = dimensions
        self._fabricate_quotes = fabricate_quotes
        self.recorded_prompts: list[str] = []

    @property
    def name(self) -> str:
        """Identify the provider in health output."""
        return "mock"

    # ------------------------------------------------------------------ JSON
    async def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        response_schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Synthesise a schema-valid object, quoting the prompt where required."""
        del system_instruction, temperature
        self.recorded_prompts.append(prompt)
        sentences = self._document_sentences(prompt)
        result = self._synthesise(response_schema, sentences, depth=0)
        return result if isinstance(result, dict) else {}

    def _document_sentences(self, prompt: str) -> list[str]:
        """Extract candidate quotable sentences from the delimited document."""
        start = prompt.find(UNTRUSTED_OPEN)
        end = prompt.find(UNTRUSTED_CLOSE)
        body = prompt[start + len(UNTRUSTED_OPEN) : end] if start != -1 and end > start else prompt
        return [match.group(0).strip() for match in _SENTENCE_PATTERN.finditer(body)]

    def _synthesise(
        self,
        schema: dict[str, Any],
        sentences: list[str],
        *,
        depth: int,
        field_name: str = "",
    ) -> Any:
        """Build the smallest value satisfying ``schema``."""
        schema_type = schema.get("type", "object")

        if "enum" in schema:
            enum_values: list[Any] = list(schema["enum"])
            return enum_values[depth % len(enum_values)] if enum_values else None

        if schema_type == "object":
            properties: dict[str, Any] = schema.get("properties", {})
            return {
                key: self._synthesise(value, sentences, depth=depth + 1, field_name=key)
                for key, value in properties.items()
            }

        if schema_type == "array":
            item_schema: dict[str, Any] = schema.get("items", {"type": "string"})
            count = min(3, max(1, len(sentences) or 1))
            return [
                self._synthesise(item_schema, sentences, depth=index, field_name=field_name)
                for index in range(count)
            ]

        if schema_type == "integer":
            return depth
        if schema_type == "number":
            return float(depth)
        if schema_type == "boolean":
            return depth % 2 == 0

        return self._synthesise_string(sentences, depth=depth, field_name=field_name)

    def _synthesise_string(self, sentences: list[str], *, depth: int, field_name: str) -> str:
        """Produce a string, preferring a real document sentence for quote fields."""
        if field_name in _QUOTE_FIELD_NAMES:
            if self._fabricate_quotes:
                return "This sentence does not appear anywhere in the source document."
            if sentences:
                return sentences[depth % len(sentences)]
            return ""
        return f"mock-{field_name or 'value'}-{depth}"

    # ---------------------------------------------------------------- stream
    async def generate_stream(
        self,
        *,
        system_instruction: str,
        prompt: str,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Stream a short deterministic answer derived from the prompt."""
        del system_instruction, temperature
        self.recorded_prompts.append(prompt)
        sentences = self._document_sentences(prompt)
        answer = sentences[0] if sentences else "The document does not address this question."
        for word in f"According to the document: {answer}".split(" "):
            yield f"{word} "

    # ------------------------------------------------------------- embedding
    async def embed(
        self,
        texts: Sequence[str],
        *,
        task: EmbeddingTask,
    ) -> list[list[float]]:
        """Return L2-normalised hashed bag-of-words vectors."""
        del task
        return [self._hash_vector(text) for text in texts]

    def _hash_vector(self, text: str) -> list[float]:
        """Map ``text`` to a stable unit vector in the hashed token space."""
        vector = [0.0] * self._dimensions
        tokens = _TOKEN_PATTERN.findall(text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]
