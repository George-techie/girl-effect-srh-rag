"""The whole system.

    validate  →  SAFEGUARDING SCREEN  →  route
                          │                  ├─ out of scope  → approved text
                          │                  ├─ chat          → conversational
                          ↓                  └─ question      → resolve* → prepare*
                    approved text                               → retrieve → generate
                    0 model calls                               → check

    * conditional: resolution only for context-dependent turns, preparation
      only for factual and access ones. Neither is a universal stage.

Only `generate` uses a hosted generative LLM, and only on turns the decision
layer sends to it. Routing, safeguarding, resolution, query preparation and
validation are deterministic rules. Retrieval is neither: `bge-m3` runs locally,
so it costs no tokens but is still an ML encoder doing real compute — which is
why it has a measurable cold start, and why the app warms it before she asks.

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

import re
import time
from dataclasses import dataclass, field
from typing import Any

from src import config
from src import conversation as conversation_mod
from src import observability
from src import services
from src.conversation import Conversation
from src.prompt_files import loader
from src.decision import input_validation, rules
from src.llm.client import get_client
from src.rag import query_prep, rescue, retrieval
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



#: Routes the service table can be asked for. A tag outside this set falls back
#: to the broadest route rather than silently asking for something no row has.
_KNOWN_ROUTES = frozenset({
    "self_harm_risk", "sexual_violence", "intimate_partner_violence",
    "emotional_support", "contraception", "youth_friendly", "hiv_sti",
    "pregnancy_support",
})


def _route_for(decision) -> str:
    """The service route for a disclosure.

    Read straight off `decision.tags`, which the rules set explicitly. The
    earlier version scanned the reason string and the regex sources for
    substrings, which is how a self-harm disclosure ended up drawing
    sexual-violence services: the reason said "safeguarding · harm", the
    substring "harm" matched, and "self_harm" never appeared anywhere to check
    against.
    """
    for tag in decision.tags:
        if tag in _KNOWN_ROUTES:
            return tag
    return "emotional_support"




#: Which service route an access question should draw contacts from. Read off
#: her words, deterministically, because "where can I get tested" and "where can
#: I get the pill" need different rows and a second classifier would be a model
#: call to answer a question a regex answers.
_ACCESS_ROUTE = (
    (re.compile(r"\b(hiv|sti|std|test(ed|ing)?|prep)\b", re.I), "hiv_sti"),
    (re.compile(r"\b(pregnan\w+|antenatal|keep the baby|abortion)\b", re.I),
     "pregnancy_support"),
)


def _access_route(message: str) -> str:
    for pattern, route in _ACCESS_ROUTE:
        if pattern.search(message):
            return route
    return "contraception"


def _with_contacts(text: str, route: str, trace: dict[str, Any]) -> str:
    """Append verified contacts for a route, if any person has verified any.

    An empty table changes nothing: the approved text already names the *kind*
    of person who helps, which is useful on its own and is what she gets today.
    Nothing here is generated -- every character of a contact comes from a row
    a named person signed off, with a date.
    """
    found = services.block(route)
    if not found:
        trace["services"] = f"none verified for {route}"
        return text
    trace["services"] = [s.service_id for s in services.for_route(route)]
    return text + "\n\n" + found


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
    language = checked.language

    # The decision is made on her words alone, never on the conversation. A
    # safety floor that depends on state is a safety floor with a state bug in
    # it, and the floor is re-evaluated from scratch on every single turn.
    decision = rules.decide(message)
    trace: dict[str, Any] = {
        "path": decision.path,
        "why": decision.reason,
        "matched": decision.matched,
        "language": language,
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
        self_harm = "self_harm_risk" in decision.tags
        trace["help_requested"] = decision.help_requested
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

        trace["urgent"] = decision.urgent

        if self_harm:
            # Urgent risk. Contacts arrive with the opening rather than behind a
            # tap: the previous build measured that failure, where a girl who
            # did not tap saw less than one who disclosed something less
            # dangerous and did.
            return Reply(
                _with_contacts(responses.SELF_HARM, "self_harm_risk", trace),
                decision.path, trace=trace)

        # --- detect broadly, escalate narrowly ------------------------------
        # Pressure and conditional consent are safeguarding, and are answered as
        # safeguarding. They are not emergencies, and treating them as one gets
        # two things wrong: it reads as being passed on when she came to talk,
        # and at any real scale it buries the services in cases that were never
        # emergencies. She is acknowledged, told plainly what consent is, and
        # *offered* somewhere to go. The offer sits behind the tap.
        if not decision.urgent:
            trace["tier"] = "concern"
            followup = _with_contacts(
                responses.PRESSURE_FOLLOWUP, _route_for(decision), trace)
            if decision.help_requested:
                # She asked in the same message. Making her ask twice is the
                # opt-in applied backwards.
                trace["why"] += " · asked for help in the same message"
                return Reply(responses.PRESSURE + "\n\n" + followup,
                             decision.path, trace=trace)
            return Reply(responses.PRESSURE, decision.path, trace=trace,
                         followup=followup)

        # Force, threat, assault, or something already done to her. Contacts go
        # in front of her rather than behind a tap, for the reason the previous
        # build measured: a girl who did not tap saw less than one who disclosed
        # something less dangerous and did. The staged opt-in still exists -- it
        # is what the concern tier above uses -- but it is the wrong instrument
        # here, and this is the half of "escalate narrowly" that does escalate.
        trace["tier"] = "urgent"
        if decision.help_requested:
            trace["why"] += " · asked for help in the same message"
        return Reply(
            _with_contacts(
                responses.SAFEGUARDING + "\n\n"
                + responses.SAFEGUARDING_FOLLOWUP,
                _route_for(decision), trace),
            decision.path, trace=trace,
        )

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
    # Support joins chat here, and for the same reason rather than a similar
    # one: neither has anything to cite. A greeting makes no claim; a girl
    # saying she is frightened is not asking for a fact. Grounding support
    # turns retrieved somebody else's situation at 0.55-0.63 -- see
    # `Decision.grounded` for what came back -- and blocked the answer when it
    # could not cite it.
    if decision.path in (rules.CHAT, rules.SUPPORT):
        return _converse(message, decision, trace, started, history, language)

    # She disclosed earlier, and has now asked where to go without naming a
    # subject. That is not a contraception question and the corpus cannot answer
    # it -- measured: it resolved against her earlier question about the
    # implant, searched implant passages, found nothing about *where*, and
    # refused, at the single most important turn in the conversation.
    #
    # A message that names its own subject ("where can I get the pill?") is a
    # real access question and is left alone. This fires only on a fragment,
    # which is the shape of a girl asking for help.
    if (decision.path == rules.ACCESS and conversation is not None
            and conversation.disclosed
            and conversation_mod.is_dependent(message)):
        trace["why"] += " · asking where to go after a disclosure"
        trace["disclosed_earlier"] = True
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return Reply(
            _with_contacts(responses.WHERE_TO_GO_AFTER_DISCLOSURE,
                           _route_for(decision), trace),
            decision.path, trace=trace)

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

    # Clause-level retrieval. Her whole message still reaches the generator --
    # the emotional half is most of why she wrote and a reply must not ignore it
    # -- but it stops being used as the search query, where it drowned the
    # health question it was wrapped around. Experiment 4.
    hits, searched = retrieval.search_message(
        query.text, k=k or config.RETRIEVAL_TOP_K)
    if len(searched) > 1:
        trace["clauses_searched"] = searched

    # Third tier, and only when the first two came back measurably weak. The
    # deterministic table handles clean questions for free; clause splitting
    # handles mixed messages for free; this handles the rest, which is where
    # her vocabulary and the corpus's have no overlap for a bi-encoder to find
    # -- "i heard pills make someone anone" against "Do COCs cause women to
    # gain or lose a lot of weight?".
    #
    # Safe to use a model here and nowhere else in retrieval: it writes a search
    # string, never a word she reads. The kept result is the better of the two,
    # compared rather than assumed.
    attempt = rescue.maybe_rescue(hits, message, k=k or config.RETRIEVAL_TOP_K)
    if attempt.used:
        hits = attempt.hits
        trace["rescued"] = {"query": attempt.query,
                            "before": round(attempt.before or 0, 3),
                            "after": round(attempt.after or 0, 3)}
        trace["llm_calls"] = trace.get("llm_calls", 0) + 1
    trace["retrieved"] = [
        {"tag": h.metadata["citation_tag"], "page": h.metadata["page_pdf"],
         "section": h.metadata["section_title"], "similarity": round(h.similarity, 3),
         "role": h.metadata["document_role"]}
        for h in hits
    ]
    if not hits:
        # Empty is now a real outcome rather than an impossible one. Experiment
        # 4's evidence floor drops clauses that retrieved nothing above the
        # noise, so a message with no answerable question in it comes back with
        # nothing at all -- which is correct, and used to be unreachable because
        # retrieval always returned k rows however weak.
        #
        # A turn that only reached `factual` by default was never a lookup, so
        # telling her the sources do not cover it answers a question she did not
        # ask. *"Aki I just feel so alone since everyone at school found out"*
        # got exactly that.
        if decision.is_fallback:
            trace["fell_through"] = "nothing retrievable, and never a lookup"
            return _converse(message, decision, trace, started, history, language)
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
                language_label=language,
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
    trace["llm_calls"] = trace.get("llm_calls", 0) + 1
    trace["model"] = response.model
    trace["contract"] = "grounded"
    trace["seriousness"] = SERIOUSNESS.get(decision.path, "personal")

    # The generator read the passages and said they do not cover it. That
    # judgement stands, and it is not the same as the question being out of
    # scope -- the corpus was searched and came back thin.
    if draft.upper().startswith(INSUFFICIENT):
        trace["insufficient"] = True
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

        # Two very different turns end up here, and they need different replies.
        #
        # A turn that *matched* a factual or access pattern and then found no
        # evidence should say so plainly: she asked a question, the corpus was
        # searched, it came back thin, and pretending otherwise would be worse.
        #
        # A turn that only reached `factual` because nothing else matched was
        # never a lookup. Telling her "I don't have anything solid enough in my
        # sources" answers a question she did not ask, and reads as a brush-off
        # to a girl who was telling you about her friends and her sister.
        if decision.is_fallback:
            trace["fell_through"] = "not a lookup; nothing matched but the default"
            return _converse(message, decision, trace, started, history, language)

        return Reply(responses.NO_EVIDENCE, decision.path, trace=trace)

    # --- check ---------------------------------------------------------------
    issues, fatal = checks.check(draft, n_passages=len(hits))
    trace["issues"] = issues
    trace["fatal"] = fatal
    trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

    if fatal:
        # **Uncitable is not the same as unanswerable.** `factual` is the
        # fallback path, so anything that matched no other family lands here and
        # is then held to a contract requiring a citation. A girl writing
        # *"mabeste wangu wote wanakaa they are having sex, but mimi i just want
        # to study"* is not asking a factual question at all, and refusing her
        # over a missing citation answers a question she did not ask.
        #
        # So when the only thing wrong is that nothing could be cited, the turn
        # is re-answered under the conversational contract, which is safe for
        # the opposite reason: it makes no claim. The uncited draft is discarded
        # rather than shown -- it may well contain claims from the model's own
        # memory, which is exactly what it must not send.
        #
        # A fabricated marker, an invented phone number or a claim of lived
        # experience still blocks. Those are not vocabulary problems.
        if checks.only_missing_citation(issues):
            # Two different situations arrive here and only one of them is
            # "there was nothing to cite".
            #
            # If retrieval came back *strong* and the model still cited nothing,
            # the evidence was there and the generation failed. Measured at
            # temperature 0.3: the same message cited 4 times out of 5 and on the
            # fifth produced a warm reply that quietly dropped the factual half.
            # Falling straight through hides that, because a conversational
            # reply looks fine -- it just answers less than it could have.
            #
            # So it is retried once, with the omission named. Only a second
            # failure is treated as evidence that there was nothing to say.
            strong = bool(hits) and hits[0].similarity >= rescue.WEAK_BELOW
            if strong and not trace.get("retried"):
                trace["retried"] = True
                retry = _generate_grounded(
                    message, decision, hits, history, language,
                    insist=True,
                )
                if retry is not None:
                    redo, fatal_again = retry
                    if not fatal_again:
                        trace["llm_calls"] = trace.get("llm_calls", 0) + 1
                        trace["contract"] = "grounded"
                        trace["latency_ms"] = int(
                            (time.perf_counter() - started) * 1000)
                        return Reply(
                            text=checks.strip_markers(redo),
                            path=decision.path,
                            sources=_cited_sources(redo, hits),
                            trace=trace,
                        )
                    trace["llm_calls"] = trace.get("llm_calls", 0) + 1

            trace["fell_through"] = "grounded answer had nothing to cite"
            return _converse(message, decision, trace, started, history, language)
        return Reply(responses.BLOCKED, decision.path, trace=trace)

    # **The service handoff.** Girl Effect's Theory of Change ends at service
    # access, and an access turn that explains what kind of provider exists and
    # then stops has done the easy half. The corpus can say a community health
    # worker can give her pills; only the table can say which number to call.
    #
    # Appended after the answer rather than woven into it, because the model
    # must never write a contact -- these rows are read, and the validator
    # treats a generated phone number as fatal.
    answer_text = checks.strip_markers(draft)
    if decision.path == rules.ACCESS:
        answer_text = _with_contacts(
            answer_text, _access_route(message), trace)

    return Reply(
        text=answer_text,
        path=decision.path,
        sources=_cited_sources(draft, hits),
        trace=trace,
    )


def answer_stream(message: str, *, k: int | None = None,
                  conversation: Conversation | None = None,
                  out: dict[str, Any] | None = None):
    """Yield text deltas as they arrive, and put the finished `Reply` in `out`.

    **Only conversational turns stream, and that is a safety decision.**

    A grounded answer's fatal condition is *having no citation at all*, which is
    only knowable once the answer is complete. Streaming one would put uncited
    health claims on her screen and then discover they were uncited — which is
    precisely what the grounded contract exists to prevent. So a factual or
    access turn is generated, validated, and only then shown; the UI holds a
    typing indicator meanwhile, which is honest about the wait rather than
    hiding it.

    Conversational turns can stream because their fatal conditions -- a citation
    marker, an invented phone number -- are visible in partial text, so the
    stream is checked as it accumulates and cut the moment one appears.

    Turns answered from approved text never reach a model, so there is nothing
    to stream and nothing to wait for: they arrive whole, in 0 ms.
    """
    sink = out if out is not None else {}
    started = time.perf_counter()

    checked = input_validation.validate(message)
    decision = rules.decide(checked.text) if checked.ok else None

    if not checked.ok or decision.path not in (rules.CHAT, rules.SUPPORT):
        # Nothing safe to stream. Run it whole; the caller shows an indicator.
        sink["reply"] = answer(message, k=k, conversation=conversation)
        return

    text = checked.text
    trace: dict[str, Any] = {"path": decision.path, "why": decision.reason,
                             "matched": decision.matched, "llm_calls": 0}
    history = conversation.history_block() if conversation is not None else ""
    if conversation is not None:
        trace["turn"] = len(conversation.turns) // 2 + 1

    prompt = loader.load("converse")
    language = checked.language
    seriousness = SERIOUSNESS.get(decision.path, "personal")
    accumulated: list[str] = []
    cut = False

    try:
        stream = get_client().stream(
            "generation",
            prompt.messages(
                language_label=language, seriousness=seriousness,
                context_block="", history_block=history, message=text,
                situation=prompt.situation(SITUATION.get(decision.path, "explore"),
                                           prompt.situation("explore")),
            ),
            temperature=config.GENERATION_TEMPERATURE,
            max_tokens=config.CONVERSE_MAX_TOKENS,
        )
        while True:
            try:
                piece = next(stream)
            except StopIteration as done:
                response = done.value
                break
            accumulated.append(piece)
            # Checked as it accumulates, not after. A citation marker or a
            # phone-shaped string is fatal on this contract, and the point of
            # catching it here is to stop before more of it is on her screen.
            so_far = "".join(accumulated)
            if checks.MARKER.search(so_far) or checks.PHONE.search(so_far):
                cut = True
                stream.close()
                break
            yield piece
    except Exception as exc:  # noqa: BLE001
        trace["error"] = f"{type(exc).__name__}: {exc}"
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        sink["reply"] = Reply(responses.TECHNICAL, decision.path, trace=trace)
        _record(sink["reply"], message, conversation)
        return

    trace.update({"llm_calls": 1, "seriousness": seriousness,
                  "contract": "conversational", "streamed": not cut})

    if cut:
        # She saw a partial reply. Replacing it is the lesser harm: what was
        # forming had a fabricated reference or a number in it.
        trace["issues"] = ["stream cut: citation marker or phone number forming"]
        trace["fatal"] = True
        trace["latency_ms"] = int((time.perf_counter() - started) * 1000)
        sink["reply"] = Reply(responses.BLOCKED, decision.path, trace=trace)
        _record(sink["reply"], message, conversation)
        return

    draft = response.text.strip()
    trace["model"] = response.model
    issues, fatal = checks.check(draft, n_passages=0, grounded=False)
    trace["issues"], trace["fatal"] = issues, fatal
    trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

    sink["reply"] = Reply(responses.BLOCKED if fatal else checks.strip_markers(draft),
                          decision.path, trace=trace)
    _record(sink["reply"], message, conversation)


def _record(reply: Reply, message: str, conversation: Conversation | None) -> None:
    """The bookkeeping `answer` does in its wrapper, for the streaming path."""
    violations = observability.record(
        trace=reply.trace, reply_path=reply.path, n_sources=len(reply.sources),
        text=reply.text, message=message,
        turn=(len(conversation.turns) // 2 + 1) if conversation else None,
    )
    if violations:
        reply.trace["violations"] = [{"name": v.name, "detail": v.detail}
                                     for v in violations]
    if conversation is not None:
        conversation.record_her(message, reply.path)
        conversation.record_aunti(reply.text, reply.path)


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
              history: str = "", language: str = "kenyan_english") -> Reply:
    """A reply written with no passages, and forbidden from stating a fact."""
    prompt = loader.load("converse")
    seriousness = SERIOUSNESS.get(decision.path, "personal")
    try:
        response = get_client().complete(
            "generation",
            prompt.messages(
                language_label=language,
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
    trace.update({"llm_calls": trace.get("llm_calls", 0) + 1,
                  "model": response.model,
                  "seriousness": seriousness, "contract": "conversational"})

    issues, fatal = checks.check(draft, n_passages=0, grounded=False)
    trace["issues"] = issues
    trace["fatal"] = fatal
    trace["latency_ms"] = int((time.perf_counter() - started) * 1000)

    if fatal:
        return Reply(responses.BLOCKED, decision.path, trace=trace)
    return Reply(checks.strip_markers(draft), decision.path, trace=trace)


#: Appended only on a retry. Names the exact omission rather than repeating the
#: whole contract, because the model already had the contract and followed every
#: other part of it.
INSIST = (
    "\n\nYour previous attempt answered without citing anything. The passages "
    "above do contain material relevant to her question. Answer it now, and put "
    "the [S...] tag at the end of every sentence that states a fact from them. "
    "Keep the warmth and the acknowledgement exactly as you had them."
)


def _generate_grounded(message, decision, hits, history, language,
                       *, insist: bool = False):
    """One grounded generation. Returns ``(draft, fatal)`` or None on error.

    Split out so the retry path is the same code as the first attempt, rather
    than a second copy that can drift away from it.
    """
    prompt = loader.load("answer")
    question = message + (INSIST if insist else "")
    try:
        response = get_client().complete(
            "generation",
            prompt.messages(
                language_label=language,
                seriousness=SERIOUSNESS.get(decision.path, "personal"),
                context_block="",
                history_block=history,
                context=_context(hits),
                question=question,
            ),
            temperature=config.GENERATION_TEMPERATURE,
            max_tokens=config.GENERATION_MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001
        return None

    draft = response.text.strip()
    if draft.upper().startswith(INSUFFICIENT):
        return draft, True
    _issues, fatal = checks.check(draft, n_passages=len(hits))
    return draft, fatal
