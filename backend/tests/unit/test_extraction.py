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


class TestExtractionBudget:
    """Pages past the retention ceiling are never parsed."""

    def test_pdf_pages_beyond_the_budget_are_not_extracted(self, minimal_pdf, monkeypatch):
        from types import SimpleNamespace

        parsed: list[int] = []

        def page(number: int) -> SimpleNamespace:
            def extract_text() -> str:
                parsed.append(number)
                return f"Clause {number}. " + "The tenant shall pay rent. " * 20

            return SimpleNamespace(extract_text=extract_text)

        pages = [page(number) for number in range(50)]
        monkeypatch.setattr(
            "app.services.extraction.PdfReader",
            lambda _stream: SimpleNamespace(is_encrypted=False, pages=pages),
        )
        result = extract(minimal_pdf, "long.pdf", max_characters=1_000)

        assert result.truncated
        assert len(result.text) == 1_000
        assert result.page_count == 50, "the page count still describes the whole file"
        assert len(parsed) < 5, f"parsed {len(parsed)} of 50 pages for a 1,000-character budget"

    def test_docx_paragraphs_beyond_the_budget_are_not_copied(self):
        import io

        import docx

        document = docx.Document()
        for number in range(200):
            document.add_paragraph(f"{number}. The employee shall give written notice. " * 5)
        buffer = io.BytesIO()
        document.save(buffer)

        result = extract(buffer.getvalue(), "long.docx", max_characters=2_000)
        assert result.truncated
        assert len(result.text) == 2_000
        assert "199." not in result.text
