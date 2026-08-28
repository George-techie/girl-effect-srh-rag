"""Deterministic citation rendering and validation.

The model emits opaque tags ([S1], [S2]) and never writes source names. Titles,
publishers, years and page numbers are attached here from chunk metadata, which
makes a fabricated citation structurally impossible: a tag either maps to a
passage that was actually retrieved, or it is rejected.

`validate` returns the numbers the evaluation reports as citation support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from src.rag.retriever import RetrievedChunk

_TAG_RE = re.compile(r"\[S(\d+)\]")
INSUFFICIENT_TOKEN = "INSUFFICIENT_CONTEXT"


@dataclass
class Citation:
    marker: str
    source_id: str
    title: str
    publisher: str
    year: int
    page: int
    section_title: str
    excerpt: str

    @property
    def label(self) -> str:
        return f"{self.title} ({self.publisher}, {self.year}), p.{self.page}"


@dataclass
class CitedAnswer:
    text: str
    citations: list[Citation]
    insufficient: bool
    invalid_markers: list[str]
    uncited_sentences: list[str]

    @property
    def citation_count(self) -> int:
        return len(self.citations)


def extract_markers(text: str) -> list[int]:
    """Ordered, de-duplicated [Sn] indices appearing in the text."""
    seen: list[int] = []
    for match in _TAG_RE.finditer(text):
        index = int(match.group(1))
        if index not in seen:
            seen.append(index)
    return seen


def _sentences(text: str) -> list[str]:
    stripped = _TAG_RE.sub("", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", stripped) if s.strip()]


def build(
    answer_text: str,
    chunks: Sequence[RetrievedChunk],
    *,
    excerpt_chars: int = 320,
) -> CitedAnswer:
    """Attach citations to a generated answer and report grounding problems."""
    text = answer_text.strip()

    insufficient = text.upper().startswith(INSUFFICIENT_TOKEN)
    if insufficient:
        # Strip the control token; it is machinery, not something a user reads.
        text = text[len(INSUFFICIENT_TOKEN) :].lstrip(" :\n-")

    citations: list[Citation] = []
    invalid: list[str] = []

    for index in extract_markers(text):
        if not 1 <= index <= len(chunks):
            # A tag pointing at a passage that was never retrieved.
            invalid.append(f"[S{index}]")
            continue
        chunk = chunks[index - 1]
        meta = chunk.metadata
        citations.append(
            Citation(
                marker=f"[S{index}]",
                source_id=chunk.source_id,
                title=str(meta.get("title", "?")),
                publisher=str(meta.get("publisher", "?")),
                year=int(meta.get("publication_year", 0) or 0),
                page=chunk.page,
                section_title=chunk.section_title,
                excerpt=chunk.text[:excerpt_chars].strip(),
            )
        )

    # Sentences carrying a factual claim but no marker. Short sentences and
    # questions are excluded — "That's a really common worry." needs no source.
    uncited: list[str] = []
    if not insufficient:
        for raw in re.split(r"(?<=[.!?])\s+", text):
            sentence = raw.strip()
            if not sentence or _TAG_RE.search(sentence):
                continue
            if len(sentence.split()) >= 8 and not sentence.endswith("?"):
                uncited.append(sentence)

    return CitedAnswer(
        text=text,
        citations=citations,
        insufficient=insufficient,
        invalid_markers=invalid,
        uncited_sentences=uncited,
    )


def strip_markers(text: str) -> str:
    """Remove [Sn] tags for display surfaces that show sources separately."""
    return re.sub(r"\s*\[S\d+\]", "", text).strip()


def render_sources_block(citations: Sequence[Citation]) -> str:
    """De-duplicated source list shown beneath an answer."""
    seen: dict[tuple[str, int], Citation] = {}
    for citation in citations:
        seen.setdefault((citation.source_id, citation.page), citation)
    lines = [f"- {c.label}" for c in seen.values()]
    return "\n".join(lines)
