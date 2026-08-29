"""What happened, recorded so it can be counted instead of remembered.

The case for this is not abstract. Three defects were found in this codebase in
a single afternoon, and every one of them was found by a person reading output
by hand:

  the phone check fired on page numbers   found by re-checking a number written
                                          in the README. It was fatal, so a
                                          correct cited answer mentioning p. 116
                                          would have been refused
  the topic was trimmed before it was used  found by printing a journey and
                                          noticing "resolved against" was absent
  `Decision.retrieves` disagreed with the pipeline  found only when a new caller
                                          started trusting it

None of those is exotic. They are the normal failure mode of a system with
several deterministic layers: a component quietly stops doing what its name
says, everything still returns a plausible answer, and nothing anywhere counts.
Reading output by hand does not scale past a demo, and the thing that does not
scale is exactly what a girl relies on.

So this module does three things, and deliberately not a fourth:

1. **An event per turn.** The pipeline already assembles a full trace for the
   demo panel and then throws it away. This writes it down.
2. **Invariants checked at runtime.** Cheap assertions about what must be true
   of a turn — a grounded answer has sources, a safeguarding turn never touched
   the encoder. Violations are recorded, never raised: an observability layer
   that can take down the service is worse than no observability layer.
3. **Journey stage**, so the events answer a Girl Effect question and not only
   an engineering one — is she moving toward service access, or circling?

It does not ship anything anywhere. No vendor, no collector, no daemon. It is a
JSONL file, and the reader is `scripts/inspect_events.py`.

---

**On logging adolescent girls' disclosures.**

This is a safeguarding product. An observability layer that writes down what
girls said about coercion, in a file, next to a timestamp, is a surveillance
database with a monitoring dashboard on top — and the ones most at risk from it
are the girls the product exists for.

So the default is **operational events only**: paths, timings, similarity
scores, flags, issue names. No message text. No reply text.

Message text is written only when `TRACE_MESSAGES=1` is set explicitly, which is
for a developer replaying a bug on their own machine and is documented as such.
There is no session identifier that survives a restart, and no identifier of any
kind for her. What you can learn from the default stream is that fragments are
failing to resolve; what you cannot learn is who said what.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: Where events land. One file, append-only, one JSON object per line.
EVENTS = Path(os.getenv("EVENTS_FILE", ROOT / "data" / "events.jsonl"))

#: Off unless a developer turns it on. See the note above.
TRACE_MESSAGES = os.getenv("TRACE_MESSAGES", "").strip() in {"1", "true", "yes"}

#: Writing is best-effort and must never interrupt a turn.
ENABLED = os.getenv("OBSERVABILITY", "1").strip() not in {"0", "false", "no"}

_LOCK = threading.Lock()


# --- journey stage -----------------------------------------------------------
#: Girl Effect's Theory of Change runs behavioural drivers -> intent -> service
#: access -> behaviour change. A path is an engineering fact; a stage is the
#: product one. Recording both is what lets someone ask "are girls getting to
#: the service question, or stopping before it?" -- which is the question the
#: whitepaper actually cares about, and which no per-turn latency chart answers.
STAGE = {
    "chat": "rapport",
    "factual": "knowledge",
    "support": "confidence",
    "access": "service_access",
    "safeguarding": "safeguarding",
    "out_of_scope": "deflected",
    "invalid_input": "none",
}


@dataclass
class Violation:
    name: str
    detail: str


def check_invariants(trace: dict[str, Any], reply_path: str,
                     n_sources: int, text: str) -> list[Violation]:
    """What must be true of any turn. Recorded, never raised.

    Each of these exists because something in this codebase has already gone
    wrong in that exact shape, or could have without anyone noticing.
    """
    bad: list[Violation] = []
    retrieved = trace.get("retrieved") or []

    # A path that must never reach the corpus, reaching it. This is the class
    # `Decision.retrieves` fell into: the property said one thing, the pipeline
    # did another, and the disagreement was invisible for as long as nothing
    # depended on it.
    if reply_path in ("safeguarding", "out_of_scope", "chat") and retrieved:
        bad.append(Violation("searched_on_a_path_that_must_not",
                             f"{reply_path} retrieved {len(retrieved)} passages"))

    # The grounded contract, checked against the output rather than trusted.
    if trace.get("contract") == "grounded" and not trace.get("fatal"):
        if not trace.get("insufficient") and n_sources == 0 and text:
            bad.append(Violation("grounded_answer_without_sources",
                                 "grounded contract, zero cited sources"))

    # The conversational contract's opposite failure.
    if trace.get("contract") == "conversational" and n_sources:
        bad.append(Violation("conversational_answer_with_sources",
                             f"{n_sources} sources on a turn with no passages"))

    # A signal written and read by nobody. The previous build set `urgent` on a
    # template, wrote it into the trace, and nothing consumed it -- so a girl at
    # risk of self-harm saw less than one who disclosed something less dangerous.
    if trace.get("help_requested") and reply_path != "safeguarding":
        bad.append(Violation("help_request_outside_safeguarding",
                             "help_requested set on a non-safeguarding turn"))

    # A fragment that stayed a fragment. Not necessarily a bug -- there may
    # genuinely be no antecedent -- but it is the shape the trimmed-topic defect
    # made, and it was invisible until someone printed a journey by hand.
    if trace.get("dependent") and not trace.get("resolved_from"):
        bad.append(Violation("unresolved_fragment",
                             "dependent message with no antecedent available"))

    # Money and latency, so a regression in either is visible before a bill is.
    if trace.get("llm_calls", 0) > 1:
        bad.append(Violation("more_than_one_model_call",
                             f"{trace['llm_calls']} calls in one turn"))

    return bad


def record(*, trace: dict[str, Any], reply_path: str, n_sources: int,
           text: str, message: str, turn: int | None = None) -> list[Violation]:
    """Write one event. Returns the violations so the caller can trace them too.

    Best-effort by construction: any failure here is swallowed, because a
    monitoring layer that can break a girl's answer has inverted its own purpose.
    """
    violations = check_invariants(trace, reply_path, n_sources, text)

    if not ENABLED:
        return violations

    event: dict[str, Any] = {
        "ts": time.time(),
        "turn": turn,
        "path": reply_path,
        "stage": STAGE.get(reply_path, "unknown"),
        "why": trace.get("why"),
        "contract": trace.get("contract"),
        "llm_calls": trace.get("llm_calls", 0),
        "model": trace.get("model"),
        "latency_ms": trace.get("latency_ms"),
        "n_retrieved": len(trace.get("retrieved") or []),
        "n_sources": n_sources,
        "top_similarity": (trace.get("retrieved") or [{}])[0].get("similarity"),
        "top_role": (trace.get("retrieved") or [{}])[0].get("role"),
        "query_prepared": bool(trace.get("query_prepared")),
        "resolved": bool(trace.get("resolved_from")),
        "dependent": bool(trace.get("dependent")),
        "disclosed_earlier": bool(trace.get("disclosed_earlier")),
        "help_requested": bool(trace.get("help_requested")),
        "insufficient": bool(trace.get("insufficient")),
        "blocked": bool(trace.get("fatal")),
        "issues": trace.get("issues") or [],
        "error": trace.get("error"),
        "reply_words": len(text.split()) if text else 0,
        "violations": [v.name for v in violations],
    }

    # Off unless a developer asked for it. See the module docstring.
    if TRACE_MESSAGES:
        event["message"] = message
        event["reply"] = text
        event["query"] = trace.get("query")

    try:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, default=str)
        with _LOCK, EVENTS.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 - never let recording break a turn
        pass

    return violations


def read(path: Path | None = None) -> list[dict[str, Any]]:
    """Every event, skipping any line that got truncated by a hard stop."""
    target = path or EVENTS
    if not target.exists():
        return []
    events = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
