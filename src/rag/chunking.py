"""Section-to-chunk splitting.

Blueprint §7.2: prefer coherent semantic units over fixed-size chopping, and
split only at sentence boundaries. A section that already fits the target size
is emitted whole — most of the UNICEF Q&A booklet's question/answer pairs land
here, which is exactly the intent, since splitting an answer from its question
destroys the thing that makes that source valuable.

Every chunk keeps its section title as a prefix. This is a deliberate retrieval
choice: it gives the embedding topical anchoring that a mid-section fragment
would otherwise lack, and it means the retrieved text a reviewer reads is
self-describing.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import tiktoken

from src import config
from src.rag.loaders import Section
from src.rag.registry import Source

# Split on sentence enders followed by whitespace and a capital/digit/quote.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(A-Z0-9])")

_tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
_embedding_tokenizer = None


def _get_embedding_tokenizer():
    """The tokenizer the embedding model itself will use.

    Chunks were previously sized with tiktoken while being embedded by an
    XLM-R-based model. The two disagree — XLM-R ran about 5% longer on this
    corpus and peaked at 702 tokens against a 650-token tiktoken budget — so
    chunks silently overflowed the encoder's context and had their tails
    dropped. Measuring with the encoder's own tokenizer removes the mismatch
    rather than leaving a margin and hoping.
    """
    global _embedding_tokenizer
    if _embedding_tokenizer is None:
        try:
            from transformers import AutoTokenizer

            _embedding_tokenizer = AutoTokenizer.from_pretrained(
                config.EMBEDDING_MODEL
            )
        except Exception:  # noqa: BLE001 - fall back rather than block ingestion
            _embedding_tokenizer = False
    return _embedding_tokenizer or None


def count_tokens(text: str) -> int:
    """Token count as the *embedding model* sees it, with a tiktoken fallback."""
    tokenizer = _get_embedding_tokenizer()
    if tokenizer is not None:
        return len(tokenizer.encode(text, add_special_tokens=True))
    return len(_tiktoken_encoder.encode(text))


def embedding_context_limit() -> int:
    """The embedding model's usable sequence length.

    Chunks are capped below this so that no passage is ever truncated at
    embedding time. bge-m3 allows 8192; multilingual-e5-* allow 512.
    """
    override = os.getenv("EMBEDDING_MAX_TOKENS")
    if override:
        return int(override)

    name = config.EMBEDDING_MODEL.lower()
    if "bge-m3" in name:
        return 8192
    if "e5" in name or "minilm" in name or "mpnet" in name:
        return 512
    try:
        from sentence_transformers import SentenceTransformer

        return int(SentenceTransformer(config.EMBEDDING_MODEL).max_seq_length)
    except Exception:  # noqa: BLE001
        return 512  # the safe assumption when the limit is unknown


def effective_max_tokens() -> int:
    """Chunk ceiling: the configured maximum, never above what the encoder reads.

    Reserves a small margin for the special tokens and any instruction prefix
    the model prepends.
    """
    return min(config.CHUNK_MAX_TOKENS, embedding_context_limit() - 16)


def effective_target_tokens() -> int:
    return min(config.CHUNK_TARGET_TOKENS, effective_max_tokens())


@dataclass
class Chunk:
    """One indexed passage and its full provenance."""

    chunk_id: str
    text: str
    source_id: str
    title: str
    citation_tag: str
    section_title: str
    domain: str
    domains: str            # pipe-joined; Chroma metadata must be scalar
    document_role: str
    page_pdf: int
    page_end: int
    publisher: str
    publication_year: int
    country_scope: str
    audience: str
    permission_status: str
    corpus_version: str
    token_count: int
    chunk_index: int = 0

    def metadata(self) -> dict[str, Any]:
        meta = asdict(self)
        meta.pop("text")

        # One boolean per domain, because Chroma cannot match inside a string.
        # `domains` is stored pipe-joined for display, and filtering on it with
        # $eq only matched a source whose domains were exactly one value — so a
        # chunk tagged "stress_anxiety|professional_help" was unreachable when
        # filtering for professional_help. No source has professional_help as
        # its *primary* domain, so that track returned zero chunks and every
        # help-seeking question was refused despite the evidence existing.
        for domain in config.DOMAINS:
            meta[f"in_{domain}"] = domain in self.domains.split("|")
        return meta

    @property
    def citation_label(self) -> str:
        """What the UI shows beneath an answer.

        The registry's citation tag, not the document title. "WHO · Contraception
        Clinical Guide" tells her which authority answered; "family-planning-a-
        global-handbook-for-providers-2022" tells her nothing.
        """
        return f"{self.citation_tag} · p.{self.page_pdf}"


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _split_oversized(sentence: str, hard_max: int) -> list[str]:
    """Word-split a single sentence that alone exceeds the encoder's limit.

    Rare, but real: run-on bulleted passages in the facilitator guides survive
    sentence splitting intact. Previously these were emitted whole and then
    truncated by the encoder, losing the tail without any signal.
    """
    total = count_tokens(sentence)
    if total <= hard_max:
        return [sentence]

    words = sentence.split()
    if len(words) <= 1:
        return [sentence]  # a single unsplittable token

    # Estimate a word budget from the observed token-per-word ratio, then verify
    # and shrink. Tokenising every prefix would be correct but quadratic, and
    # this path runs over the longest passages in the corpus.
    ratio = total / len(words)
    budget = max(1, int(hard_max * 0.9 / ratio))

    pieces: list[str] = []
    index = 0
    while index < len(words):
        take = min(budget, len(words) - index)
        piece_words = words[index : index + take]
        # Shrink until it fits. Never grows, so no word is skipped.
        while len(piece_words) > 1 and count_tokens(" ".join(piece_words)) > hard_max:
            piece_words = piece_words[: max(1, len(piece_words) * 9 // 10)]
        pieces.append(" ".join(piece_words))
        index += len(piece_words)
    return pieces


def _pack(sentences: list[str], target: int, hard_max: int) -> list[str]:
    """Greedily pack sentences up to `target`, never exceeding `hard_max`."""
    out: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for raw in sentences:
        for sentence in _split_oversized(raw, hard_max):
            tokens = count_tokens(sentence)
            if current and current_tokens + tokens > target:
                out.append(" ".join(current))
                current, current_tokens = [], 0
            current.append(sentence)
            current_tokens += tokens
            if current_tokens >= hard_max:
                out.append(" ".join(current))
                current, current_tokens = [], 0

    if current:
        out.append(" ".join(current))
    return out


def _with_overlap(pieces: list[str], overlap_tokens: int, hard_max: int) -> list[str]:
    """Prepend the tail of each piece to the next, so ideas spanning a split
    boundary remain retrievable from either side.

    The overlap budget is capped by the headroom actually left in the target
    piece; otherwise adding context would push the chunk back over the
    encoder's limit — reintroducing the truncation this is meant to prevent.
    """
    if overlap_tokens <= 0 or len(pieces) < 2:
        return pieces

    out = [pieces[0]]
    for previous, piece in zip(pieces, pieces[1:]):
        headroom = hard_max - count_tokens(piece)
        budget = min(overlap_tokens, max(headroom, 0))
        if budget <= 0:
            out.append(piece)
            continue

        tail: list[str] = []
        for sentence in reversed(split_sentences(previous)):
            cost = count_tokens(sentence)
            if cost > budget:
                break
            tail.insert(0, sentence)
            budget -= cost
        out.append((" ".join(tail) + " " + piece).strip() if tail else piece)
    return out


def chunk_section(
    source: Source,
    section: Section,
    *,
    start_index: int = 0,
    target: int | None = None,
    hard_max: int | None = None,
    overlap: int | None = None,
    min_tokens: int | None = None,
) -> list[Chunk]:
    """Split one section into chunks, preserving provenance on each."""
    # Caps are clamped to what the embedding model can actually read, so an
    # over-large CHUNK_MAX_TOKENS cannot reintroduce silent truncation.
    hard_max = min(
        hard_max if hard_max is not None else config.CHUNK_MAX_TOKENS,
        effective_max_tokens(),
    )
    target = min(
        target if target is not None else config.CHUNK_TARGET_TOKENS, hard_max
    )
    overlap = overlap if overlap is not None else config.CHUNK_OVERLAP_TOKENS
    min_tokens = min_tokens if min_tokens is not None else config.CHUNK_MIN_TOKENS

    body = section.text.strip()
    if not body:
        return []

    # The section title is prepended to every chunk below, so its cost has to
    # be inside the budget rather than added after the limit check.
    title_cost = count_tokens(section.title) + 2
    body_max = max(hard_max - title_cost, 64)
    body_target = max(min(target, body_max), 64)

    if count_tokens(body) <= body_max:
        pieces = [body]
    else:
        pieces = _with_overlap(
            _pack(split_sentences(body), body_target, body_max), overlap, body_max
        )

    chunks: list[Chunk] = []
    for offset, piece in enumerate(pieces):
        # The section title is carried into the text, not just the metadata.
        text = piece if piece.startswith(section.title) else f"{section.title}\n\n{piece}"
        tokens = count_tokens(text)
        # Drop fragments too small to answer anything; they dilute retrieval.
        if tokens < min_tokens:
            continue
        index = start_index + offset
        chunks.append(
            Chunk(
                chunk_id=f"{source.source_id}_p{section.page_start:04d}_{index:03d}",
                text=text,
                source_id=source.source_id,
                title=source.title,
                citation_tag=source.citation_tag,
                section_title=section.title[:180],
                domain=source.domains[0] if source.domains else "",
                domains="|".join(source.domains),
                document_role=source.document_role,
                page_pdf=section.page_start,
                page_end=section.page_end,
                publisher=source.publisher,
                publication_year=source.year,
                country_scope=source.country_scope,
                audience=source.audience,
                permission_status=source.permission_status,
                corpus_version=config.CORPUS_VERSION,
                token_count=tokens,
                chunk_index=index,
            )
        )
    return chunks


def chunk_source(source: Source, sections: list[Section], **kwargs: Any) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        chunks.extend(chunk_section(source, section, start_index=len(chunks), **kwargs))
    return chunks
