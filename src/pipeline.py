"""The whole system.

    decide  →  resolve  →  prepare  →  retrieve  →  generate  →  check

Only `generate` costs anything. The other five are rules.

Six steps, one model call, and the model is only reached on turns the decision
layer sends to it. Everything else — the decision, the retrieval, the checks —
is deterministic and free.

What is deliberately not here, and why, with the measurement in each case:

  evidence judge     the previous build's own ablation: +6 unhelpful refusals
                     to prevent one unsafe case that sits inside the variance
                     floor of ~3 cases in 51
  output judge       what refused a girl's compliment twice. Its deterministic
                     half is in safety/checks.py and does the work
  turn planner       replaced by rules: 51 of 52 with precision 1.000
  query rewriting    a model call to rewrite her question. The deterministic
                     table in rag/query_prep.py got Adequate@5 from 0.880 to
                     0.960 with no question regressing, for no tokens. A model
                     would have to beat that, not merely work
  conversation memory  bounded to six turns in conversation.py, and it is state
                     rather than memory: no summariser, no entity tracker, no
                     profile. Measured: a follow-up fragment retrieved material
                     about sterilisation until it could see the turn before it
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src import config
from src import conversation as conversation_mod
from src import observability
from src.conversation import Conversation
from src.prompt_files import loader
from src.decision import input_validation, rules
from src.llm.client import get_client
from src.rag import query_prep, retrieval
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


def answer(message: str, *, k: int | None = None,
           conversation: Conversation | None = None) -> Reply:
    """One turn, and the record of it.

    `conversation` is optional. Without it this behaves exactly as it did
    before, which is what keeps every single-turn evaluation still valid.

    Recording brackets the turn rather than sitting inside it: her message must
    not appear in its own history block, and the reply is recorded on every
    return path -- including the safeguarding ones, which leave early.
    """
    reply = _answer(message, k=k, conversation=conversation)

    # One event per turn, on every path -- including the ones that return early.
    # Wrapping rather than instrumenting each return is the point: a branch
    # added later is observed by default instead of being the one nobody
    # remembered to log, which is how the early-return paths stayed invisible.
    violations = observability.record(
        trace=reply.trace, reply_path=reply.path, n_sources=len(reply.sources),
        text=reply.text, message=message,
        turn=(len(conversation.turns) // 2 + 1) if conversation else None,
    )
    if violations:
        reply.trace["violations"] = [
            {"name": v.name, "detail": v.detail} for v in violations
        ]

    if conversation is not None:
        conversation.record_her(message, reply.path)
        conversation.record_aunti(reply.text, reply.path)
    return reply


def _answer(message: str, *, k: int | None = None,
            conversation: Conversation | None = None) -> Reply:
    started = time.perf_counter()

    # The front door. Nothing unusable reaches routing, the encoder or a model.
    checked = input_validation.validate(message)
    if not checked.ok:
        return Reply(
            responses.TOO_LONG if "longer" in checked.reason
            else responses.EMPTY_INPUT,
            "invalid_input",
            trace={"path": "invalid_input", "why": checked.reason,
                   "llm_calls": 0, "latency_ms": 0},
        )

    message = checked.text

    # The decision is made on her words alone, never on the conversation. A
    # safety floor that depends on state is a safety floor with a state bug in
    # it, and the floor is re-evaluated from scratch on every single turn.
    decision = rules.decide(message)
    trace: dict[str, Any] = {
        "path": decision.path,
        "why": decision.reason,
        "matched": decision.matched,
        "llm_calls": 0,
    }

    if conversation is not None:
        # Built from prior turns only -- this message arrives separately, as
        # "her message just now", and a prompt that shows it in both places
        # invites the model to answer it twice.
        history = conversation.history_block()
        trace["turn"] = len(conversation.turns) // 2 + 1
        if conversation.disclosed:
            # Sticky within the session. It never softens the floor -- it only
            # stops a girl who told us about coercion four turns ago being
            # handled as an anonymous first-time asker when she finally asks
            # where to go.
            trace["disclosed_earlier"] = True
    else:
        history = ""

    # --- the safety floor, before anything is searched ----------------------
    # Retrieval cannot decline: a deliberately out-of-scope question was
    # measured retrieving at 0.691, above most in-scope ones. So the decision is
    # made on her words, and these two paths never reach the corpus at all.
    if decision.path == rules.SAFEGUARDING:
        self_harm = "self_harm_risk" in decision.matched
        trace["help_requested"] = decision.help_requested
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

        if self_harm:
            # Urgent risk. Contacts arrive with the opening rather than behind a
            # tap: the previous build measured that failure, where a girl who
            # did not tap saw less than one who disclosed something less
            # dangerous and did.
            return Reply(responses.SELF_HARM, decision.path, trace=trace)

        if decision.help_requested:
            # She disclosed AND asked where to go, in one message. Holding the
            # pathway behind a button here applies the opt-in backwards: it
            # exists so a girl who has *not* asked is not handed everything at
            # once while distressed, never to make someone who has asked, ask
            # twice. The acknowledgement still comes first and unchanged.
            trace["why"] += " · asked for help in the same message"
            return Reply(
                responses.SAFEGUARDING + "\n\n" + responses.SAFEGUARDING_FOLLOWUP,
                decision.path, trace=trace,
            )

        # Support first, offer the option. She chooses whether to receive it,
        # which keeps the first message short enough to read while distressed.
        return Reply(responses.SAFEGUARDING, decision.path, trace=trace,
                     followup=responses.SAFEGUARDING_FOLLOWUP)

    if decision.path == rules.OUT_OF_SCOPE:
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.OUT_OF_SCOPE, decision.path, trace=trace)

    # --- the conversational contract -----------------------------------------
    # A greeting has nothing to look up and nothing to cite. Answering it under
    # the grounded contract -- which requires a citation -- is what turned
    # "hello aunti" into "I had trouble putting that answer together".
    #
    # Safe for the opposite reason to a grounded answer: that one is safe
    # because every claim is cited, this one because it makes no claim at all.
    if decision.path == rules.CHAT:
        return _converse(message, decision, trace, started, history)

    # --- retrieve ------------------------------------------------------------
    # The query the encoder sees is not always the message. On factual and
    # access turns her words get the corpus's vocabulary appended -- measured at
    # Adequate@5 0.880 -> 0.960 with no question regressing. On every other
    # path `restate` is False and the query is her message verbatim, which is
    # the condition that keeps support turns pointed at material written for
    # her rather than policy literature about her.
    #
    # Before that, a dependent fragment gets its antecedent back. "and does it
    # hurt?" asked after a question about the implant retrieved *female
    # sterilization*; "where can I go?" after a coercion disclosure retrieved
    # *BTL*, which is permanent. Both are answers to a question she did not ask.
    followup = conversation_mod.resolve(message, conversation,
                                        retrieves=decision.retrieves)
    # Recorded whether or not it resolved. A fragment that found no antecedent
    # is the shape the trimmed-topic defect made, and it was invisible because
    # nothing wrote down that the message needed one in the first place.
    trace["dependent"] = conversation_mod.is_dependent(message)
    if followup.resolved:
        trace["resolved_from"] = followup.antecedent

    query = query_prep.prepare(followup.text, restate=decision.restate)
    trace["query"] = query.text
    trace["query_prepared"] = query.restated
    if query.restated:
        trace["query_mappings"] = query.applied

    hits = retrieval.search(query.text, k=k or config.RETRIEVAL_TOP_K)
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
    # Both contracts are rendered by the same loader from the same persona.
    # They were two implementations until now -- the conversational path got
    # persona.yaml with its tone notes, emoji policy and register mirroring,
    # while the grounded path got a second persona written by hand. A girl
    # cannot see which path her message took, so a warm greeting followed by a
    # flatter answer reads as the service losing interest in her.
    prompt = loader.load("answer")
    try:
        response = get_client().complete(
            "generation",
            prompt.messages(
                language_label="",
                seriousness=SERIOUSNESS.get(decision.path, "personal"),
                context_block="",
                history_block=history,
                context=_context(hits),
                question=message,
            ),
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
    trace["contract"] = "grounded"
    trace["seriousness"] = SERIOUSNESS.get(decision.path, "personal")

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


#: How gravely to speak, derived from the path rather than from a second model
#: call. The previous build made this a separate axis for a measured reason: a
#: model shown all four tone notes produces their average, the register that
#: fits nothing. So one note is selected and only that one is sent.
SERIOUSNESS = {
    rules.CHAT: "casual",
    rules.FACTUAL: "factual",
    rules.ACCESS: "factual",
    rules.SUPPORT: "personal",
}

#: Which situation note the conversational prompt gets. `greeting` says what the
#: service can help with and stops; `support` acknowledges before anything else.
SITUATION = {rules.CHAT: "greeting", rules.SUPPORT: "support"}


def _converse(message: str, decision, trace: dict, started: float,
              history: str = "") -> Reply:
    """A reply written with no passages, and forbidden from stating a fact."""
    prompt = loader.load("converse")
    seriousness = SERIOUSNESS.get(decision.path, "personal")
    try:
        response = get_client().complete(
            "generation",
            prompt.messages(
                language_label="",
                seriousness=seriousness,
                context_block="",
                history_block=history,
                message=message,
                situation=prompt.situation(SITUATION.get(decision.path, "explore"),
                                           prompt.situation("explore")),
            ),
            temperature=config.GENERATION_TEMPERATURE,
            max_tokens=config.CONVERSE_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        trace["error"] = f"{type(exc).__name__}: {exc}"
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(responses.TECHNICAL, decision.path, trace=trace)

    draft = response.text.strip()
    trace.update({"llm_calls": 1, "model": response.model,
                  "seriousness": seriousness, "contract": "conversational"})

    issues, fatal = checks.check(draft, n_passages=0, grounded=False)
    trace["issues"] = issues
    trace["fatal"] = fatal
    trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

    if fatal:
        return Reply(responses.BLOCKED, decision.path, trace=trace)
    return Reply(checks.strip_markers(draft), decision.path, trace=trace)
