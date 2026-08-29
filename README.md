# Trusted Aunti — sexual and reproductive health, for adolescent girls in Kenya

A safety-aware assistant answering questions about **contraception, sexual
health, staying safe, and how to reach a service** — grounded in eight governed
documents, with a deterministic safety floor above it.

This is a **refined** build. The feedback on the previous one was that it was
overengineered in places, and this repository is the answer to that: the same
solution philosophy, with every component either justified by a measurement or
deleted.

```
decide  →  prepare  →  retrieve  →  generate  →  check
```

**Four deterministic steps and one model call.** The model is reached only on
turns the decision layer sends to it, and never on a disclosure of harm.

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
python -m pytest -q                                 # 84 tests
python scripts/eval_decision.py                     # 52/52
python scripts/eval_retrieval.py                    # Hit@5, MRR, by driver
python scripts/eval_retrieval.py --compare-prepared # Experiment 3
```

Embeddings are **local** (`BAAI/bge-m3`) — no per-query embedding cost, and no
girl's question leaves the machine to be embedded. Generation runs through
OpenRouter on `anthropic/claude-sonnet-5`; set `OPENROUTER_API_KEY` in `.env`.

---

## Layout

```
src/
  pipeline.py            the whole system, ~280 lines
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

## What was deliberately not built

**Conversation memory** — nothing measured that this demo needs it.
**A journey-event schema** and **an observability layer** — both defensible for a
production service and neither justified by anything measured here. Adding them
now would repeat the exact mistake this build exists to correct.

The honest version of "what's next" is not a feature list. It is: **verify the
service directory**, because the safeguarding routes are where having nothing
verified costs the most; and **get the corpus more youth-facing material**,
because 78%-clinical is the constraint underneath most of what is still weak.
