"""Clause-analysis schemas.

The JSON Schema handed to the model is derived from these Pydantic models via
:func:`app.services.prompts.json_schema_for`, so the contract the model is
constrained to and the contract the API validates against cannot drift apart.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.common import ApiModel


class RiskLevel(StrEnum):
    """How much attention a finding warrants from a non-lawyer reader."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ClauseCategory(StrEnum):
    """The functional role a clause plays in an agreement."""

    PAYMENT = "payment"
    TERMINATION = "termination"
    AUTO_RENEWAL = "auto_renewal"
    LIABILITY = "liability"
    INDEMNITY = "indemnity"
    CONFIDENTIALITY = "confidentiality"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DATA_PRIVACY = "data_privacy"
    DISPUTE_RESOLUTION = "dispute_resolution"
    RESTRICTIVE_COVENANT = "restrictive_covenant"
    OBLIGATION = "obligation"
    OTHER = "other"


class SourceSpan(ApiModel):
    """Character range in the source text backing a finding."""

    start: int = Field(ge=0, description="Inclusive start offset in the document text.")
    end: int = Field(ge=0, description="Exclusive end offset in the document text.")


class ClauseFinding(ApiModel):
    """One clause the reader should know about, grounded in a verified quote."""

    title: str = Field(description="Short label for the clause, in plain language.")
    category: ClauseCategory = Field(description="Functional role of the clause.")
    risk: RiskLevel = Field(description="How much attention the clause warrants.")
    plain_language: str = Field(description="What the clause means, without legal jargon.")
    why_it_matters: str = Field(description="The practical consequence for the reader.")
    quote: str = Field(description="Verbatim text from the document supporting the finding.")
    source: SourceSpan | None = Field(
        default=None, description="Where the quote sits in the document text."
    )


class ObligationItem(ApiModel):
    """A concrete action the reader is required to take."""

    who: str = Field(description="The party responsible.")
    what: str = Field(description="The action required.")
    when: str = Field(description="The deadline or trigger, or 'Not specified'.")


class DocumentAnalysis(ApiModel):
    """The complete analysis of one document."""

    document_id: str = Field(description="Handle of the analysed document.")
    document_type: str = Field(description="Best-effort classification, e.g. 'Lease agreement'.")
    parties: list[str] = Field(description="Named parties to the document.")
    plain_language_summary: str = Field(description="The document explained in plain language.")
    key_dates: list[str] = Field(description="Dates, durations and notice periods that matter.")
    findings: list[ClauseFinding] = Field(description="Clauses the reader should know about.")
    obligations: list[ObligationItem] = Field(description="Actions the reader must take.")
    questions_for_a_lawyer: list[str] = Field(
        description="Specific questions to raise with a qualified professional."
    )
    unverified_finding_count: int = Field(
        default=0,
        description="Findings discarded because their quote was not present in the document.",
    )
    disclaimer: str = Field(description="Notice that this is information, not legal advice.")
