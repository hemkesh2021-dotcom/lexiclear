"""Text extraction is format-aware and refuses files it cannot read."""

import pytest

from app.core.errors import DocumentExtractionError
from app.security.file_validation import validate_upload
from app.services.extraction import extract_document, normalise_whitespace


def extract(content: bytes, name: str, *, max_characters: int = 400_000):
    upload = validate_upload(content, raw_filename=name, max_bytes=10 * 1024 * 1024)
    return extract_document(upload, max_characters=max_characters)


class TestNormalisation:
    def test_horizontal_whitespace_collapses(self):
        assert normalise_whitespace("The  Tenant\t shall   pay") == "The Tenant shall pay"

    def test_paragraph_breaks_survive(self):
        assert normalise_whitespace("Clause 1\n\n\n\nClause 2") == "Clause 1\n\nClause 2"

    def test_leading_and_trailing_space_is_trimmed(self):
        assert normalise_whitespace("\n\n  text  \n\n") == "text"


class TestPlainText:
    def test_a_contract_is_extracted_whole(self, contract_bytes):
        result = extract(contract_bytes, "lease.txt")
        assert "RESIDENTIAL RENTAL AGREEMENT" in result.text
        assert result.character_count == len(result.text)
        assert result.truncated is False

    def test_truncation_is_reported(self, contract_bytes):
        result = extract(contract_bytes, "lease.txt", max_characters=500)
        assert result.truncated is True
        assert result.character_count == 500


class TestWordDocuments:
    def test_paragraph_text_is_extracted(self, minimal_docx):
        assert "thirty (30) days written notice" in extract(minimal_docx, "a.docx").text

    def test_a_zip_that_is_not_a_docx_is_rejected(self, zip_bomb_lookalike):
        with pytest.raises(DocumentExtractionError):
            extract(zip_bomb_lookalike, "notes.docx")


class TestPdfDocuments:
    def test_an_image_only_pdf_is_rejected_with_actionable_guidance(self, minimal_pdf):
        with pytest.raises(DocumentExtractionError, match="scan or a photo"):
            extract(minimal_pdf, "scan.pdf")

    def test_a_corrupt_pdf_is_rejected(self):
        with pytest.raises(DocumentExtractionError):
            extract(b"%PDF-1.4\nthis is not a real pdf body", "broken.pdf")
