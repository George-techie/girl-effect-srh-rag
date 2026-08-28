"""Text normalisation and boilerplate removal.

PDF text extraction produces artefacts that quietly poison retrieval: running
headers repeated on every page, hyphens splitting words across line breaks, page
numbers embedded mid-sentence. Each one costs recall, because the embedding of a
chunk padded with "Family Planning: A Global Handbook for Providers 143" is
pulled toward the boilerplate rather than the content.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

# Ligatures and typographic characters that break exact matching downstream.
_REPLACEMENTS = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", "​": "", "﻿": "",
    "•": "- ", "●": "- ", "▪": "- ", "·": "- ",

    # Ligatures mangled by a font subset in the Kenya MoH FAQ. That PDF encodes
    # its ti/ft/tt ligatures at Latin Extended-B codepoints, so extraction
    # returns "Ɵme", "aŌer", "transmiƩed", "breasƞeeding". Left alone it would
    # corrupt the one Kenyan youth-facing source in the corpus -- and quietly,
    # because the text still looks like words.
    #
    # Each mapping is confirmed against several words rather than inferred from
    # one: Ɵ from time/effective/protection/contraceptives/fertile, Ō from
    # after/lifting, Ʃ from transmitted/better, ƫ from getting, ƞ from
    # breastfeeding.
    "Ɵ": "ti", "Ō": "ft", "Ʃ": "tt", "ƫ": "tti", "ƞ": "tf",
}

_BULLET_RE = re.compile(r"^\s*[•●▪◦⁃∙*]\s*")
_PAGE_NUMBER_ONLY_RE = re.compile(r"^\s*(?:page\s*)?[ivxlcdm\d]{1,6}\s*$", re.IGNORECASE)

_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# A hyphen at end of line followed by a lowercase continuation = split word.
_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z])-\n([a-z])")


def normalise(text: str) -> str:
    """Apply character-level fixes that are always safe."""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def clean_line(line: str) -> str:
    line = _BULLET_RE.sub("- ", line)
    return line.rstrip()


def is_noise_line(line: str) -> bool:
    """Lines that carry no retrievable meaning on their own."""
    stripped = line.strip()
    if not stripped:
        return True
    if _PAGE_NUMBER_ONLY_RE.match(stripped):
        return True
    # A line of dots/underscores is a table-of-contents leader or a form field.
    if len(stripped) > 3 and len(set(stripped) - set(". _-|")) == 0:
        return True
    return False


def find_running_headers(
    pages: Iterable[str], *, min_share: float = 0.35, max_len: int = 110
) -> set[str]:
    """Detect header/footer lines repeated across many pages.

    A line appearing near the top or bottom of at least `min_share` of pages is
    almost certainly a running header rather than content. Detecting them
    statistically avoids hand-maintaining a per-document exclusion list.
    """
    pages = list(pages)
    if len(pages) < 4:
        return set()

    counts: Counter[str] = Counter()
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        if not lines:
            continue
        # Only the first three and last three lines can be running furniture.
        for line in {*lines[:3], *lines[-3:]}:
            if len(line) <= max_len:
                # Normalise digits so "Page 12"/"Page 13" collapse together.
                counts[re.sub(r"\d+", "#", line)] += 1

    threshold = max(3, int(len(pages) * min_share))
    return {line for line, count in counts.items() if count >= threshold}


def strip_running_headers(page: str, headers: set[str]) -> str:
    if not headers:
        return page
    kept = [
        line
        for line in page.splitlines()
        if re.sub(r"\d+", "#", line.strip()) not in headers
    ]
    return "\n".join(kept)


def collapse_whitespace(text: str) -> str:
    lines = [clean_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if not is_noise_line(ln)]
    return _MULTI_NEWLINE_RE.sub("\n\n", "\n".join(lines)).strip()
