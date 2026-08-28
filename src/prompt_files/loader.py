"""Prompt loading and versioning.

Prompts live in YAML rather than in Python string literals for two reasons: a
non-engineer reviewer (safeguarding, content, clinical) can read and comment on
them without reading code, and the `version` field can be stamped onto every
evaluation result so a score is always attributable to an exact prompt text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src import config


#: Instruction injected into the answer prompt, chosen by detected language.
#:
#: Without this, register mirroring was left to the model and was inconsistent:
#: a fully Kiswahili question got a Kiswahili answer, while "niko na exams
#: zinacom and i have not prepreared" — code-switched, mostly English words with
#: Kiswahili structure — got pure English back. Same user, same session,
#: different treatment, for no reason she could see.
LANGUAGE_NOTES: dict[str, str] = {
    "kenyan_english": (
        "She wrote in English. Answer in clear Kenyan English."
    ),
    "kiswahili": (
        "She wrote in Kiswahili. Answer in Kiswahili — the everyday kind, not "
        "formal or academic Swahili, which reads as officialdom and is exactly "
        "what she may be avoiding by asking a phone instead of a person."
    ),
    "sheng_code_switch": (
        "She has been writing in the mixed Kenyan register — Kiswahili, English "
        "and Sheng together. **Answer in that same mixed register.** Do not "
        "switch her to English; a girl who writes 'niko na exams zinacom' and "
        "receives a formal English paragraph has been told, without words, that "
        "she was speaking wrongly.\n"
        "  This covers the **short** English lines a code-switching person "
        "drops in — 'i haven't studied enough', 'yes', 'sawa' — where switching "
        "her to formal English for one turn and back is more jarring than never "
        "matching her at all.\n"
        "  It does **not** mean answering in Sheng whatever she writes. If she "
        "has typed a whole message in plain English, she has switched, and "
        "performing a register she just stepped out of is the same failure in "
        "the other direction."
    ),
    "mixed": (
        "She mixed Kiswahili and English. Answer the same way — match how she "
        "actually writes rather than correcting her into one language."
    ),
    "unknown": (
        "Answer in clear Kenyan English."
    ),
}


@lru_cache(maxsize=1)
def _persona() -> dict[str, Any]:
    """The Trusted Aunti definition, loaded once.

    Separate from the `Prompt` dataclass because it is not a prompt — it has no
    user template and is never sent on its own. It is the first layer of every
    generation prompt, assembled here so the grounded and conversational paths
    cannot drift into two voices.
    """
    path = config.PROMPTS_DIR / "persona.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No persona file at {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def persona_block(seriousness: str | None = None) -> str:
    """Layer 1 — identity, boundaries, style, language, phrases, tone.

    `seriousness` selects one tone note rather than showing all four. A model
    given every tone and asked to pick reliably blends them, which produces the
    average of light and grave — the register that fits nothing.
    """
    p = _persona()
    tones = p.get("tone") or {}
    key = seriousness if seriousness in tones else p.get(
        "default_seriousness", "personal"
    )

    parts = [
        p.get("identity", ""),
        p.get("boundaries", ""),
        p.get("conversation_style", ""),
        p.get("language_policy", ""),
        tones.get(key, ""),
        p.get("emoji", ""),
        p.get("phrase_bank", ""),
    ]
    return "\n\n".join(s.strip() for s in parts if s and s.strip())


def tone_expectation(seriousness: str | None = None) -> str:
    """The tone note as given to the writer, for handing to the judge.

    Both sides must be reading the same instruction. If the judge re-derived
    the right tone from the message itself, a disagreement would be a difference
    of opinion between two models rather than evidence the writer ignored what
    it was told — and only the second of those is actionable.
    """
    p = _persona()
    tones = p.get("tone") or {}
    key = seriousness if seriousness in tones else p.get(
        "default_seriousness", "personal"
    )
    return str(tones.get(key, "")).strip()


def persona_stamp() -> dict[str, str]:
    """Version and fingerprint, so a scored response is attributable to a voice."""
    p = _persona()
    digest = hashlib.sha256(persona_block().encode("utf-8")).hexdigest()[:8]
    return {
        "persona": str(p.get("name", "persona")),
        "persona_version": str(p.get("version", "v0")),
        "persona_fingerprint": digest,
    }


def turn_context(**fields: Any) -> str:
    """Layer 2 — what is true about this turn.

    Passed as a labelled block rather than folded into prose, because these
    values change every turn while everything around them does not. Keeping the
    variable part visibly separate is what lets one persona behave differently
    for a girl asking a question, venting, continuing a thread, or unsure what
    she wants — without four persona variants to maintain.
    """
    lines = [f"  {k}: {v}" for k, v in fields.items() if v not in (None, "", [])]
    if not lines:
        return ""
    return "Context for this turn:\n" + "\n".join(lines) + "\n\n"


def _SYSTEM_VALUES(
    language_label: str | None = None, seriousness: str | None = None
) -> dict[str, Any]:
    """Configured values available to every system prompt."""
    return {
        "persona": persona_block(seriousness),
        "target_words": config.RESPONSE_TARGET_WORDS,
        "min_target_words": config.RESPONSE_MIN_TARGET_WORDS,
        "max_words": config.RESPONSE_MAX_WORDS,
        "converse_min_target_words": config.CONVERSE_MIN_TARGET_WORDS,
        "converse_target_words": config.CONVERSE_TARGET_WORDS,
        "converse_max_words": config.CONVERSE_MAX_WORDS,
        "language_note": LANGUAGE_NOTES.get(
            language_label or "kenyan_english", LANGUAGE_NOTES["kenyan_english"]
        ),
    }


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str
    user_template: str
    raw: dict[str, Any]

    def render_user(self, **kwargs: Any) -> str:
        return self.user_template.format(**kwargs)

    def render_system(
        self, language_label: str | None = None, seriousness: str | None = None
    ) -> str:
        """Substitute configured values into the system prompt.

        Response length lives in config rather than in the prompt text, so the
        prompt, the token budget and the output validator cannot drift apart.
        They previously did: the prompt asked for 60-150 words while the
        validator only blocked above 320, which meant nothing was enforcing
        length in practice.

        Unknown placeholders are left as written rather than raising, so a
        prompt can use braces for other purposes without breaking.
        """
        try:
            return self.system.format(**_SYSTEM_VALUES(language_label, seriousness))
        except (KeyError, IndexError, ValueError):
            return self.system

    def messages(
        self,
        *,
        language_label: str | None = None,
        seriousness: str | None = None,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system",
             "content": self.render_system(language_label, seriousness).strip()},
            {"role": "user", "content": self.render_user(**kwargs).strip()},
        ]

    @property
    def fingerprint(self) -> str:
        """Short hash of the actual text, so edits are detectable even if the
        author forgets to bump `version`."""
        digest = hashlib.sha256(
            (self.system + self.user_template).encode("utf-8")
        ).hexdigest()
        return digest[:8]

    def situation(self, key: str, default: str = "") -> str:
        """A named situation note from the prompt file.

        Lets one prompt cover several closely related paths — an explore turn and
        a no-evidence turn share every rule and differ only in what happened —
        without either duplicating the rules in a second file or leaving the
        model to infer why it is on this path.
        """
        note = (self.raw.get("situations") or {}).get(key, default)
        return " ".join(str(note).split())

    def stamp(self) -> dict[str, str]:
        return {
            "prompt_name": self.name,
            "prompt_version": self.version,
            "prompt_fingerprint": self.fingerprint,
        }


@lru_cache(maxsize=32)
def load(name: str) -> Prompt:
    path: Path = config.PROMPTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file at {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = {"system", "user"} - set(data)
    if missing:
        raise ValueError(f"Prompt {name!r} missing required keys: {sorted(missing)}")

    return Prompt(
        name=data.get("name", name),
        version=str(data.get("version", "v0")),
        system=data["system"],
        user_template=data["user"],
        raw=data,
    )
