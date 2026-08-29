# Trusted Aunti — sexual and reproductive health, for adolescent girls in Kenya

A safety-aware assistant answering questions about **contraception, sexual
health, staying safe, and how to reach a service** — grounded in eight governed
documents, with a deterministic safety floor above it.

This is a **refined** build. The feedback on the previous one was that it was
overengineered in places, and this repository is the answer to that: the same
solution philosophy, with every component either justified by a measurement or
deleted.

```mermaid
flowchart TD
    HER["Her message"]:::her

    VAL["<b>1 · Validate</b><br/>reject empty, non-text, over 2000 chars<br/><i>her words otherwise untouched — no<br/>sanitising of Sheng, emoji or case</i>"]:::free

    DEC{"<b>2 · Decide</b><br/>ordered rules + Kenyan lexicon<br/>reads her words alone, never the conversation"}:::decide

    SAFE["<b>Safeguarding</b><br/>approved text, never generated"]:::approved
    OOS["<b>Out of scope</b><br/>approved text"]:::approved
    HELP["<b>Asked where to go,<br/>after a disclosure</b><br/>help pathway, approved text"]:::approved
    CHAT["<b>Conversational contract</b><br/>no passages · claims nothing"]:::model

    RES["<b>3 · Resolve</b><br/>give a fragment its antecedent<br/><i>retrieval query only</i>"]:::free
    PREP["<b>4 · Prepare</b><br/>append the corpus's vocabulary<br/><i>factual and access turns only</i>"]:::free
    RET["<b>5 · Retrieve</b><br/>bge-m3 local · ChromaDB cosine · top-5"]:::free
    GEN["<b>6 · Generate</b><br/>grounded contract · every claim cited"]:::model
    CHK["<b>7 · Check</b><br/>fabricated citation · phone number ·<br/>claimed experience · machinery talk"]:::free

    REPLY["Her reply, with sources"]:::her
    EVT[("<b>8 · Event</b><br/>one per turn<br/>+ invariants")]:::obs

    HER --> VAL --> DEC

    DEC -->|"disclosure of harm"| SAFE
    DEC -->|"deliberately not covered"| OOS
    DEC -->|"greeting · thanks · her ambitions"| CHAT
    DEC -->|"fragment + disclosed earlier"| HELP
    DEC -->|"factual · access · support"| RES

    RES --> PREP --> RET --> GEN --> CHK

    SAFE --> REPLY
    OOS --> REPLY
    HELP --> REPLY
    CHAT --> REPLY
    CHK -->|"fatal → blocked"| REPLY
    CHK --> REPLY

    REPLY -.-> EVT

    classDef her fill:#5B2340,stroke:#5B2340,color:#fff,font-weight:bold
    classDef free fill:#E8F4F3,stroke:#0E7A86,color:#123
    classDef decide fill:#0E7A86,stroke:#0E7A86,color:#fff,font-weight:bold
    classDef approved fill:#FBEAE4,stroke:#C04B2F,color:#123,font-weight:bold
    classDef model fill:#FFF4D6,stroke:#B8860B,color:#123,font-weight:bold
    classDef obs fill:#EFEAF2,stroke:#5B2340,color:#123
```

**One model call, and only on turns the decision layer sends to it — never on a
disclosure of harm.** Teal is deterministic: free, instant, auditable. Rust is
human-approved text that is never generated. Gold is the model.

Roughly a third of turns never reach a model at all, and they are the turns
where that matters most — every safeguarding reply is instant, because a girl
who has just disclosed coercion should not wait on a network round trip.

Four more diagrams in **[`docs/architecture.md`](docs/architecture.md)**: why
the safety floor runs *before* retrieval, the two output contracts, what state
is and is not kept, and where the evidence comes from.

---

## What was removed, and what it cost to find out

Removing things is the easy half. Knowing which ones is the work, so every
removal here has a number attached.

| Removed | The measurement |
|---|---|
| **LLM evidence judge** | The previous build's own ablation: it bought **+6 unhelpful refusals** to prevent one unsafe case, inside a variance floor of ~3 in 51 |
| **LLM output judge** | It refused a girl's compliment. Twice. Its non-opinion half is [`src/safety/checks.py`](src/safety/checks.py) -- deterministic, free, and doing the actual work |
| **LLM turn planner** | Replaced by ordered rules: **52/52** on the decision benchmark, safeguarding precision **1.000** |
| **LLM query rewriter** | Never built. A string table got Adequate@5 **0.880 → 0.960** for zero tokens. A model would have to beat that, not merely work |
| **Five model roles → one** | Nothing measured that the others earned their latency |
| **Two content tracks (mental health, menstruation)** | Out of scope as *topics*. Not out of scope as *risk* — see below |
| **`rag/citations.py`** | Unreferenced. Deleted |

**Added back, and why.** Two things this build originally left out are now in it,
both because a measurement asked for them rather than because they seemed like
good ideas: **conversation state**, after replaying a real journey retrieved
material about sterilisation for a girl asking a follow-up about the implant; and
**observability**, after three defects in one afternoon were all found by a person
reading output by hand. Neither is a model call. Both are covered below.

**What was kept, for the same reason.** The decision layer, the safety floor, the
citation contract and the deterministic validator all stayed, because each has a
measured failure behind it. Minimum justified complexity is not fewest parts.

---

## The one distinction the whole design rests on

**Narrowing what the product answers does not narrow what it must not walk past.**

The scope is contraception and sexual health. But a girl who asks about the pill
and then says her boyfriend threatened to leave her if she keeps taking it has
not changed the subject — she has told you something the product must handle
whether or not it is "in scope".

So there are two different things, and they are sized differently:

- **The safeguarding floor is risk-based and universal.** Self-harm, violence,
  coercion, third-party disclosure. It does not shrink when the topic list does.
- **The answering vocabulary is domain-scoped.** It shrank with the scope, and
  five old-scope terms were removed from the Kenyan lexicon in a recorded pass.

Written up as [D-01](docs/decisions.md). **Reproductive coercion** was added as a
safeguarding category for this scope ([D-02](docs/decisions.md)) — including
contraceptive sabotage, pressure to stop a method, and consent made conditional.

---

## Two output contracts

Every reply is written under one of two contracts, and **which one is chosen by
provenance, never inferred from whether citations happen to be present.**

|  | **Grounded** | **Conversational** |
|---|---|---|
| Used for | factual, access, support | greetings, thanks, small talk |
| Safe because | every claim carries a citation | it makes **no claim at all** |
| Uncited claim | fatal, blocked | fatal, blocked |
| Citation marker | required | fatal — a marker with no passage looks *more* verified than an uncited claim |

This split is what stopped *"hello aunti"* being answered under a contract
requiring a citation — which is how the previous build turned a greeting into
*"I had trouble putting that answer together."*

Both contracts render from **one persona file**. They were two hand-written
personas until a merge, and the reason is not tidiness: a girl cannot see which
path her message took, so a warm greeting followed by a flatter answer reads as
the service losing interest in her.

---

## What is measured

Four evaluations, each with criteria fixed **before** the run. Full write-ups in
[`evaluation/`](evaluation/).

### Decision layer — 52 messages
```
overall accuracy       1.000   (52/52)
safeguarding recall    1.000   (12/12)
safeguarding precision 1.000   (12/12)
contrast pairs           6/6
```
The contrast pairs are the point: six pairs that share a surface form and need
different paths. *"My boyfriend doesn't like condoms"* is support; *"my boyfriend
says he'll leave me if I don't stop taking the pill"* is safeguarding.

### Retrieval — 31 questions, tagged by Theory-of-Change driver
```
Hit@5 0.963 · Recall@5 0.586 · MRR 0.920 · Adequate@5 0.960
```
Gold labels are **source-level**, so Hit@5 is an optimistic upper bound and is
reported as one. `Adequate@5` is the floor under it — a coarse phrase check for
whether a retrieved passage plausibly *answers* her, which is a different
question from whether the right document came back.

Questions are tagged by the **eight behavioural drivers** in Girl Effect's
Theory of Change, not by generic RAG categories, because **knowledge is one
driver of eight**. A retriever measured only on factual questions looks flawless
while failing the drivers that actually lead to service access — and this one
did: knowledge MRR **1.000** while self-identity sat at **0.417**.

### Experiment 1 — source role preference · **rejected**
A soft score bonus on youth-facing sources. Swept seven strengths; it moved
youth material to the top without improving what the answers could support.
Rejected, `role_bonus` left at 0.0.

### Experiment 2 — oracle restatement · **ceiling established, feature refused**
Hand-written retrieval queries. Adequate@5 1.000, agency mean 0.889 — and two
findings that became constraints rather than a feature: restating **support**
turns pulled retrieval toward policy literature *about* her, and restating an
**out-of-scope** question made it retrieve *more* confidently (0.668 → 0.691).

### Experiment 3 — deterministic query preparation · **adopted**
Her words with the corpus's vocabulary appended, from a fixed table.

| | natural | prepared | oracle |
|---|--:|--:|--:|
| Adequate@5 | 0.880 | **0.960** | 1.000 |
| MRR | 0.883 | **0.920** | 0.864 |
| agency mean | 0.611 | **0.750** | 0.889 |

Zero per-question regressions. **All four boundary cases are bit-identical to
baseline**, because the gate — factual and access turns only, and only after the
decision — never opens for them. That is Experiment 2's constraint doing its job
in the shipped system rather than in a note.

Mappings are labelled `evidenced` or `extrapolated` **in the source code**. Three
come from measured failures; seven are the same kind of gap written from the
corpus's own section titles. Tuning a table against the set you then report on
measures the tuning, not the layer.

---

## Multi-turn, because she arrives with a conversation

A girl does not send a query. She moves — contraception, what she wants to be,
something he said, then where she can actually go — and the turns that carry a
conversation are the shortest ones. Scored one at a time, they looked fine.
Replayed as a journey, four things broke and two were safety-relevant:

| Her turn | What came back |
|---|---|
| *"and does it hurt?"* after asking about the implant | **female sterilization**, 0.593 |
| *"where can I go?"* after disclosing coercion | **BTL** — permanent sterilisation, 0.508 |
| *"is it free?"* | "Clients rights", 0.484 |
| *"I want to be a doctor, I'm the first in my family to finish school"* | routed to `factual`, answered from contraception passages |

[`src/conversation.py`](src/conversation.py) is **state, not memory**: six turns,
one topic, one flag, all by rules. No summariser, no entity tracker, no profile,
nothing written down about her. Three boundaries are pinned by tests:

1. **The decision still reads her words alone.** A safety floor that depends on
   conversational state is a safety floor with a state bug in it.
2. **Resolution touches the retrieval query only** — the same split that made
   query preparation safe.
3. **It is bounded and it forgets.**

The rehearsal found one more, and it was the worst-placed failure in the build.
She discloses coercion, then asks *"where can I go?"* — and it resolved against
her earlier question about the **implant**, searched implant passages, found
nothing about *where*, and refused. At the exact turn she asked for help. Then
apologised for it on the next turn.

A subjectless question after a disclosure is a request for help, not a
contraception question, and it is now answered from approved text with no model
call. *"Where can I get the pill?"* names its own subject and is still a real
access question. The `disclosed` flag existed for this and was doing nothing.

Measured with `python scripts/eval_multiturn.py` over four journeys, 23 turns:
**forbidden passages 1 → 0**, path accuracy 21/23 either way. The two
disagreements are disputed labels — mine — left uncorrected and documented in
the dataset rather than quietly fixed to make a criterion pass.

---

## Observability, because otherwise you are guessing

Three defects were found in this codebase in a single afternoon. **Every one was
found by a person reading output by hand:** the phone check firing on page
numbers, the conversation topic being trimmed before it was used, and
`Decision.retrieves` disagreeing with the pipeline. None is exotic — they are the
normal failure mode of a system with several deterministic layers. A component
quietly stops doing what its name says, every answer still looks plausible, and
nothing anywhere counts. Reading output by hand does not scale past a demo.

[`src/observability.py`](src/observability.py) writes **one event per turn** —
the pipeline already assembled a full trace for the demo panel and then threw it
away — and checks **invariants at runtime**. Each invariant exists because
something here has already failed in that exact shape:

| Invariant | The failure behind it |
|---|---|
| a path that must not search, searching | `Decision.retrieves` and the pipeline disagreed for weeks |
| grounded answer with zero cited sources | the citation-example defect that took three wrong theories to find |
| conversational answer carrying sources | a marker with no passage looks *more* verified than an uncited claim |
| a signal set and read by nobody | `urgent` was written to the trace and consumed by nothing, so a girl at risk of self-harm saw *less* than one who disclosed something less dangerous |
| a fragment that found no antecedent | the trimmed-topic defect, invisible until printed by hand |
| more than one model call in a turn | cost regressions should be visible before the bill is |

Violations are **recorded, never raised**. A monitoring layer that can take down
the service has inverted its own purpose.

```bash
python scripts/inspect_events.py            # what is wrong, anomalies first
python scripts/inspect_events.py --violations
```

It found two things within a minute of existing:

**A 39,479 ms first turn**, against a 5,406 ms median — the encoder loads lazily,
so the first search paid for it. A median latency chart showed nothing wrong, and
the girl who waits 39 seconds is by definition the one asking her first question.
The app now warms the encoder at startup.

**The `access` turn returned no evidence.** *"Where can I go?"* retrieved
adequately (0.659) and the generator correctly said the passages could not answer
it — because the corpus has no service directory. Girl Effect's Theory of Change
runs drivers → intent → **service access** → behaviour change, so events carry a
journey stage as well as a route. The terminal stage is the one this system
currently cannot serve, and that is now a number rather than an intuition.

### Logging adolescent girls' disclosures

An event log for a safeguarding product is a surveillance database with a
dashboard on it, and the girls most at risk from that are the ones it exists for.
So the default stream is **operational only** — paths, timings, similarity, flags,
issue names. No message text, no reply text, no identifier for her, no session id
that survives a restart. Text is written only under an explicit `TRACE_MESSAGES=1`
for a developer replaying a bug locally. You can learn from the default stream
that fragments are failing to resolve. You cannot learn who said what.

---

## What is known to be wrong

**The phone-number check was firing on page numbers.** Run over the corpus, the
short-code half of the regex matched 9 chunks -- every one a page reference,
*"see LNG-IUD for Women With HIV, p. 199"*. That check is **fatal**, so a
generated answer citing p. 116 would have been blocked and the girl would have
got a refusal. Rewritten to the actual four-digit Kenyan short codes plus 116
only where something nearby presents it as a number to call: **0 corpus matches**,
and every fabricated-contact case still caught. The regression test carries both
directions.

This one is worth naming because of how it was found. It was not found by a
test, a judge or a review -- it was found by checking whether a claim in this
README was true, and it was not.

**Recall@5 fell 0.012 under query preparation.** One question's worth, inside the
noise of 31. Reported because it moved.

**Two service contacts are `unverified` and the system will not surface them.**
They were carried over from the previous build with no source, date or checker.
A table whose column says `verified_at` is worthless if the dates in it were
invented, so they stay unverified and unreachable until a person confirms them.
The schema, the fillable Word document and the guidance are all in place:
[`data/services/`](data/services/).

**78% of corpus chunks are provider guidance** — 1,326 clinical against 58
youth-facing. The facts are right; the reader they were written for is a
clinician. Query preparation narrows this, it does not fix it.

**Kiswahili costs −0.062 similarity**, over five matched pairs. Direct
translation is handled; idiomatic Sheng is not. *"Inaharibu mji wa mtoto"* is a
metaphor, and it retrieved a policy report where its English twin found the
myth-correcting passage immediately — which is what the lexicon and one query
mapping now exist for.

**Boundary cases retrieve confidently.** *"My periods have been irregular for
three months"* — deliberately out of scope — retrieves at **0.668, above most
in-scope questions**. Retrieval cannot decline. That is the entire argument for
deciding **before** searching, on her words, which is what the pipeline does.

---

## Quick start

```bash
pip install -r requirements.txt
python scripts/ingest.py                            # build the index
streamlit run app.py                                # the demo
```

```bash
python -m pytest -q                                 # 120 tests
python scripts/eval_decision.py                     # 52/52
python scripts/eval_retrieval.py                    # Hit@5, MRR, by driver
python scripts/eval_retrieval.py --compare-prepared # Experiment 3
python scripts/eval_multiturn.py                    # four journeys, 23 turns
python scripts/inspect_events.py                    # read the event log
```

Embeddings are **local** (`BAAI/bge-m3`) — no per-query embedding cost, and no
girl's question leaves the machine to be embedded. Generation runs through
OpenRouter on `anthropic/claude-sonnet-5`; set `OPENROUTER_API_KEY` in `.env`.

---

## Layout

```
src/
  pipeline.py            the whole system, ~380 lines
  conversation.py        six turns, one topic, one flag — state, not memory
  observability.py       one event per turn, invariants checked at runtime
  decision/
    rules.py             ordered deterministic router, 6 paths
    input_validation.py  the front door
  rag/
    query_prep.py        Experiment 3 — the mapping table
    retrieval.py         cosine search over ChromaDB
    chunking.py          500/650/0, section-aware
  safety/
    checks.py            deterministic output validation, no model
    responses.py         approved text, never generated
  language/glossary.py   Kenyan lexicon, 19 terms, 90 surface forms
  prompt_files/          persona.yaml + two contracts
docs/decisions.md        D-01 … D-06, each with what would reverse it
evaluation/              four experiments, criteria fixed beforehand
```

**Safeguarding text is never generated.** Not because a model would do worse,
but because nobody can review, approve or audit text rewritten on every turn.
Contacts are a **table read** — no corpus chunk contains a phone number -- checked
across all 1,693 -- so any number in a generated answer is invented by
definition, and the validator treats a phone-shaped string as fatal.

---

## What is still deliberately not built

No summarisation model over the conversation, no entity tracker, no per-girl
profile, no external monitoring vendor. The event log is a JSONL file.

The honest version of "what's next" is not a feature list. It is: **verify the
service directory**, because the safeguarding routes are where having nothing
verified costs the most, and because the event log now shows the service-access
turn is the one that returns nothing; and **get the corpus more youth-facing
material**, because 78%-clinical is the constraint underneath most of what is
still weak.
