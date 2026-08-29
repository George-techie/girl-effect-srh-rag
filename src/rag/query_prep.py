"""Conditional query preparation. Deterministic, no model.

Experiment 2 measured the gap this closes. The corpus says *"informed consent
for adolescents and youth"*; she says *"without my parents agreeing"*. The
passage exists, is Kenyan, is authoritative — and retrieves at 0.565 from her
words against 0.711 from the document's own. Same question, different
vocabulary, and no amount of source weighting fixed it.

Two constraints the same experiment put on it, both measured:

**Only factual and access turns.** Restating a support turn or a disclosure
pulled retrieval away from the youth material written in her register and
toward policy literature *about* her situation — *"I am pregnant and scared to
tell anyone"* moved from UNICEF's youth Q&A to Kenya MoH informed-consent
guidance.

**Only after the decision.** Restatement made a deliberately out-of-scope
question retrieve *more* confidently (0.668 → 0.691). Deciding on a rewritten
query means deciding on words she never said.

**Expansion, not replacement.** Her terms stay in the query and the corpus's are
appended. A replacement throws away the signal that was working; an expansion
can only add. That is also why this is cheap to be wrong about — a mapping that
does not apply contributes an unused phrase rather than a wrong query.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Each entry: a pattern in her words, and the corpus vocabulary to append.
#:
#: EVIDENCED — these three come from measured failures in Experiment 1 and 2,
#: with the retrieval scores recorded in evaluation/experiment_*.md.
#: EXTRAPOLATED — the rest are the same *kind* of gap (her register against
#: clinical or policy register) written from the corpus's own section titles,
#: not from running queries and keeping whatever scored well. They are marked so
#: the distinction survives into review.
_EXPANSIONS: tuple[tuple[str, str, str], ...] = (
    # --- evidenced ----------------------------------------------------------
    (r"\bwithout (my )?(parents?|mum|mother|dad|father|guardian)\b"
     r"|\bparents? (agreeing|knowing|permission)\b",
     "informed consent for adolescents and youth parental consent",
     "evidenced"),
    (r"\b(not married|unmarried|single)\b",
     "marital status eligibility guiding principles non-discrimination",
     "evidenced"),
    (r"\bmji wa mtoto\b|\bkizazi\b|\bdamage.{0,20}\bwomb\b",
     "uterus womb return to fertility infertility misconception",
     "evidenced"),

    # --- extrapolated -------------------------------------------------------
    (r"\bmake me infertile\b|\bnever have (children|kids|a baby)\b"
     r"|\bstill.{0,20}\bhave children\b",
     "return to fertility after stopping contraception infertility",
     "extrapolated"),
    (r"\bwhere (can|do|could) i (get|go|find)\b|\bnaweza pata\b",
     "service delivery points facilities community access",
     "extrapolated"),
    (r"\bmorning after\b|\bP2\b",
     "emergency contraceptive pills timing effectiveness",
     "extrapolated"),
    (r"\b(makes? you|make me) fat\b|\bgain weight\b",
     "weight change side effects correcting misunderstandings",
     "extrapolated"),
    (r"\bstop(s|ped)? my periods?\b|\bno periods?\b",
     "amenorrhoea changes in monthly bleeding side effects",
     "extrapolated"),
    (r"\bwhat will they ask\b|\bwhat happens (at|when i go to) the clinic\b",
     "counselling client assessment screening first visit",
     "extrapolated"),
    (r"\btoo young\b|\bmy age\b|\bi'?m 1[0-9]\b|\bi am 1[0-9]\b",
     "adolescents and youth all contraceptives are safe for young people",
     "extrapolated"),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), add, kind)
                  for p, add, kind in _EXPANSIONS)


@dataclass(frozen=True)
class PreparedQuery:
    text: str
    original: str
    restated: bool
    applied: list[str]

    @property
    def changed(self) -> bool:
        return self.text != self.original


def prepare(message: str, *, restate: bool) -> PreparedQuery:
    """Build the retrieval query. `restate=False` returns her words untouched.

    The caller decides — `Decision.restate` is true only for factual and access
    turns, which is the condition Experiment 2 established.
    """
    if not restate:
        return PreparedQuery(message, message, False, [])

    additions: list[str] = []
    applied: list[str] = []
    for pattern, addition, kind in _COMPILED:
        if pattern.search(message):
            additions.append(addition)
            applied.append(f"{kind}: {pattern.pattern[:40]}")

    if not additions:
        return PreparedQuery(message, message, False, [])

    # Her words first. The embedding sees both registers, and the one that was
    # already working is not discarded.
    return PreparedQuery(
        f"{message} {' '.join(additions)}", message, True, applied
    )
