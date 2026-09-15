"""Uploads are classified by content, never by the name or type a client claims."""

import pytest

from app.core.errors import FileTooLargeError, UnsupportedFileTypeError
from app.security.file_validation import (
    DocumentFormat,
    detect_format,
    sanitise_filename,
    validate_upload,
)


class TestFilenameSanitisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("contract.pdf", "contract.pdf"),
            ("../../../etc/passwd", "passwd"),
            ("..\\..\\windows\\system32\\config", "config"),
            ("/absolute/path/lease.docx", "lease.docx"),
            ("re;port&$.txt", "re_port__.txt"),
            ("", "document"),
            (None, "document"),
            ("...", "document"),
        ],
    )
    def test_path_traversal_and_control_characters_are_stripped(self, raw, expected):
        assert sanitise_filename(raw) == expected

    def test_long_names_are_truncated(self):
        assert len(sanitise_filename("a" * 500)) <= 120

    def test_unicode_lookalikes_are_normalised(self):
        # Full-width solidus normalises to "/" under NFKC and must not survive
        # as a path separator.
        assert "/" not in sanitise_filename("evil／..／passwd")


class TestFormatDetection:
    def test_pdf_is_detected_from_magic_bytes(self):
        assert detect_format(b"%PDF-1.7\nrest of file") is DocumentFormat.PDF

    def test_docx_is_detected_from_zip_magic(self, minimal_docx):
        assert detect_format(minimal_docx) is DocumentFormat.DOCX

    def test_plain_text_is_detected(self):
        assert detect_format(b"This agreement is made on 1 April.") is DocumentFormat.TEXT

    def test_executable_is_rejected_despite_a_pdf_extension(self):
        # A Windows PE header: the caller may call it "invoice.pdf"; we do not.
        with pytest.raises(UnsupportedFileTypeError):
            detect_format(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00")

    def test_elf_binary_is_rejected(self):
        with pytest.raises(UnsupportedFileTypeError):
            detect_format(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)

    def test_invalid_utf8_is_rejected(self):
        with pytest.raises(UnsupportedFileTypeError):
            detect_format(b"\xff\xfe\x00\x01\x02\x03binary junk")


class TestUploadValidation:
    def test_valid_text_upload_is_accepted(self, contract_bytes):
        result = validate_upload(contract_bytes, raw_filename="lease.txt", max_bytes=1024 * 1024)
        assert result.document_format is DocumentFormat.TEXT
        assert result.safe_filename == "lease.txt"
        assert result.size_bytes == len(contract_bytes)

    def test_empty_upload_is_rejected(self):
        with pytest.raises(FileTooLargeError):
            validate_upload(b"", raw_filename="empty.txt", max_bytes=1024)

    def test_oversized_upload_is_rejected(self):
        with pytest.raises(FileTooLargeError, match="smaller than"):
            validate_upload(b"a" * 2048, raw_filename="big.txt", max_bytes=1024)

    def test_a_zip_that_is_not_a_docx_is_accepted_here_and_fails_at_extraction(
        self, zip_bomb_lookalike
    ):
        # Magic-byte detection cannot distinguish a DOCX from any other ZIP;
        # that is the extraction layer's job, and it is tested there.
        result = validate_upload(
            zip_bomb_lookalike, raw_filename="notes.docx", max_bytes=1024 * 1024
        )
        assert result.document_format is DocumentFormat.DOCX
