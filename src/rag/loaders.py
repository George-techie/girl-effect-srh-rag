"""PDF loading with structure recovery.

Only one document in the corpus ships an embedded outline, so section structure
has to be inferred. PyMuPDF exposes per-span font size and weight, which is
enough to separate headings from body text: a heading is a short line rendered
noticeably larger than the document's dominant body size, or rendered bold.

Recovering headings matters for retrieval quality in two ways. It keeps
semantically coherent sections together instead of splitting mid-explanation,
and it gives every chunk a `section_title` that can be shown to the user as
part of the citation.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import fitz

from src.rag import cleaning
from src.rag.registry import Source


@dataclass
class Block:
    """A run of text from one page, tagged as heading or body."""

    text: str
    page: int          # 1-indexed PDF page
    size: float        # dominant font size
    is_heading: bool
    is_bold: bool


@dataclass
class Section:
    """A heading and the body text beneath it."""

    title: str
    text: str
    page_start: int
    page_end: int
    source_id: str


_SENTENCE_END_RE = re.compile(r"[.!?:]\s*$")
# Designed layouts often place a page or question number inside the heading box.
_TRAILING_NUMBER_RE = re.compile(r"\s+\d{1,3}$")


def _strip_trailing_page_number(text: str) -> str:
    return _TRAILING_NUMBER_RE.sub("", text) if not text.rstrip().isdigit() else text


def _spans_to_blocks(page: fitz.Page, page_no: int) -> list[Block]:
    """Group a page's text into paragraph-level blocks with font metadata.

    PyMuPDF's `dict` output nests spans inside lines inside blocks, where a
    block is roughly a paragraph. Classification happens at paragraph level:
    testing individual lines misreads any document that sets body copy in bold
    or in a large face, which several sources here do.
    """
    blocks: list[Block] = []
    # `sort=True` orders blocks by position rather than content-stream order.
    # Without it, the designed booklets return answers before their questions,
    # which silently detaches body text from the heading it belongs to.
    data = page.get_text("dict", sort=True)

    for block in data.get("blocks", []):
        if block.get("type") != 0:  # skip images
            continue

        lines: list[str] = []
        weighted_size = 0.0
        bold_chars = 0
        total_chars = 0

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(s.get("text", "") for s in spans).strip()
            if not line_text:
                continue
            lines.append(line_text)
            for span in spans:
                chars = len(span.get("text", ""))
                if not chars:
                    continue
                total_chars += chars
                weighted_size += span.get("size", 0) * chars
                is_bold = "bold" in str(span.get("font", "")).lower() or bool(
                    span.get("flags", 0) & 2**4
                )
                if is_bold:
                    bold_chars += chars

        if not lines or not total_chars:
            continue

        blocks.append(
            Block(
                # Newline-joined so hyphenated line breaks can be repaired.
                text="\n".join(lines),
                page=page_no,
                size=round(weighted_size / total_chars, 1),
                is_heading=False,
                is_bold=bold_chars / total_chars > 0.6,
            )
        )
    return blocks


def _body_size(blocks: list[Block]) -> float:
    """The document's dominant font size, weighted by text volume."""
    weights: Counter[float] = Counter()
    for b in blocks:
        weights[b.size] += len(b.text)
    return weights.most_common(1)[0][0] if weights else 10.0


def _mark_headings(blocks: list[Block], body: float) -> None:
    """Flag paragraph blocks that look like section headings.

    A heading is short, and is set apart either by size, by weight, or by being
    numbered. Multi-paragraph and sentence-shaped blocks are excluded regardless
    of styling, which is what stops bold body copy being read as structure.
    """
    for b in blocks:
        # Display headings are frequently set large and wrap over several lines,
        # so measure the collapsed text rather than the laid-out lines.
        text = _strip_trailing_page_number(" ".join(b.text.split()))
        words = len(text.split())

        # Youth Q&A booklets ask questions in her words, and those run long:
        # "I feel embarrassed and ashamed when my friends shout sexual comments
        # at girls on the street; how can I get them to stop?" is 23 words and
        # is unmistakably the heading of the answer beneath it.
        #
        # A flat 20-word cap dropped every such question before the question
        # rule below could see it, and one source lost its whole structure --
        # 2 sections out of 17 pages, where its siblings gave 12 and 17. The
        # answers survived; what was lost was knowing which question they
        # answered, which is the only reason a Q&A source is worth having.
        is_question = text.rstrip().endswith("?")
        if not text or words > (32 if is_question else 20) or words < 2:
            continue

        # A heading starts a thought. Text beginning mid-sentence is a
        # continuation fragment from a column or page break — several were
        # otherwise promoted to headings ("you this.", "was feeling?"),
        # which corrupts both the citation label and the embedded title prefix.
        if not re.match(r"^[A-Z0-9\"'(\[]", text):
            continue

        # A face several points above body copy is a heading whatever its
        # length or line count — this is what recovers the wrapped display
        # questions that organise the UNICEF Q&A booklet.
        display = b.size >= body + 2.5

        # The weaker signals are only trusted for genuinely short, single-run
        # blocks, otherwise bold body copy is misread as structure.
        if not display and b.text.count("\n") >= 2:
            continue

        looks_like_sentence = bool(_SENTENCE_END_RE.search(text)) and words > 5

        larger = b.size >= body + 0.9
        bold_standalone = b.is_bold and words <= 12
        numbered = bool(re.match(r"^\d+(\.\d+)*[\s.)-]+\S", text))
        question = is_question

        if display or question or (
            (larger or bold_standalone or numbered) and not looks_like_sentence
        ):
            b.is_heading = True
            b.text = text


def load_blocks(source: Source) -> list[Block]:
    """Extract cleaned, heading-tagged blocks from a source's included pages."""
    raw_pages: dict[int, str] = {}
    page_blocks: dict[int, list[Block]] = {}

    with fitz.open(source.path) as doc:
        # Header detection needs the whole document, not just included pages,
        # so repeated furniture is measured against a full sample.
        sample = range(len(doc))
        for i in sample:
            raw_pages[i + 1] = doc[i].get_text()

        headers = cleaning.find_running_headers(raw_pages.values())

        # An empty page list means the whole document. The previous corpus
        # needed hand-picked ranges to keep facilitator material out; every
        # source here is ingested entire, and an empty set must not silently
        # mean "no pages".
        wanted = set(source.pages()) or set(range(1, len(doc) + 1))

        for page_no in sorted(wanted):
            if page_no > len(doc):
                continue
            blocks = _spans_to_blocks(doc[page_no - 1], page_no)
            page_blocks[page_no] = blocks

    all_blocks = [b for page in sorted(page_blocks) for b in page_blocks[page]]
    if not all_blocks:
        return []

    # Normalise before classifying: hyphen repair and ligature fixes change the
    # word counts and line counts the heading heuristics depend on.
    kept: list[Block] = []
    for b in all_blocks:
        key = re.sub(r"\d+", "#", " ".join(b.text.split()))
        if key in headers or cleaning.is_noise_line(b.text):
            continue
        b.text = cleaning.normalise(b.text)
        if b.text:
            kept.append(b)

    if not kept:
        return []

    _mark_headings(kept, _body_size(kept))
    return kept


def build_sections(source: Source, blocks: list[Block]) -> list[Section]:
    """Assemble heading-led sections from a block stream.

    Body text appearing before the first heading is kept under a synthetic
    title so no content is silently dropped.
    """
    sections: list[Section] = []
    title = ""
    buffer: list[str] = []
    page_start = blocks[0].page if blocks else 0
    page_end = page_start

    def flush() -> None:
        nonlocal buffer, title, page_start, page_end
        body = cleaning.collapse_whitespace("\n".join(buffer))
        if body:
            sections.append(
                Section(
                    title=title or f"{source.title} (p.{page_start})",
                    text=body,
                    page_start=page_start,
                    page_end=page_end,
                    source_id=source.source_id,
                )
            )
        buffer = []

    for block in blocks:
        if block.is_heading:
            flush()
            title = block.text
            page_start = block.page
            page_end = block.page
        else:
            if not buffer:
                page_start = block.page
            buffer.append(block.text)
            page_end = block.page

    flush()
    return _drop_excluded(source, sections)


def _drop_excluded(source: Source, sections: list[Section]) -> list[Section]:
    """Apply the per-source exclusion list from the registry.

    This is where "exclude facilitator logistics" stops being a comment and
    becomes an enforced ingestion rule.
    """
    if not source.drop_headings:
        return sections
    patterns = tuple(p.lower() for p in source.drop_headings)
    kept = []
    for section in sections:
        haystack = f"{section.title}\n{section.text[:200]}".lower()
        if any(p in haystack for p in patterns):
            continue
        kept.append(section)
    return kept


def load_sections(source: Source) -> list[Section]:
    return build_sections(source, load_blocks(source))
