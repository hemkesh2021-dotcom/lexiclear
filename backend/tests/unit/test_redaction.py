"""Direct identifiers are replaced before text leaves the process, reversibly."""

import pytest

from app.security.redaction import redact


class TestRedaction:
    @pytest.mark.parametrize(
        ("text", "label"),
        [
            ("Contact anita.raghavan@example.com for details.", "EMAIL"),
            ("Her PAN is ABCDE1234F on file.", "PAN"),
            ("Aadhaar 1234 5678 9012 was verified.", "AADHAAR"),
            ("Call 9845012345 between 9 and 5.", "PHONE"),
            ("Card 4111 1111 1111 1111 on record.", "CARD"),
            ("Transfer to GB29NWBK60161331926819 today.", "IBAN"),
        ],
    )
    def test_identifiers_are_replaced(self, text, label):
        result = redact(text)
        assert f"[{label}_1]" in result.text
        assert result.mapping

    def test_the_original_value_is_gone_from_the_redacted_text(self):
        result = redact("Write to anita.raghavan@example.com today.")
        assert "anita.raghavan@example.com" not in result.text

    def test_restore_is_the_exact_inverse(self):
        original = "Email anita@example.com or call 9845012345. PAN ABCDE1234F."
        result = redact(original)
        assert result.restore(result.text) == original

    def test_the_same_identifier_maps_to_one_placeholder(self):
        result = redact("Mail a@b.com, then mail a@b.com again.")
        assert result.text.count("[EMAIL_1]") == 2
        assert len(result.mapping) == 1

    def test_distinct_identifiers_get_distinct_placeholders(self):
        result = redact("Mail a@b.com and c@d.com.")
        assert "[EMAIL_1]" in result.text
        assert "[EMAIL_2]" in result.text

    def test_disabling_redaction_is_a_passthrough(self):
        original = "Email a@b.com."
        result = redact(original, enabled=False)
        assert result.text == original
        assert result.mapping == {}

    def test_ordinary_legal_text_is_untouched(self):
        clause = "The Tenant shall pay monthly rent of Rupees Forty-Five Thousand."
        assert redact(clause).text == clause

    def test_a_real_contract_is_redacted_end_to_end(self, contract_text):
        result = redact(contract_text)
        assert "anita.raghavan@example.com" not in result.text
        assert "ABCDE1234F" not in result.text
        assert result.restore(result.text) == contract_text
