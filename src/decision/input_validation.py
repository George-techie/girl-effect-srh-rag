"""The front door. Deterministic, and deliberately almost nothing.

Rejects input that cannot be routed, embedded or answered, before any of those
things are attempted. That is the whole job.

**What this does not do.** It does not sanitise, moderate, spell-correct or
translate. She writes in English, Kiswahili, Sheng or a mix of all three, with
emoji, without punctuation, in lower case — and every one of those is valid
input from the person this is built for. A front door that "cleans up" her
language before the system reads it has already decided she writes wrongly.

So the only thing normalised here is whitespace, and the original is returned
alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src import config
from src.language import detect


@dataclass(frozen=True)
class ValidatedInput:
    ok: bool
    text: str
    #: Exactly what she typed, kept whatever happens. Every downstream stage
    #: that reasons about her wording -- the decision layer, the support path,
    #: the generator -- reads this rather than anything derived from it.
    original: str
    reason: str = ""
    #: Which register she is writing in, so the generator can mirror it rather
    #: than switching her to English. A signal, not a determination.
    language: str = detect.KENYAN_ENGLISH


def validate(message: str | None) -> ValidatedInput:
    original = message if isinstance(message, str) else ""

    if not isinstance(message, str):
        return ValidatedInput(False, "", original, "not text")

    # Collapse runs of whitespace and newlines. This is the only change made to
    # her words, and it is made because a message pasted from a phone keyboard
    # arrives with line breaks that mean nothing.
    text = " ".join(message.split())

    if not text:
        return ValidatedInput(False, "", original, "empty")

    if len(text) > config.MAX_INPUT_CHARS:
        # Truncating and answering anyway would answer a question she did not
        # finish asking.
        return ValidatedInput(
            False, text, original,
            f"longer than {config.MAX_INPUT_CHARS} characters",
        )

    return ValidatedInput(True, text, original, language=detect.detect(text))
