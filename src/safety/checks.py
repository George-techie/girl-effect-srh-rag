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

#: Kenyan and international phone shapes. No corpus chunk contains a real phone
#: number -- checked across all 1,693 -- so any number in a generated answer was
#: invented, and a plausible wrong number given to a girl in crisis is the
#: highest-consequence output this system could produce. Hence fatal.
#:
#: The short-code half was rewritten after being run over the corpus. It was
#: `1(?:99|95|16)`, which matched **9 chunks**: every one of them a page
#: reference -- *"see LNG-IUD for Women With HIV, p. 199"*, *"p. 116"*, a
#: citation's page range. None was a phone number. A fatal check firing on a
#: page number does not produce a wrong contact; it produces a refusal, which is
#: the failure this whole build exists to stop repeating.
#:
#: So the short codes are now the actual four-digit Kenyan ones, plus 116 only
#: where something nearby presents it as a number to call. A fabricated contact
#: arrives with that cue -- a bare 116 in prose does not.
PHONE = re.compile(
    r"(?<!\[S)\b(?:\+?254|0)\s?\d{3}[\s-]?\d{3}[\s-]?\d{3,4}\b"
    r"|\b(?:1190|1195|1199)\b"
    r"|(?:\b(?:call|dial|text|whatsapp|helpline|hotline|toll[- ]free|number)\b"
    r"[^.\n]{0,30}\b116\b)"
    r"|(?:\b116\b[^.\n]{0,20}\b(?:free|24/7|helpline|hotline|toll)\b)",
    re.IGNORECASE,
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


#: Promising to answer instead of answering. On a grounded turn the passages are
#: already in the prompt, so "I can look into that if you want" is the system
#: offering to fetch what it is holding.
DEFERRAL = re.compile(
    r"\bi (can|could|will|would) (look (it |that )?up|look into|check|find out|"
    r"go through|dig into)\b"
    r"|\blet me (look|check|find)\b"
    r"|\bi can (tell you more|share more)\b.{0,20}\bif you want\b",
    re.IGNORECASE,
)

#: A dash used as punctuation: em, en, or a spaced hyphen doing the same job.
#: Not a hyphen inside a word, and not a bullet at the start of a line.
DASH = re.compile(r"[—–]|(?<=\s)-(?=\s)")

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


#: The one issue that means "nothing could be cited" and nothing worse. Named
#: rather than spelled out at each use, because a caller comparing against a
#: literal copy of this sentence is a bug waiting for someone to reword it.
NO_CITATION = "no citation on a grounded health answer"

#: Fragments identifying the *other* fatal problems. A draft carrying any of
#: these is unsendable no matter what else is true of it.
_OTHER_FATAL = (
    "citation markers on a turn that had no source passages",
    "citation markers pointing at passages",
    "came from no source",
    "claims lived experience",
)


def only_missing_citation(issues: list[str]) -> bool:
    """Is the sole *fatal* problem that the draft could not cite anything?

    Non-fatal issues -- dashes, length, machinery talk -- are ignored here on
    purpose. They were being counted, and a draft that merely contained a dash
    stopped qualifying for the conversational fall-through and was refused
    instead. A punctuation rule must never be able to take an answer down; that
    is the output judge's mistake, and it cost a girl an answer about being
    frightened of becoming a young mother.
    """
    if NO_CITATION not in issues:
        return False
    return not any(fragment in issue
                   for issue in issues for fragment in _OTHER_FATAL)


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
            issues.append(NO_CITATION)
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

    dashes = len(DASH.findall(draft))
    if dashes:
        # Recorded, not fatal. A dash is a register problem, not a safety one,
        # and blocking an otherwise good answer over punctuation would be the
        # output judge's mistake all over again. This exists so "the prompt says
        # not to" can be checked instead of believed.
        issues.append(f"{dashes} dash(es) used as punctuation")

    deferral = DEFERRAL.search(draft)
    if deferral and grounded:
        # It is holding the passages and offering to go and find them. Recorded
        # rather than fatal, because the reply is still warm and still hers --
        # but it answered by promising to answer, which on a mixed message is
        # how the factual half quietly disappears. Measured on the real one:
        # top similarity 0.798, the right passage retrieved, zero citations.
        issues.append(f"offers to look up what it already has: "
                      f"{deferral.group(0)!r}")

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
