"""Corpus sanity checks.

These do not test retrieval quality -- that needs a question set and human
judgement. They test the things that can silently go wrong during ingestion and
would poison everything downstream: a source that never made it in, a chunk with
no provenance, text corrupted by a font encoding.

Run: pytest tests/ -q
"""

from __future__ import annotations

import json

import pytest

from src import config
from src.rag import registry

EXPECTED = {
    "KE_FAQ", "KE_FPG", "WHO_HB", "WHO_EMP",
    "UNFPA_SWP", "UNICEF_HIV", "UNICEF_SAFE", "UNICEF_PARENT",
}


@pytest.fixture(scope="module")
def chunks() -> list[dict]:
    if not config.CHUNKS_FILE.exists():
        pytest.skip("no chunks.jsonl — run scripts/ingest.py --dry-run")
    return [json.loads(line) for line in config.CHUNKS_FILE.open(encoding="utf-8")]


class TestRegistry:

    def test_all_eight_sources_registered(self):
        assert {s.source_id for s in registry.load()} == EXPECTED

    def test_every_pdf_is_present_and_valid(self):
        assert registry.validate() == []

    def test_every_source_has_a_citation_tag(self):
        """The tag is what a girl sees under an answer. A blank one reaches the
        UI as an empty bracket, and a filename reaches it as noise."""
        for s in registry.load():
            assert s.citation_tag and "·" in s.citation_tag, s.source_id
            assert not s.citation_tag.endswith(".pdf")

    def test_provider_guidance_is_marked_as_such(self):
        """Two sources are written for clinicians, not for her. Nothing filters
        on this yet, but it has to be recorded now or the distinction is
        unrecoverable later without re-ingesting."""
        provider = {s.source_id for s in registry.load() if s.is_provider_facing}
        assert provider == {"WHO_HB", "KE_FPG"}


class TestChunks:

    def test_every_source_reached_the_index(self, chunks):
        assert {c["source_id"] for c in chunks} == EXPECTED

    def test_every_chunk_carries_its_provenance(self, chunks):
        for c in chunks:
            for field in ("source_id", "citation_tag", "page_pdf",
                          "section_title", "domains", "document_role"):
                assert c.get(field) not in (None, ""), f"{c['chunk_id']}: {field}"

    def test_no_chunk_is_empty(self, chunks):
        assert all(c["text"].strip() for c in chunks)

    def test_no_chunk_exceeds_the_encoder_cap(self, chunks):
        """Over the cap, bge-m3 truncates silently and the tail of the passage
        is embedded as though it does not exist."""
        over = [c["chunk_id"] for c in chunks
                if c["token_count"] > config.CHUNK_MAX_TOKENS]
        assert not over, over[:5]

    def test_categories_are_from_the_agreed_list(self, chunks):
        for c in chunks:
            for d in c["domains"].split("|"):
                assert d in config.DOMAINS, f"{c['chunk_id']}: {d}"


class TestExtractionQuality:

    def test_the_kenya_faq_ligatures_were_repaired(self, chunks):
        """That PDF encodes ti/ft/tt ligatures at Latin Extended-B codepoints,
        so raw extraction gives "Ɵme", "aŌer", "breasƞeeding". Left in, it
        corrupts the only Kenyan youth-facing source -- and quietly, because the
        result still looks like words."""
        text = " ".join(c["text"] for c in chunks if c["source_id"] == "KE_FAQ")
        for glyph in "ƟŌƩƫƞ":
            assert glyph not in text, f"unrepaired ligature {glyph!r}"
        assert "time" in text and "after" in text

    def test_the_youth_qa_kept_its_questions_as_section_titles(self, chunks):
        """A Q&A source is only worth having if a retrieved answer still knows
        which question it answers. Questions run long in her own words, and a
        20-word heading cap was dropping them into the body."""
        titles = [c["section_title"] for c in chunks
                  if c["source_id"] in {"UNICEF_PARENT", "UNICEF_HIV", "KE_FAQ"}]
        assert sum(t.rstrip().endswith("?") for t in titles) >= 10


class TestIndex:

    def test_chroma_holds_exactly_what_was_chunked(self, chunks):
        from src.rag import indexing
        try:
            collection = indexing.get_collection()
        except Exception:
            pytest.skip("no index — run scripts/ingest.py")
        assert collection.count() == len(chunks)

    def test_query_embedding_matches_the_stored_dimension(self):
        from src.rag import indexing
        try:
            collection = indexing.get_collection()
        except Exception:
            pytest.skip("no index — run scripts/ingest.py")
        stored = collection.get(limit=1, include=["embeddings"])["embeddings"][0]
        assert len(indexing.embed_query("contraception")) == len(stored)
