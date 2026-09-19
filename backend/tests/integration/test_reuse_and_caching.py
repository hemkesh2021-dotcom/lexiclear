"""Expensive work is done once per document content, never once per request.

Re-uploading a document that is still held (the front end does this on its own
when a session expires) must not re-embed it, and concurrent analysis requests
must share a single model call. Reuse must also never leak one upload's handle
into another upload's response.
"""

import asyncio

import pytest


async def upload(client, payload: bytes, name: str = "lease.txt") -> str:
    response = await client.post("/api/v1/documents", files={"file": (name, payload, "text/plain")})
    assert response.status_code == 201 or response.status_code == 200
    return response.json()["document_id"]


@pytest.fixture
def counted(app, monkeypatch):
    """Count embedding and analysis calls made by the running application."""
    counts = {"embed": 0, "analyse": 0}

    def install() -> None:
        llm = app.state.llm_provider
        service = app.state.analysis_service
        original_embed = llm.embed
        original_analyse = service.analyse

        async def embed(texts, *, task):
            if task.name == "DOCUMENT":
                counts["embed"] += 1
            return await original_embed(texts, task=task)

        async def analyse(document):
            counts["analyse"] += 1
            await asyncio.sleep(0.01)  # widen the window a race would need
            return await original_analyse(document)

        monkeypatch.setattr(llm, "embed", embed)
        monkeypatch.setattr(service, "analyse", analyse)

    return counts, install


class TestContentReuse:
    async def test_reuploading_identical_content_does_not_re_embed(
        self, client, contract_bytes, counted
    ):
        counts, install = counted
        install()
        first = await upload(client, contract_bytes)
        second = await upload(client, contract_bytes)
        assert first != second, "each upload must receive its own handle"
        assert counts["embed"] == 1

    async def test_different_content_is_embedded_separately(self, client, contract_bytes, counted):
        counts, install = counted
        install()
        await upload(client, contract_bytes)
        await upload(client, contract_bytes + b"\n\n14. An extra clause.")
        assert counts["embed"] == 2

    async def test_an_analysis_is_reused_but_addressed_to_the_new_handle(
        self, client, contract_bytes, counted
    ):
        counts, install = counted
        install()
        first = await upload(client, contract_bytes)
        first_body = (await client.post(f"/api/v1/documents/{first}/analysis")).json()
        second = await upload(client, contract_bytes)
        second_body = (await client.post(f"/api/v1/documents/{second}/analysis")).json()

        assert counts["analyse"] == 1
        assert second_body["document_id"] == second
        assert first not in str(second_body)
        assert first_body["findings"] == second_body["findings"]

    async def test_a_twin_analysed_later_is_reused_too(self, client, contract_bytes, counted):
        counts, install = counted
        install()
        first = await upload(client, contract_bytes)
        second = await upload(client, contract_bytes)  # uploaded before any analysis
        await client.post(f"/api/v1/documents/{first}/analysis")
        body = (await client.post(f"/api/v1/documents/{second}/analysis")).json()
        assert counts["analyse"] == 1
        assert body["document_id"] == second


class TestSingleFlightAnalysis:
    async def test_concurrent_requests_share_one_model_call(self, client, contract_bytes, counted):
        counts, install = counted
        install()
        document_id = await upload(client, contract_bytes)
        responses = await asyncio.gather(
            *(client.post(f"/api/v1/documents/{document_id}/analysis") for _ in range(5))
        )
        assert {response.status_code for response in responses} == {200}
        assert counts["analyse"] == 1
        assert len({response.text for response in responses}) == 1
