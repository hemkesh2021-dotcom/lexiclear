"""Reversible redaction of direct identifiers before text leaves the process.

Legal documents routinely carry government identifiers, account numbers and
contact details.  None of that is needed for the model to explain a clause, so
each match is replaced by a stable placeholder (``[PAN_1]``) before the text is
sent upstream, and the mapping is kept in memory only for the duration of the
request so the answer can be rendered back with the original values.

This is a *defence in depth* measure, not a compliance guarantee: it reduces the
identifiers exposed to a third-party model, and it is disabled by a single
setting for operators whose own policy differs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Order matters. Patterns are applied in sequence, so the longest and most
#: specific identifiers are matched first: a sixteen-digit card number would
#: otherwise be partly consumed by the twelve-digit Aadhaar pattern, leaving
#: four digits of it in the clear.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+\d{1,3}[ -]?)?\d{10}(?!\w)")),
)


@dataclass(slots=True)
class RedactionResult:
    """Redacted text plus the placeholder-to-original mapping."""

    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    def restore(self, text: str) -> str:
        """Substitute original values back into model output.

        Args:
            text: Text that may contain redaction placeholders.

        Returns:
            The text with every known placeholder replaced by its original value.
        """
        for placeholder, original in self.mapping.items():
            text = text.replace(placeholder, original)
        return text


def redact(text: str, *, enabled: bool = True) -> RedactionResult:
    """Replace direct identifiers in ``text`` with stable placeholders.

    Args:
        text: The text to scan.
        enabled: When ``False`` the text is returned untouched, which keeps the
            call site free of conditionals.

    Returns:
        A :class:`RedactionResult` holding the redacted text and its mapping.
    """
    if not enabled or not text:
        return RedactionResult(text=text)

    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}
    counters: dict[str, int] = {}

    def _replace(label: str, match: re.Match[str]) -> str:
        original = match.group(0)
        if original in reverse:
            return reverse[original]
        counters[label] = counters.get(label, 0) + 1
        placeholder = f"[{label}_{counters[label]}]"
        mapping[placeholder] = original
        reverse[original] = placeholder
        return placeholder

    redacted = text
    for label, pattern in _PATTERNS:
        redacted = pattern.sub(lambda m, label=label: _replace(label, m), redacted)  # type: ignore[misc]

    return RedactionResult(text=redacted, mapping=mapping)
