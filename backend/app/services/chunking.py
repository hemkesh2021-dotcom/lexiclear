"""Structure-aware splitting of a legal document into retrievable chunks.

Naive fixed-width splitting cuts through the middle of clauses, which produces
citations that begin mid-sentence and answers that miss the operative verb.  The
splitter here works in three passes:

#. Detect clause headings (``7.`` , ``7.1`` , ``ARTICLE IV``, ``Section 12``)
   and treat each as a hard boundary, so a clause is never merged with its
   neighbour.
#. Pack paragraphs inside a clause up to a target character budget.
#. Split any single oversized paragraph on sentence boundaries, with a small
   overlap so a sentence spanning a boundary is still retrievable.

Every chunk keeps the character offsets it occupies in the source text, which is
what lets the user interface highlight the exact passage a finding came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

#: Clause headings seen across contracts, policies and statutory instruments.
_HEADING_PATTERN = re.compile(
    r"^\s*("
    r"(?:ARTICLE|SECTION|CLAUSE|SCHEDULE|ANNEXURE|APPENDIX|PART)\s+[IVXLC\d]+[.:）)]?"
    r"|\d{1,2}(?:\.\d{1,2}){0,3}[.)]?\s+[A-Z]"
    r"|[A-Z][A-Z \-&,']{6,80}$"
    r")",
    re.MULTILINE,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.;:!?])\s+")

#: A numbered or named clause reference at the very start of a segment.
_CLAUSE_REFERENCE = re.compile(
    r"^\s*(?:(?P<named>ARTICLE|SECTION|CLAUSE|SCHEDULE|ANNEXURE|APPENDIX|PART)\s+"
    r"(?P<named_number>[IVXLC]+|\d+(?:\.\d+)*)|(?P<number>\d{1,2}(?:\.\d{1,2}){0,3})(?=[.)]?\s+[A-Z]))"
)

#: An all-capitals title line, the other common heading style in contracts.
_TITLE_HEADING = re.compile(r"^\s*([A-Z][A-Z \-&,\']{5,60})\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable passage and its position in the source document."""

    index: int
    text: str
    start_offset: int
    end_offset: int
    heading: str | None

    @property
    def citation_label(self) -> str:
        """Short human-readable label used in citations."""
        return self.heading or f"Passage {self.index + 1}"


#: A segment shorter than this is a bare section heading such as
#: ``"4. TERMINATION"``.  On its own it retrieves nothing useful, so it is
#: merged into the clause that follows it, where it adds helpful context.
MIN_SEGMENT_CHARACTERS = 120


def _segment_boundaries(text: str) -> list[int]:
    """Return sorted start offsets of clause-level segments."""
    offsets = {0}
    for match in _HEADING_PATTERN.finditer(text):
        offsets.add(match.start())
    offsets.add(len(text))
    return sorted(offsets)


def _segments(text: str) -> list[tuple[int, int]]:
    """Split ``text`` into ``(start, end)`` clause segments, merging stubs.

    Args:
        text: The normalised document text.

    Returns:
        Segment ranges, with bare heading lines folded into the clause below.
    """
    boundaries = _segment_boundaries(text)
    ranges = [(start, end) for start, end in pairwise(boundaries) if text[start:end].strip()]

    merged: list[tuple[int, int]] = []
    pending_start: int | None = None
    for start, end in ranges:
        effective_start = pending_start if pending_start is not None else start
        if len(text[effective_start:end].strip()) < MIN_SEGMENT_CHARACTERS:
            pending_start = effective_start
            continue
        merged.append((effective_start, end))
        pending_start = None

    if pending_start is not None and ranges:
        merged.append((pending_start, ranges[-1][1]))
    return merged


def _sentence_spans(span: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` ranges of the sentences in ``span``."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _SENTENCE_BOUNDARY.finditer(span):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(span)))
    return [(start, end) for start, end in spans if span[start:end].strip()]


def _split_long_span(span: str, *, target: int, overlap: int) -> list[tuple[int, int]]:
    """Split an oversized span on sentence boundaries, with overlap.

    Offsets are returned rather than text, so the caller can slice the source
    itself. That is what guarantees a chunk's recorded range always addresses
    exactly the chunk's own text - the property the citation highlighting in the
    user interface depends on.

    Args:
        span: The text to split.
        target: Target chunk size in characters.
        overlap: Maximum length of a trailing sentence repeated in the next
            chunk, so a sentence answering a question is never orphaned by a
            boundary falling immediately before it.

    Returns:
        ``(start, end)`` ranges into ``span``, in order.
    """
    sentences = _sentence_spans(span)
    if not sentences:
        return []

    pieces: list[tuple[int, int]] = []
    current_start, current_end = sentences[0]
    previous = sentences[0]

    for start, end in sentences[1:]:
        if end - current_start > target:
            pieces.append((current_start, current_end))
            repeat_previous = overlap > 0 and (previous[1] - previous[0]) <= overlap
            current_start = previous[0] if repeat_previous else start
            current_end = end
        else:
            current_end = end
        previous = (start, end)

    pieces.append((current_start, current_end))
    return pieces


def derive_heading(segment: str) -> str | None:
    """Derive a short citation label for a clause segment.

    A citation reading ``[Clause 6.2]`` is useful; one reading ``[6.2 The
    Landlord shall not be liable to the Tenant for any loss...]`` is not.  The
    label is therefore reduced to a clause reference or a short title, and
    falls back to ``None`` when neither is present.

    Args:
        segment: The segment text, starting at its heading if it has one.

    Returns:
        A short label such as ``"Clause 6.2"``, or ``None``.
    """
    reference = _CLAUSE_REFERENCE.match(segment)
    if reference is not None:
        named = reference.group("named")
        if named:
            return f"{named.capitalize()} {reference.group('named_number')}"
        return f"Clause {reference.group('number')}"

    title = _TITLE_HEADING.match(segment)
    if title is not None:
        return title.group(1).strip().title()
    return None


def chunk_document(text: str, *, target_characters: int, overlap_characters: int) -> list[Chunk]:
    """Split ``text`` into offset-tracked, clause-aware chunks.

    Args:
        text: The normalised document text.
        target_characters: Soft upper bound on chunk length.
        overlap_characters: Characters repeated between adjacent chunks.

    Returns:
        The chunks, ordered by position in the document.
    """
    if not text.strip():
        return []

    chunks: list[Chunk] = []

    for start, end in _segments(text):
        segment = text[start:end]
        heading = derive_heading(segment)

        pieces = (
            [(0, len(segment))]
            if len(segment) <= target_characters
            else _split_long_span(segment, target=target_characters, overlap=overlap_characters)
        )

        for relative_start, relative_end in pieces:
            raw = text[start + relative_start : start + relative_end]
            body = raw.strip()
            if not body:
                continue
            offset = start + relative_start + (len(raw) - len(raw.lstrip()))
            chunks.append(
                Chunk(
                    index=len(chunks),
                    text=body,
                    start_offset=offset,
                    end_offset=offset + len(body),
                    heading=heading,
                )
            )

    return chunks
