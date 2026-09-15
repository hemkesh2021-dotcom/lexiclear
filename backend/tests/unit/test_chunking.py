"""Chunks follow clause boundaries and keep offsets that index the source."""

from app.services.chunking import MIN_SEGMENT_CHARACTERS, chunk_document, derive_heading


def split(text: str):
    return chunk_document(text, target_characters=1600, overlap_characters=200)


class TestOffsetIntegrity:
    def test_every_chunk_offset_addresses_its_own_text(self, contract_text):
        for chunk in split(contract_text):
            assert contract_text[chunk.start_offset : chunk.end_offset] == chunk.text

    def test_chunks_are_ordered_and_indexed_consecutively(self, contract_text):
        chunks = split(contract_text)
        assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
        offsets = [chunk.start_offset for chunk in chunks]
        assert offsets == sorted(offsets)

    def test_empty_input_yields_nothing(self):
        assert split("") == []
        assert split("   \n\n  ") == []


class TestClauseAwareness:
    def test_numbered_clauses_become_separate_chunks(self, contract_text):
        labels = {chunk.citation_label for chunk in split(contract_text)}
        assert "Clause 4.2" in labels
        assert "Clause 6.2" in labels

    def test_a_clause_is_not_split_across_chunks(self, contract_text):
        # Clause 4.2 is the tenant's termination right; it must stay whole so a
        # citation to it carries the whole obligation.
        chunks = split(contract_text)
        clause = next(c for c in chunks if c.citation_label == "Clause 4.2")
        assert "three (3) months written" in clause.text
        assert "forfeit the entire security deposit" in clause.text

    def test_bare_headings_are_folded_into_the_clause_below(self, contract_text):
        for chunk in split(contract_text):
            assert len(chunk.text) >= MIN_SEGMENT_CHARACTERS or chunk.index == 0

    def test_oversized_paragraphs_are_split_on_sentence_boundaries(self):
        sentence = "The Tenant shall observe every covenant set out in this Agreement. "
        chunks = chunk_document(sentence * 80, target_characters=400, overlap_characters=50)
        assert len(chunks) > 1
        assert all(len(chunk.text) < 900 for chunk in chunks)


class TestHeadingDerivation:
    def test_numbered_references_are_shortened(self):
        assert derive_heading("7.2 The Landlord shall maintain the roof.") == "Clause 7.2"

    def test_named_sections_are_recognised(self):
        assert derive_heading("ARTICLE IV Payment terms follow.") == "Article IV"
        assert derive_heading("SECTION 12 Governing law.") == "Section 12"

    def test_all_capitals_titles_become_title_case(self):
        assert derive_heading("RESIDENTIAL RENTAL AGREEMENT\n\nThis is made...") == (
            "Residential Rental Agreement"
        )

    def test_ordinary_prose_has_no_heading(self):
        assert derive_heading("The parties agree as follows, without more.") is None
