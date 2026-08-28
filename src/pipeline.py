"""The whole system.

    decide  →  retrieve  →  generate  →  check

Four steps, one model call, and the model is only reached on turns the decision
layer sends to it. Everything else — the decision, the retrieval, the checks —
is deterministic and free.

What is deliberately not here, and why, with the measurement in each case:

  evidence judge     the previous build's own ablation: +6 unhelpful refusals
                     to prevent one unsafe case that sits inside the variance
                     floor of ~3 cases in 51
  output judge       what refused a girl's compliment twice. Its deterministic
                     half is in safety/checks.py and does the work
  turn planner       replaced by rules: 51 of 52 with precision 1.000
  query restatement  measured as helping factual and access turns and actively
                     harming support and disclosure ones. The oracle showed the
                     ceiling; an automatic version is the next experiment, not
                     a shipped feature
  conversation memory  nothing has measured that this demo needs it
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src import config, prompts
from src.decision import rules
from src.llm.client import get_client
from src.rag import retrieval
from src.safety import checks, responses

INSUFFICIENT = "INSUFFICIENT_CONTEXT"


@dataclass
class Reply:
    text: str
    path: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    #: Everything the demo's "how it decided" panel shows. Recorded whether or
    #: not anyone looks, so a bad answer can be explained after the fact.
    trace: dict[str, Any] = field(default_factory=dict)
    followup: str | None = None


def _context(hits: list[retrieval.Hit]) -> str:
    return "\n\n".join(
        f"[S{i}] {h.metadata['citation_tag']} · p.{h.metadata['page_pdf']} · "
        f"{h.metadata['section_title']}\n{h.text}"
        for i, h in enumerate(hits, 1)
    )


def _cited_sources(draft: str, hits: list[retrieval.Hit]) -> list[dict[str, Any]]:
    """Only the passages the answer actually used, deduplicated.

    Built from metadata rather than from anything the model wrote, which is what
    makes a fabricated source name impossible rather than merely discouraged.
    """
    used, seen = [], set()
    for n in checks.MARKER.findall(draft):
        i = int(n)
        if not 1 <= i <= len(hits) or i in seen:
            continue
        seen.add(i)
        meta = hits[i - 1].metadata
        used.append({
            "tag": meta["citation_tag"],
            "page": meta["page_pdf"],
            "section": meta["section_title"],
            "role": meta["document_role"],
            "excerpt": hits[i - 1].text[:400],
        })
    return used


def answer(message: str, *, k: int | None = None) -> Reply:
    started = time.perf_counter()
    decision = rules.decide(message)
    trace: dict[str, Any] = {
        "path": decision.path,
        "why": decision.reason,
        "matched": decision.matched,
        "llm_calls": 0,
    }

    # --- the safety floor, before anything is searched ----------------------
    # Retrieval cannot decline: a deliberately out-of-scope question was
    # measured retrieving at 0.691, above most in-scope ones. So the decision is
    # made on her words, and these two paths never reach the corpus at all.
    if decision.path == rules.SAFEGUARDING:
        self_harm = "self_harm_risk" in decision.matched
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(
            text=responses.SELF_HARM if self_harm else responses.SAFEGUARDING,
            path=decision.path,
            trace=trace,
            followup=None if self_harm else responses.SAFEGUARDING_FOLLOWUP,
        )

    if decision.path == rules.OUT_OF_SCOPE:
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.OUT_OF_SCOPE, decision.path, trace=trace)

    # --- retrieve ------------------------------------------------------------
    hits = retrieval.search(message, k=k or config.RETRIEVAL_TOP_K)
    trace["retrieved"] = [
        {"tag": h.metadata["citation_tag"], "page": h.metadata["page_pdf"],
         "section": h.metadata["section_title"], "similarity": round(h.similarity, 3),
         "role": h.metadata["document_role"]}
        for h in hits
    ]
    if not hits:
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.NO_EVIDENCE, decision.path, trace=trace)

    # --- generate ------------------------------------------------------------
    try:
        response = get_client().complete(
            "generation",
            [
                {"role": "system", "content": prompts.ANSWER_SYSTEM},
                {"role": "user", "content": prompts.ANSWER_USER.format(
                    context=_context(hits), question=message)},
            ],
            temperature=config.GENERATION_TEMPERATURE,
            max_tokens=config.GENERATION_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        # A provider error reaching her as a refusal is indistinguishable from
        # "we have nothing for you", and she has no way to know it is worth
        # retrying.
        trace["error"] = f"{type(exc).__name__}: {exc}"
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.TECHNICAL, decision.path, trace=trace)

    draft = response.text.strip()
    trace["llm_calls"] = 1
    trace["model"] = response.model

    # The generator read the passages and said they do not cover it. That
    # judgement stands, and it is not the same as the question being out of
    # scope -- the corpus was searched and came back thin.
    if draft.upper().startswith(INSUFFICIENT):
        trace["insufficient"] = True
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.NO_EVIDENCE, decision.path, trace=trace)

    # --- check ---------------------------------------------------------------
    issues, fatal = checks.check(draft, n_passages=len(hits))
    trace["issues"] = issues
    trace["fatal"] = fatal
    trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

    if fatal:
        return Reply(responses.BLOCKED, decision.path, trace=trace)

    return Reply(
        text=checks.strip_markers(draft),
        path=decision.path,
        sources=_cited_sources(draft, hits),
        trace=trace,
    )
