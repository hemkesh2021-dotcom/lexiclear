"""Clause extraction, risk flagging and grounding verification.

The model is asked for a structured analysis in which every finding carries a
verbatim quotation.  Each quotation is then *verified against the source text*
before the finding is returned.  A finding whose quote cannot be located is
discarded and counted, so a fabricated clause never reaches the user and the
response reports how many were dropped.

Verification is deliberately tolerant of whitespace and quotation-mark variants,
because extracting text from a PDF reflows it, but it is not tolerant of
paraphrase: the words themselves must be present, in order.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import Field, ValidationError

from app.core.errors import LlmUnavailableError
from app.core.logging import get_logger
from app.llm.base import LlmProvider
from app.schemas.analysis import (
    ClauseFinding,
    DocumentAnalysis,
    ObligationItem,
    RiskLevel,
    SourceSpan,
)
from app.schemas.common import ApiModel
from app.security.redaction import redact
from app.services.prompts import (
    ANALYSIS_SYSTEM_INSTRUCTION,
    DISCLAIMER,
    build_analysis_prompt,
    json_schema_for,
)
from app.services.store import StoredDocument

_logger = get_logger(__name__)

_WHITESPACE = re.compile(r"\s+")
_SMART_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

#: A quotation shorter than this carries too little signal to be treated as
#: evidence, and would match incidental text almost anywhere in a document.
MIN_QUOTE_CHARACTERS = 12

#: Presentation order: the clauses a reader most needs to see come first.
_RISK_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.HIGH,
    RiskLevel.MEDIUM,
    RiskLevel.LOW,
    RiskLevel.INFORMATIONAL,
)


class AnalysisPayload(ApiModel):
    """The shape requested from the model, before grounding verification.

    Kept separate from :class:`~app.schemas.analysis.DocumentAnalysis` because
    the fields the model produces and the fields the API returns are not the
    same set: identifiers, verified offsets, the discarded-finding count and the
    disclaimer are all added by this service, not by the model.
    """

    document_type: str = Field(description="Best-effort classification, e.g. 'Lease agreement'.")
    parties: list[str] = Field(description="Named parties to the document.")
    plain_language_summary: str = Field(
        description="Three to five sentences explaining the document in plain language."
    )
    key_dates: list[str] = Field(description="Dates, durations and notice periods that matter.")
    findings: list[ClauseFinding] = Field(
        description="Between three and twelve clauses the reader should know about."
    )
    obligations: list[ObligationItem] = Field(description="Actions the reader must take.")
    questions_for_a_lawyer: list[str] = Field(
        description="Three to six specific questions to raise with a qualified professional."
    )


@dataclass(frozen=True, slots=True)
class NormalisedText:
    """Whitespace-collapsed text alongside a map back to original offsets."""

    value: str
    offsets: tuple[int, ...]


def normalise_for_matching(text: str) -> NormalisedText:
    """Collapse whitespace and fold quote variants, tracking original offsets.

    Args:
        text: The text to normalise.

    Returns:
        The normalised text and, for each of its characters, the offset of the
        corresponding character in ``text``.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_SMART_QUOTES).lower()
    characters: list[str] = []
    offsets: list[int] = []
    previous_was_space = True

    for index, character in enumerate(folded):
        if character.isspace():
            if not previous_was_space and characters:
                characters.append(" ")
                offsets.append(index)
                previous_was_space = True
            continue
        characters.append(character)
        offsets.append(index)
        previous_was_space = False

    while characters and characters[-1] == " ":
        characters.pop()
        offsets.pop()

    return NormalisedText(value="".join(characters), offsets=tuple(offsets))


def locate_quote(
    quote: str, document: NormalisedText, *, original_length: int
) -> SourceSpan | None:
    """Find ``quote`` in ``document`` and map it back to original offsets.

    Args:
        quote: The verbatim quotation claimed by the model.
        document: The normalised document text and its offset map.
        original_length: Length of the original text, used to clamp the result.

    Returns:
        The span the quote occupies in the original text, or ``None`` when the
        quote is absent or too short to count as evidence.
    """
    normalised_quote = _WHITESPACE.sub(
        " ", unicodedata.normalize("NFKC", quote).translate(_SMART_QUOTES).lower()
    ).strip()
    if len(normalised_quote) < MIN_QUOTE_CHARACTERS or not document.offsets:
        return None

    position = document.value.find(normalised_quote)
    if position == -1:
        return None

    last = len(document.offsets) - 1
    start = document.offsets[min(position, last)]
    stop_index = min(position + len(normalised_quote) - 1, last)
    end = min(original_length, document.offsets[stop_index] + 1)
    return SourceSpan(start=start, end=end) if end > start else None


class ClauseAnalysisService:
    """Produces a verified, plain-language analysis of a stored document."""

    def __init__(self, *, llm: LlmProvider, redact_pii: bool) -> None:
        """Wire the model provider and the redaction policy."""
        self._llm = llm
        self._redact_pii = redact_pii

    async def analyse(self, document: StoredDocument) -> DocumentAnalysis:
        """Analyse ``document``, returning only findings grounded in its text.

        Args:
            document: The indexed document to analyse.

        Returns:
            The verified analysis.

        Raises:
            LlmUnavailableError: If the model reply fails schema validation.
        """
        redaction = redact(document.text, enabled=self._redact_pii)
        payload = await self._llm.generate_json(
            system_instruction=ANALYSIS_SYSTEM_INSTRUCTION,
            prompt=build_analysis_prompt(filename=document.filename, document_text=redaction.text),
            response_schema=json_schema_for(AnalysisPayload),
        )

        try:
            parsed = AnalysisPayload.model_validate(payload)
        except ValidationError as exc:
            raise LlmUnavailableError(
                "The analysis could not be completed. Please try again.",
                detail=f"Model reply failed schema validation with {exc.error_count()} errors.",
            ) from exc

        verified, discarded = self._verify_findings(parsed.findings, document, redaction.restore)

        if discarded:
            _logger.info(
                "findings_discarded_unverified",
                document_id=document.document_id,
                discarded=discarded,
                retained=len(verified),
            )

        restore = redaction.restore
        return DocumentAnalysis(
            document_id=document.document_id,
            document_type=restore(parsed.document_type),
            parties=[restore(party) for party in parsed.parties],
            plain_language_summary=restore(parsed.plain_language_summary),
            key_dates=[restore(date) for date in parsed.key_dates],
            findings=verified,
            obligations=[
                item.model_copy(
                    update={
                        "who": restore(item.who),
                        "what": restore(item.what),
                        "when": restore(item.when),
                    }
                )
                for item in parsed.obligations
            ],
            questions_for_a_lawyer=[
                restore(question) for question in parsed.questions_for_a_lawyer
            ],
            unverified_finding_count=discarded,
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _verify_findings(
        findings: list[ClauseFinding],
        document: StoredDocument,
        restore: Callable[[str], str],
    ) -> tuple[list[ClauseFinding], int]:
        """Keep only findings whose quote is present in the document text.

        Args:
            findings: The findings as returned by the model.
            document: The document the quotes must be found in.
            restore: Callable that reverses PII redaction on model output.

        Returns:
            The verified findings, ordered by risk, and the number discarded.
        """
        normalised = normalise_for_matching(document.text)
        verified: list[ClauseFinding] = []
        discarded = 0

        for finding in findings:
            span = locate_quote(
                restore(finding.quote), normalised, original_length=len(document.text)
            )
            if span is None:
                discarded += 1
                continue
            verified.append(
                finding.model_copy(
                    update={
                        # Replace the model's rendering of the quote with the
                        # document's own bytes, so the UI highlight and the
                        # displayed text are guaranteed to agree.
                        "quote": document.text[span.start : span.end],
                        "plain_language": restore(finding.plain_language),
                        "why_it_matters": restore(finding.why_it_matters),
                        "source": span,
                    }
                )
            )

        verified.sort(key=lambda item: _RISK_ORDER.index(item.risk))
        return verified, discarded
