"""The Gemini adapter: retries, timeouts, batching and failure containment.

The SDK client is replaced with a scripted double. That keeps the tests offline
and deterministic while still exercising the adapter's own logic - the retry
budget, the back-off, the batch fan-out and the guarantee that an upstream
failure becomes a client-safe error rather than a leaked SDK exception.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import LlmUnavailableError
from app.llm.base import EmbeddingTask
from app.llm.gemini import GeminiProvider


class FakeModels:
    """Scripted stand-in for ``client.aio.models``."""

    def __init__(self, *, replies=None, error=None, embed_dimensions=768, embed_error=None):
        self.replies = list(replies or [])
        self.error = error
        self.embed_dimensions = embed_dimensions
        self.embed_error = embed_error
        self.calls = 0
        self.embed_batches: list[list[str]] = []
        self.embed_task_types: list[str] = []

    async def generate_content(self, *, model, contents, config):
        del contents
        self.calls += 1
        self.last_model = model
        self.last_config = config
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.replies.pop(0) if self.replies else "")

    async def generate_content_stream(self, *, model, contents, config):
        del model, contents, config
        if self.error is not None:
            raise self.error

        async def iterator():
            for fragment in self.replies:
                yield SimpleNamespace(text=fragment)

        return iterator()

    async def embed_content(self, *, model, contents, config):
        del model
        if self.embed_error is not None:
            raise self.embed_error
        self.embed_batches.append(list(contents))
        self.embed_task_types.append(config.task_type)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * self.embed_dimensions) for _ in contents]
        )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        llm_provider="gemini",
        google_api_key="test-key-not-a-real-secret",
        embedding_batch_size=2,
        llm_timeout_seconds=0.2,
    )


def build(settings: Settings, models: FakeModels, monkeypatch) -> GeminiProvider:
    monkeypatch.setattr(
        "app.llm.gemini.genai.Client",
        lambda api_key: SimpleNamespace(aio=SimpleNamespace(models=models)),
    )
    monkeypatch.setattr("app.llm.gemini._RETRY_BASE_DELAY_SECONDS", 0.0)
    return GeminiProvider(settings)


class TestConfiguration:
    def test_a_missing_api_key_fails_fast_with_a_client_safe_message(self):
        with pytest.raises(LlmUnavailableError) as caught:
            GeminiProvider(Settings(llm_provider="gemini", google_api_key=""))
        assert "not configured" in caught.value.message
        assert "LEXICLEAR_GOOGLE_API_KEY" not in caught.value.message

    def test_the_key_is_never_exposed_through_the_provider_name(self, settings, monkeypatch):
        provider = build(settings, FakeModels(), monkeypatch)
        assert "test-key" not in provider.name
        assert provider.name.startswith("gemini:")


class TestJsonGeneration:
    async def test_a_valid_reply_is_decoded(self, settings, monkeypatch):
        models = FakeModels(replies=['{"document_type": "Lease"}'])
        provider = build(settings, models, monkeypatch)
        result = await provider.generate_json(
            system_instruction="s", prompt="p", response_schema={"type": "object"}
        )
        assert result == {"document_type": "Lease"}
        assert models.calls == 1

    async def test_a_transient_failure_is_retried(self, settings, monkeypatch):
        class FlakyModels(FakeModels):
            async def generate_content(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError("upstream 503")
                return SimpleNamespace(text='{"ok": true}')

        models = FlakyModels()
        provider = build(settings, models, monkeypatch)
        assert await provider.generate_json(
            system_instruction="s", prompt="p", response_schema={}
        ) == {"ok": True}
        assert models.calls == 3

    async def test_the_retry_budget_is_bounded(self, settings, monkeypatch):
        models = FakeModels(error=RuntimeError("permanently down"))
        provider = build(settings, models, monkeypatch)
        with pytest.raises(LlmUnavailableError):
            await provider.generate_json(system_instruction="s", prompt="p", response_schema={})
        assert models.calls == 3

    async def test_upstream_details_never_reach_the_client_message(self, settings, monkeypatch):
        models = FakeModels(error=RuntimeError("API key AIzaSyDEADBEEF rejected"))
        provider = build(settings, models, monkeypatch)
        with pytest.raises(LlmUnavailableError) as caught:
            await provider.generate_json(system_instruction="s", prompt="p", response_schema={})
        assert "AIzaSy" not in caught.value.message

    async def test_malformed_json_is_reported_as_unavailable(self, settings, monkeypatch):
        provider = build(settings, FakeModels(replies=["not json at all"]), monkeypatch)
        with pytest.raises(LlmUnavailableError, match="unreadable"):
            await provider.generate_json(system_instruction="s", prompt="p", response_schema={})

    async def test_a_json_array_is_rejected_because_an_object_was_requested(
        self, settings, monkeypatch
    ):
        provider = build(settings, FakeModels(replies=["[1, 2, 3]"]), monkeypatch)
        with pytest.raises(LlmUnavailableError, match="unexpected result"):
            await provider.generate_json(system_instruction="s", prompt="p", response_schema={})

    async def test_a_hanging_call_is_abandoned_at_the_timeout(self, settings, monkeypatch):
        class HangingModels(FakeModels):
            async def generate_content(self, **kwargs):
                self.calls += 1
                await asyncio.sleep(5)

        models = HangingModels()
        provider = build(settings, models, monkeypatch)
        with pytest.raises(LlmUnavailableError):
            await provider.generate_json(system_instruction="s", prompt="p", response_schema={})
        assert models.calls == 3


class TestStreaming:
    async def test_fragments_are_yielded_in_order(self, settings, monkeypatch):
        provider = build(settings, FakeModels(replies=["The ", "notice ", "period"]), monkeypatch)
        fragments = [
            fragment
            async for fragment in provider.generate_stream(system_instruction="s", prompt="p")
        ]
        assert "".join(fragments) == "The notice period"

    async def test_a_stream_failure_becomes_a_client_safe_error(self, settings, monkeypatch):
        provider = build(settings, FakeModels(error=RuntimeError("socket reset")), monkeypatch)
        with pytest.raises(LlmUnavailableError):
            async for _ in provider.generate_stream(system_instruction="s", prompt="p"):
                pass


class TestEmbedding:
    async def test_inputs_are_split_into_configured_batches(self, settings, monkeypatch):
        models = FakeModels()
        provider = build(settings, models, monkeypatch)
        vectors = await provider.embed(
            [f"passage {i}" for i in range(5)], task=EmbeddingTask.DOCUMENT
        )
        assert len(vectors) == 5
        assert [len(batch) for batch in models.embed_batches] == [2, 2, 1]

    async def test_the_retrieval_task_type_is_propagated(self, settings, monkeypatch):
        models = FakeModels()
        provider = build(settings, models, monkeypatch)
        await provider.embed(["a question"], task=EmbeddingTask.QUERY)
        assert models.embed_task_types == ["RETRIEVAL_QUERY"]

    async def test_an_empty_input_makes_no_call(self, settings, monkeypatch):
        models = FakeModels()
        provider = build(settings, models, monkeypatch)
        assert await provider.embed([], task=EmbeddingTask.DOCUMENT) == []
        assert models.embed_batches == []

    async def test_a_short_reply_is_treated_as_a_failure(self, settings, monkeypatch):
        class ShortModels(FakeModels):
            async def embed_content(self, **kwargs):
                return SimpleNamespace(embeddings=[])

        provider = build(settings, ShortModels(), monkeypatch)
        with pytest.raises(LlmUnavailableError, match="could not be indexed"):
            await provider.embed(["a", "b"], task=EmbeddingTask.DOCUMENT)

    async def test_an_upstream_failure_becomes_a_client_safe_error(self, settings, monkeypatch):
        models = FakeModels(embed_error=RuntimeError("quota exceeded for project 12345"))
        provider = build(settings, models, monkeypatch)
        with pytest.raises(LlmUnavailableError) as caught:
            await provider.embed(["a"], task=EmbeddingTask.DOCUMENT)
        assert "12345" not in caught.value.message


class TestGenerationConfig:
    async def test_tool_calling_is_disabled_and_thinking_is_bounded(self, settings, monkeypatch):
        models = FakeModels(replies=['{"ok": true}'])
        provider = build(settings, models, monkeypatch)
        await provider.generate_json(system_instruction="s", prompt="p", response_schema={})
        assert models.last_config.automatic_function_calling.disable is True
        assert models.last_config.thinking_config.thinking_level.value == "LOW"
        assert models.last_config.response_mime_type == "application/json"

    async def test_the_configured_model_is_used(self, settings, monkeypatch):
        models = FakeModels(replies=["{}"])
        provider = build(settings, models, monkeypatch)
        await provider.generate_json(system_instruction="s", prompt="p", response_schema={})
        assert models.last_model == settings.generation_model == "gemini-3.6-flash"
