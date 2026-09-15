"""The analysis endpoint, end to end."""

import pytest


@pytest.fixture
async def document_id(client, contract_bytes):
    response = await client.post(
        "/api/v1/documents", files={"file": ("lease.txt", contract_bytes, "text/plain")}
    )
    return response.json()["document_id"]


class TestAnalysis:
    async def test_a_document_is_analysed(self, client, document_id):
        response = await client.post(f"/api/v1/documents/{document_id}/analysis")
        assert response.status_code == 200
        body = response.json()
        assert body["document_id"] == document_id
        assert body["findings"]
        assert body["disclaimer"]

    async def test_every_returned_finding_quotes_the_document(
        self, client, document_id, contract_text
    ):
        body = (await client.post(f"/api/v1/documents/{document_id}/analysis")).json()
        for finding in body["findings"]:
            assert finding["quote"] in contract_text
            span = finding["source"]
            assert contract_text[span["start"] : span["end"]] == finding["quote"]

    async def test_the_result_is_cached_for_the_document_lifetime(self, client, document_id):
        first = (await client.post(f"/api/v1/documents/{document_id}/analysis")).json()
        second = (await client.post(f"/api/v1/documents/{document_id}/analysis")).json()
        assert first == second

    async def test_analysing_an_expired_document_is_a_404(self, client):
        response = await client.post("/api/v1/documents/gone/analysis")
        assert response.status_code == 404

    async def test_the_response_carries_no_personal_identifiers(self, client, document_id):
        body = (await client.post(f"/api/v1/documents/{document_id}/analysis")).json()
        rendered = str(body)
        assert "[EMAIL_" not in rendered
        assert "[PAN_" not in rendered
