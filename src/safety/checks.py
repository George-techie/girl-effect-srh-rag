"""Deterministic output checks. No model.

These are what the previous build's LLM output judge was mostly doing, minus the
part that refused a girl's compliment twice. Each one is free, instant, and
checks something that is not a matter of opinion: a fabricated citation, a phone
number that came from nowhere, a claim to have lived something.

`fatal` means the draft does not ship. Everything else is recorded and sent.
"""

from __future__ import annotations

import re

from src import config

#: A citation marker. The generator writes these; the readable labels are added
#: afterwards from metadata.
MARKER = re.compile(r"\[S(\d+)\]")

#: Kenyan and international phone shapes. Nothing in the corpus contains one --
#: measured, zero of 1,693 chunks -- so any number in a generated answer was
#: invented, and a plausible wrong number given to a girl in crisis is the
#: highest-consequence output this system could produce.
PHONE = re.compile(
    r"(?<!\[S)\b(?:\+?254|0)\s?\d{3}[\s-]?\d{3}[\s-]?\d{3,4}\b"
    r"|\b1(?:99|95|16)\b"
)

#: Claims of lived experience. Narrow on purpose: "I hear what you're going
#: through" must pass; only claims of having lived it are caught.
LIVED = re.compile(
    r"\b(i (can )?relate\b|i('ve| have) been there|"
    r"i know (exactly )?how (that|you|it) feel|"
    r"(the )?same thing happened to me|when i was your age|"
    r"i went through (the same|that|this))",
    re.IGNORECASE,
)


#: The system describing its own plumbing to a girl who cannot see it. Recorded,
#: never fatal, and the asymmetry is the point: blocking here would trade a
#: slightly awkward answer for a refusal, which is the worse of the two. The
#: prompt asks for this; the check is how we find out whether asking worked.
MACHINERY = re.compile(
    r"\b(the |these |those |my )?passages?\b"
    r"|\bknowledge base\b|\bretrieved\b|\bthe context i (have|was given)\b"
    r"|\bthe documents? i\b|\bmy (source|document)s?\b",
    re.IGNORECASE,
)


def check(draft: str, *, n_passages: int, grounded: bool = True
          ) -> tuple[list[str], bool]:
    """Returns ``(issues, fatal)``."""
    issues: list[str] = []
    fatal = False

    markers = [int(m) for m in MARKER.findall(draft)]

    if not grounded and markers:
        # No passages were retrieved, so a marker is a fabricated reference --
        # worse than an uncited claim, because it looks verified.
        issues.append("citation markers on a turn that had no source passages")
        fatal = True

    if grounded:
        if not markers:
            issues.append("no citation on a grounded health answer")
            fatal = True

        invalid = sorted({m for m in markers if not 1 <= m <= n_passages})
        if invalid:
            # Worse than an uncited claim: a fabricated reference looks verified.
            issues.append(f"citation markers pointing at passages that were "
                          f"never retrieved: {invalid}")
            fatal = True

    for number in PHONE.findall(draft):
        issues.append(f"contact number that came from no source: {number}")
        fatal = True

    match = LIVED.search(draft)
    if match:
        issues.append(f"claims lived experience it does not have: "
                      f"{match.group(0)!r}")
        fatal = True

    machinery = MACHINERY.search(draft)
    if machinery:
        issues.append(f"describes its own machinery to her: "
                      f"{machinery.group(0)!r}")

    words = len(draft.split())
    if words < config.RESPONSE_MIN_WORDS:
        issues.append(f"only {words} words")
    elif words > config.RESPONSE_MAX_WORDS:
        # Not a safety failure, but not sendable on a phone either.
        issues.append(f"{words} words, over the {config.RESPONSE_MAX_WORDS} limit")

    return issues, fatal


def strip_markers(text: str) -> str:
    """Remove citation tags for display, taking the space before them.

    A plain substitution leaves "does not cause infertility ." -- the marker
    goes and the space it was attached to stays. She sees the seam.
    """
    return re.sub(r"[ 	]*\[S\d+\]", "", text).strip()
