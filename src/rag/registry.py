"""The governed source list, read from CSV.

The previous build kept this as 462 lines of hand-written Python: fifteen fields
per source, permission and review status, page-range include lists, per-source
heading exclusions. That was real governance, and most of it was answering
questions this corpus does not raise -- every document here is open, and none of
them need pages excluded by hand.

So the registry is a CSV a non-engineer can open, and the code is the twelve
lines needed to read it. What survived is the part that does work at runtime:
`document_role`, which separates provider guidance from what a girl reads.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from src import config


@dataclass(frozen=True)
class Source:
    """One corpus document and the metadata that follows its text into Chroma."""

    source_id: str
    filename: str
    title: str
    citation_tag: str
    publisher: str
    year: int
    domains: tuple[str, ...]
    document_role: str
    country_scope: str
    audience: str
    total_pages: int
    why_included: str

    #: Kept so the ported loader keeps working. No source needs either here --
    #: whole documents are ingested, and nothing is dropped by heading.
    drop_headings: tuple[str, ...] = field(default_factory=tuple)
    permission_status: str = "open_licence"

    @property
    def path(self) -> Path:
        return config.RAW / self.filename

    @property
    def is_provider_facing(self) -> bool:
        """Provider guidance rather than something written for her to read."""
        return self.document_role == config.CLINICAL_BOUNDARY

    def pages(self) -> list[int]:
        """Every page. The previous corpus needed hand-picked ranges; this one
        does not, and inventing ranges would be curation dressed as governance."""
        return []


def _split(value: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in (value or "").split("|") if p.strip())


def load(path: Path | None = None) -> tuple[Source, ...]:
    with open(path or config.REGISTRY_CSV, encoding="utf-8-sig", newline="") as fh:
        return tuple(
            Source(
                source_id=r["source_id"].strip(),
                filename=r["filename"].strip(),
                title=r["title"].strip(),
                citation_tag=r["citation_tag"].strip(),
                publisher=r["publisher"].strip(),
                year=int(r["year"]),
                domains=_split(r["categories"]),
                document_role=r["document_role"].strip(),
                country_scope=r["country_scope"].strip(),
                audience=r["audience"].strip(),
                total_pages=int(r["total_pages"] or 0),
                why_included=r["why_included"].strip(),
            )
            for r in csv.DictReader(fh)
        )


def all_sources() -> tuple[Source, ...]:
    return load()


def indexable() -> list[Source]:
    """Every registered source. Kept as a named function because the ingest
    script reads better for it, and because a later permission or review gate
    has one obvious place to go."""
    return list(load())


def by_id(source_id: str) -> Source | None:
    return next((s for s in load() if s.source_id == source_id), None)


def validate() -> list[str]:
    """Problems worth stopping for. Returns an empty list when the corpus is
    sound, so a caller can print it and exit non-zero."""
    problems: list[str] = []
    seen: set[str] = set()

    for s in load():
        if s.source_id in seen:
            problems.append(f"{s.source_id}: duplicate source_id")
        seen.add(s.source_id)

        if not s.path.exists():
            problems.append(f"{s.source_id}: {s.filename} not found in {config.RAW}")
        if s.document_role not in config.DOCUMENT_ROLES:
            problems.append(f"{s.source_id}: unknown document_role {s.document_role!r}")
        if not s.domains:
            problems.append(f"{s.source_id}: no categories")
        for d in s.domains:
            if d not in config.DOMAINS:
                problems.append(f"{s.source_id}: unknown category {d!r}")
        if not s.citation_tag:
            problems.append(f"{s.source_id}: no citation_tag — it would reach the UI blank")

    return problems
