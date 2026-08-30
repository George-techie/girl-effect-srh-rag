"""Verified services. A table read, never a generation.

Zero of the 1,693 corpus chunks contains a phone number, so a number in a
generated answer is invented by definition and the validator treats one as
fatal. This file is the only legitimate source of a contact detail in the
system, and it has one rule above all others:

    **A row is invisible until a person has verified it.**

`status` must be exactly `verified`. Anything else -- blank, `unverified`, a
typo -- does not reach a girl. That is deliberate and it is not a soft default:
a directory whose column says `verified_at` is worthless if the dates in it
were invented, and a plausible wrong number given to a girl in crisis is the
highest-consequence output this system can produce.

**Ranking is not alphabetical, and the reason is practical.** A girl on a shared
phone, in a room with family, often cannot make a call. A row she can text or
WhatsApp is worth more to her than another hotline, so text-capable rows come
first, then free ones, then ones that do not require her name.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES_CSV = ROOT / "data" / "services" / "services.csv"

VERIFIED = "verified"

#: Channels she can use without speaking out loud.
_TEXT_CAPABLE = {"sms", "whatsapp", "phone_whatsapp", "ussd", "web"}


@dataclass(frozen=True)
class Service:
    service_id: str
    name: str
    routes: tuple[str, ...]
    contact_type: str
    contact: str
    what_they_do: str
    coverage: str = ""
    is_free: str = ""
    anonymous_ok: str = ""
    opening_hours: str = ""
    eligibility: str = ""

    @property
    def textable(self) -> bool:
        return self.contact_type.strip().lower() in _TEXT_CAPABLE

    def render(self) -> str:
        """One line, as she would read it. Built from columns, never written."""
        bits = [f"**{self.name}** · {self.contact}"]
        detail = []
        if self.textable:
            detail.append("call or text")
        if self.is_free.strip().lower() in {"yes", "y", "true", "free"}:
            detail.append("free")
        if self.anonymous_ok.strip().lower() in {"yes", "y", "true"}:
            detail.append("you don't have to give your name")
        if self.opening_hours.strip():
            detail.append(self.opening_hours.strip())
        if detail:
            bits.append(" · ".join(detail))
        line = " · ".join(bits)
        if self.what_they_do.strip():
            line += f"\n{self.what_they_do.strip()}"
        return line


@lru_cache(maxsize=1)
def _load() -> tuple[Service, ...]:
    if not SERVICES_CSV.exists():
        return ()
    rows: list[Service] = []
    with SERVICES_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            # The gate. Everything else in this function is presentation.
            if (row.get("status") or "").strip().lower() != VERIFIED:
                continue
            if not (row.get("contact") or "").strip():
                continue
            rows.append(Service(
                service_id=(row.get("service_id") or "").strip(),
                name=(row.get("name") or "").strip(),
                routes=tuple(r.strip() for r in
                             (row.get("routes") or "").split("|") if r.strip()),
                contact_type=(row.get("contact_type") or "").strip(),
                contact=(row.get("contact") or "").strip(),
                what_they_do=(row.get("what_they_do") or "").strip(),
                coverage=(row.get("coverage") or "").strip(),
                is_free=(row.get("is_free") or "").strip(),
                anonymous_ok=(row.get("anonymous_ok") or "").strip(),
                opening_hours=(row.get("opening_hours") or "").strip(),
                eligibility=(row.get("eligibility") or "").strip(),
            ))
    return tuple(rows)


def reload() -> None:
    """Pick up edits to the CSV without restarting. For whoever is filling it."""
    _load.cache_clear()


def for_route(route: str, limit: int = 3) -> list[Service]:
    """Verified services for one route, best-for-her first."""
    matches = [s for s in _load() if route in s.routes]
    matches.sort(key=lambda s: (
        not s.textable,                                    # textable first
        s.is_free.strip().lower() not in {"yes", "y", "true", "free"},
        s.anonymous_ok.strip().lower() not in {"yes", "y", "true"},
        s.name.lower(),
    ))
    return matches[:limit]


def block(route: str, limit: int = 3) -> str:
    """The rendered contacts for a route, or an empty string if there are none.

    Empty is a valid and expected answer. The caller must have something to say
    without it -- naming the *kind* of person who helps is useful even when we
    cannot name one, and it is what the approved text already does.
    """
    found = for_route(route, limit)
    return "\n\n".join(s.render() for s in found) if found else ""


def counts() -> dict[str, int]:
    """Verified rows per route. For the demo panel and the readiness check."""
    tally: dict[str, int] = {}
    for service in _load():
        for route in service.routes:
            tally[route] = tally.get(route, 0) + 1
    return tally
