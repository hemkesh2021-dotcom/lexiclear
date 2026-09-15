"""Findings reach the user only if the document actually says what they quote."""

import numpy as np
import pytest

from app.core.errors import LlmUnavailableError
from app.llm.mock import MockLlmProvider
from app.schemas.analysis import RiskLevel
from app.services.chunking import chunk_document
from app.services.clause_analysis import (
    ClauseAnalysisService,
    locate_quote,
    normalise_for_matching,
)
from app.services.store import DocumentStore


@pytest.fixture
async def document(contract_text):
    store = DocumentStore(ttl_seconds=600, max_documents=5)
    chunks = chunk_document(contract_text, target_characters=1600, overlap_characters=200)
    return await store.add(
        filename="lease.txt",
        text=contract_text,
        chunks=chunks,
        embeddings=np.zeros((len(chunks), 8), dtype=np.float32),
        page_count=1,
        truncated=False,
    )


class TestQuoteLocation:
    def test_an_exact_quote_is_located(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        quote = "The Landlord may terminate this Agreement at any time"
        span = locate_quote(quote, normalised, original_length=len(contract_text))
        assert span is not None
        assert quote.lower() in contract_text[span.start : span.end].lower()

    def test_a_quote_reflowed_across_lines_is_still_located(self, contract_text):
        # PDF extraction inserts line breaks mid-sentence; the model quotes the
        # sentence as one line. Matching must survive that difference.
        normalised = normalise_for_matching(contract_text)
        quote = "The Tenant shall pay monthly rent of Rupees Forty-Five Thousand"
        assert locate_quote(quote, normalised, original_length=len(contract_text)) is not None

    def test_smart_quotes_do_not_defeat_matching(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        quote = "thirty (30) days’ written"  # right single quotation mark
        source = "Either party may give thirty (30) days' written notice here."
        assert locate_quote(quote, normalise_for_matching(source), original_length=len(source))
        del normalised

    def test_a_paraphrase_is_not_located(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        paraphrase = "The landlord is allowed to end the lease whenever they wish"
        assert locate_quote(paraphrase, normalised, original_length=len(contract_text)) is None

    def test_a_fabricated_quote_is_not_located(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        invented = "The Tenant shall surrender their passport to the Landlord on demand."
        assert locate_quote(invented, normalised, original_length=len(contract_text)) is None

    def test_a_trivially_short_quote_is_rejected_as_evidence(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        assert locate_quote("the", normalised, original_length=len(contract_text)) is None

    def test_offsets_are_within_the_document(self, contract_text):
        normalised = normalise_for_matching(contract_text)
        span = locate_quote(
            "sole arbitrator appointed by", normalised, original_length=len(contract_text)
        )
        assert span is not None
        assert 0 <= span.start < span.end <= len(contract_text)


class TestGroundingVerification:
    async def test_grounded_findings_survive_and_carry_offsets(self, document):
        service = ClauseAnalysisService(llm=MockLlmProvider(), redact_pii=False)
        analysis = await service.analyse(document)

        assert analysis.findings, "the mock quotes real sentences, so findings must survive"
        assert analysis.unverified_finding_count == 0
        for finding in analysis.findings:
            assert finding.source is not None
            # The returned quote is the document's own bytes, not the model's.
            assert document.text[finding.source.start : finding.source.end] == finding.quote

    async def test_fabricated_findings_are_discarded_and_counted(self, document):
        service = ClauseAnalysisService(
            llm=MockLlmProvider(fabricate_quotes=True), redact_pii=False
        )
        analysis = await service.analyse(document)

        assert analysis.findings == []
        assert analysis.unverified_finding_count > 0

    async def test_findings_are_ordered_by_risk(self, document):
        service = ClauseAnalysisService(llm=MockLlmProvider(), redact_pii=False)
        analysis = await service.analyse(document)
        order = [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.INFORMATIONAL]
        positions = [order.index(finding.risk) for finding in analysis.findings]
        assert positions == sorted(positions)

    async def test_the_disclaimer_is_always_attached(self, document):
        service = ClauseAnalysisService(llm=MockLlmProvider(), redact_pii=False)
        analysis = await service.analyse(document)
        assert "not legal advice" in analysis.disclaimer

    async def test_redaction_is_reversed_before_the_result_is_returned(self, document):
        service = ClauseAnalysisService(llm=MockLlmProvider(), redact_pii=True)
        analysis = await service.analyse(document)
        assert all("[EMAIL_" not in finding.quote for finding in analysis.findings)
        assert "[PAN_" not in analysis.plain_language_summary

    async def test_document_text_is_never_sent_without_containment(self, document):
        llm = MockLlmProvider()
        await ClauseAnalysisService(llm=llm, redact_pii=False).analyse(document)
        prompt = llm.recorded_prompts[0]
        assert "<<<DOCUMENT_EXCERPT>>>" in prompt
        assert "<<<END_DOCUMENT_EXCERPT>>>" in prompt

    async def test_an_unusable_model_reply_raises_a_client_safe_error(self, document):
        class BrokenProvider(MockLlmProvider):
            async def generate_json(self, **kwargs):
                return {"document_type": "Lease"}  # every other field missing

        service = ClauseAnalysisService(llm=BrokenProvider(), redact_pii=False)
        with pytest.raises(LlmUnavailableError) as caught:
            await service.analyse(document)
        assert "schema" not in caught.value.message.lower()  # internals stay internal
