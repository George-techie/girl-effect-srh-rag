"""Kenyan-register glossary.

Deterministic. No model call, no network, no latency worth measuring. This is
the layer that lets the safety system read a disclosure written the way the
target user actually writes.

The problem it solves, measured before it was built:

    "my boyfriend hits me when he is angry"            -> detected
    "chali yangu hunipiga but yeye huapologize later"  -> MISSED
    "i wish kuondokea hii dunia"                       -> MISSED

Language *detection* already worked — both were correctly labelled as
code-switched. What failed was reading the harm, because the rule layer matches
English patterns and has no idea what `hunipiga` means.

Three design commitments:

**Deterministic, not a translation model.** A glossary lookup cannot hallucinate,
cannot time out, and costs nothing. It also means the safeguarding path keeps
working when the API is down — a property verified when the rate limit hit
mid-build, and one an LLM normalisation step would have destroyed.

**Risk tags raise scrutiny; they do not prove a disclosure.** `kudedi` means
"to die" and is almost always exasperation. Tags feed the safety layer as one
signal among four, never as a verdict.

**The original message is never replaced.** Normalisation produces an additional
interpretation. Every downstream component still sees the raw text, so a wrong
glossary entry cannot erase a disclosure — it can only fail to add one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from src import config

LEXICON_PATH = config.DATA / "language" / "kenyan_lexicon.json"


@dataclass(frozen=True)
class Term:
    """One glossary entry and every surface form it may appear as."""

    term: str
    meaning: str
    risk_tags: tuple[str, ...]
    variants: tuple[str, ...] = ()
    domain: str | None = None
    confidence: str = "medium"
    source: str = ""
    note: str = ""

    @property
    def surface_forms(self) -> tuple[str, ...]:
        return (self.term, *self.variants)


@dataclass(frozen=True)
class Idiom:
    """A phrase whose literal reading would trigger the wrong risk tag."""

    phrase: str
    meaning: str
    suppresses: tuple[str, ...]
    variants: tuple[str, ...] = ()
    note: str = ""

    @property
    def surface_forms(self) -> tuple[str, ...]:
        return (self.phrase, *self.variants)


@dataclass
class Match:
    term: Term
    matched_text: str
    start: int
    end: int


@dataclass
class GlossaryResult:
    """What the glossary found in one message."""

    matches: list[Match] = field(default_factory=list)
    suppressed: list[str] = field(default_factory=list)
    idioms_found: list[str] = field(default_factory=list)

    @property
    def risk_tags(self) -> list[str]:
        """Tags surviving idiom suppression."""
        tags: set[str] = set()
        for match in self.matches:
            tags.update(match.term.risk_tags)
        return sorted(tags)

    @property
    def domains(self) -> list[str]:
        return sorted({m.term.domain for m in self.matches if m.term.domain})

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_terms": [
                {
                    "term": m.term.term,
                    "matched": m.matched_text,
                    "meaning": m.term.meaning,
                    "risk_tags": list(m.term.risk_tags),
                }
                for m in self.matches
            ],
            "risk_tags": self.risk_tags,
            "domains": self.domains,
            "idioms_found": self.idioms_found,
            "suppressed_tags": self.suppressed,
        }


@dataclass(frozen=True)
class Lexicon:
    terms: tuple[Term, ...]
    idioms: tuple[Idiom, ...]
    version: str
    reviewer: str

    @property
    def size(self) -> int:
        return sum(len(t.surface_forms) for t in self.terms)


def _compile(forms: tuple[str, ...]) -> re.Pattern[str]:
    """Word-boundary alternation over surface forms, longest first.

    Longest-first matters: `sitaki kukuwa kwa hii dunia` must win over any
    shorter entry that overlaps it, or the more specific meaning is lost.
    """
    ordered = sorted(forms, key=len, reverse=True)
    escaped = "|".join(re.escape(f) for f in ordered)
    return re.compile(rf"(?<!\w)(?:{escaped})(?!\w)", re.IGNORECASE)


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> Lexicon:
    data = json.loads((path or LEXICON_PATH).read_text(encoding="utf-8"))

    terms = tuple(
        Term(
            term=t["term"],
            meaning=t["meaning"],
            risk_tags=tuple(t.get("risk_tags") or ()),
            variants=tuple(t.get("variants") or ()),
            domain=t.get("domain"),
            confidence=t.get("confidence", "medium"),
            source=t.get("source", ""),
            note=t.get("note", ""),
        )
        for t in data.get("terms", [])
    )
    idioms = tuple(
        Idiom(
            phrase=i["phrase"],
            meaning=i["meaning"],
            suppresses=tuple(i.get("suppresses") or ()),
            variants=tuple(i.get("variants") or ()),
            note=i.get("note", ""),
        )
        for i in data.get("idioms", [])
    )
    return Lexicon(
        terms=terms,
        idioms=idioms,
        version=data.get("lexicon_version", "unknown"),
        reviewer=data.get("reviewer", "unknown"),
    )


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[re.Pattern[str], Term], ...]:
    return tuple((_compile(t.surface_forms), t) for t in load().terms)


@lru_cache(maxsize=1)
def _idiom_patterns() -> tuple[tuple[re.Pattern[str], Idiom], ...]:
    return tuple((_compile(i.surface_forms), i) for i in load().idioms)


def scan(text: str) -> GlossaryResult:
    """Find glossary terms, applying idiom suppression.

    Suppression is recorded rather than silent, so a reviewer can see that a
    tag was found and deliberately dropped — the difference between a rule that
    never fired and one that fired and was overruled.
    """
    result = GlossaryResult()
    if not text or not text.strip():
        return result

    # Idioms first: they decide which tags are allowed to survive.
    suppressed_tags: set[str] = set()
    for pattern, idiom in _idiom_patterns():
        if pattern.search(text):
            result.idioms_found.append(idiom.phrase)
            suppressed_tags.update(idiom.suppresses)

    for pattern, term in _patterns():
        for match in pattern.finditer(text):
            blocked = set(term.risk_tags) & suppressed_tags
            if blocked and set(term.risk_tags) <= suppressed_tags:
                result.suppressed.append(
                    f"{term.term}: {sorted(blocked)} suppressed by idiom"
                )
                continue
            result.matches.append(
                Match(term=term, matched_text=match.group(0),
                      start=match.start(), end=match.end())
            )
    return result


def normalise(text: str) -> str:
    """Produce an English interpretation by substituting known terms.

    Supporting evidence, never a replacement. The caller keeps the original and
    passes both onward, so a wrong entry here cannot erase a disclosure — the
    worst it can do is fail to add one.
    """
    result = scan(text)
    if not result.matches:
        return text

    # Right to left, so earlier offsets stay valid as we splice.
    out = text
    for match in sorted(result.matches, key=lambda m: m.start, reverse=True):
        out = out[: match.start] + match.term.meaning + out[match.end :]
    return out


def stats() -> dict[str, Any]:
    lex = load()
    tagged = [t for t in lex.terms if t.risk_tags]
    return {
        "lexicon_version": lex.version,
        "reviewer": lex.reviewer,
        "terms": len(lex.terms),
        "surface_forms": lex.size,
        "risk_tagged_terms": len(tagged),
        "idioms": len(lex.idioms),
        "risk_tags": sorted({tag for t in tagged for tag in t.risk_tags}),
    }
