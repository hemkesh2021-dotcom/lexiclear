"""The upload endpoint, exercised through the full middleware stack."""

import pytest


class TestUpload:
    async def test_a_text_contract_is_indexed(self, client, contract_bytes):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("lease.txt", contract_bytes, "text/plain")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "lease.txt"
        assert body["chunk_count"] > 5
        assert body["truncated"] is False
        assert body["expires_in_seconds"] == 60

    async def test_a_word_document_is_indexed(self, client, minimal_docx):
        response = await client.post(
            "/api/v1/documents",
            files={
                "file": (
                    "notice.docx",
                    minimal_docx,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 201

    async def test_a_path_traversal_filename_is_sanitised(self, client, contract_bytes):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("../../etc/passwd", contract_bytes, "text/plain")},
        )
        assert response.status_code == 201
        assert response.json()["filename"] == "passwd"

    async def test_an_executable_renamed_to_pdf_is_refused(self, client):
        payload = b"MZ\x90\x00\x03" + b"\x00" * 200
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", payload, "application/pdf")},
        )
        assert response.status_code == 415
        assert response.json()["code"] == "unsupported_file_type"

    async def test_an_oversized_upload_is_refused(self, client):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("big.txt", b"a" * (2 * 1024 * 1024), "text/plain")},
        )
        assert response.status_code == 413
        assert response.json()["code"] == "file_too_large"

    async def test_an_empty_upload_is_refused(self, client):
        response = await client.post(
            "/api/v1/documents", files={"file": ("empty.txt", b"", "text/plain")}
        )
        assert response.status_code == 413

    async def test_a_missing_file_field_is_refused(self, client):
        response = await client.post("/api/v1/documents")
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"

    async def test_a_scanned_pdf_gets_actionable_guidance(self, client, minimal_pdf):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("scan.pdf", minimal_pdf, "application/pdf")},
        )
        assert response.status_code == 422
        assert "scan or a photo" in response.json()["message"]


class TestRetrievalAndDeletion:
    @pytest.fixture
    async def document_id(self, client, contract_bytes):
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("lease.txt", contract_bytes, "text/plain")},
        )
        return response.json()["document_id"]

    async def test_metadata_can_be_fetched(self, client, document_id):
        response = await client.get(f"/api/v1/documents/{document_id}")
        assert response.status_code == 200
        assert response.json()["document_id"] == document_id

    async def test_an_unknown_document_is_a_404(self, client):
        response = await client.get("/api/v1/documents/not-a-real-id")
        assert response.status_code == 404
        assert response.json()["code"] == "document_not_found"

    async def test_a_document_can_be_deleted_on_demand(self, client, document_id):
        assert (await client.delete(f"/api/v1/documents/{document_id}")).status_code == 204
        assert (await client.get(f"/api/v1/documents/{document_id}")).status_code == 404

    async def test_deleting_an_unknown_document_is_idempotent(self, client):
        assert (await client.delete("/api/v1/documents/whatever")).status_code == 204
