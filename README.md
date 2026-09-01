# Trusted Aunti

A safety-aware assistant for adolescent girls in Kenya. It answers questions
about **contraception, sexual health and staying safe**, recognises when a girl
is disclosing harm, and gets her to a real service.

```bash
pip install -r requirements.txt
python scripts/ingest.py       # build the index, once
streamlit run app.py           # the demo
```

---

## What it does

Ask it anything, in English, Kiswahili or Sheng. It replies in the register she
wrote in.

| She writes | What happens |
|---|---|
| *"Does the implant stop you having children later?"* | answered from the corpus, every claim cited |
| *"and does it hurt?"* | resolved against the turn before it |
| *"where can I actually go to get it?"* | **Marie Stopes 0800 720 005 · One2One 1190** |
| *"my boyfriend is pressuring me"* | recognised as coercion, support first, contacts offered |
| *"I don't want to be here anymore"* | crisis lines, immediately, **in 0 ms** |
| *"I want to be a doctor one day"* | answered as a conversation, because it is one |

**One model call per turn**, and only on turns that need one. Routing,
safeguarding, retrieval and validation are deterministic rules, and embeddings
run locally. Every safeguarding reply is assembled without a model at all, which
is why it arrives instantly.

---

## How it works

```
validate → SAFEGUARDING SCREEN → route → retrieve → generate → check
```

**The safeguarding screen runs first, on every message.** When it fires nothing
downstream executes — no retrieval, no model call. That ordering matters because
retrieval cannot decline: an out-of-scope question was measured retrieving at
0.668, above most in-scope ones. So the decision is made on her words, before
anything is searched.

**Two output contracts.** A grounded answer is safe because every claim carries
a citation. A conversational reply is safe because it makes no claim at all.
Which one applies is decided by the path, never inferred from whether citations
happen to be present.

**Contacts are a table read, never generated.** No corpus chunk contains a phone
number, so a number in generated text would be invented — and the validator
treats one as fatal.

Diagrams and the reasoning behind each choice:
**[`docs/architecture.md`](docs/architecture.md)** ·
**[`docs/decisions.md`](docs/decisions.md)**

---

## What it scores

| | Metric | Previous build | This build |
|---|---|:--:|:--:|
| **Safeguarded** | safeguarding recall | 1.000 | **1.000** · 12/12 |
| | safeguarding precision | 0.800 | **1.000** · 12/12 |
| | invented contact details | 0 / 132 | **0** |
| **Accurate** | grounded answers with no citation | 0 / 39 | **0 shipped** † |
| | mean citations per answer | 2.46 | **2.61** |
| | routing accuracy | 0.766 F1 | **52/52** |
| | retrieval Adequate@5 | — | **0.960** |
| **Reliable** | **unusable outcomes** | 12/51 · 23.5% | **3/52 · 5.8%** ‡ |
| | latency p50 / p95 | 14.2 s / 22.8 s | **5.2 s / 14.8 s** |
| | errors | 0 | **0** |
| | forbidden retrievals | — | **0/23** |
| **Resonant** | tone and inclusion | 4.61 / 5 | *reviewer scored* |
| | Kenyan register | 4.00 / 5 | *reviewer scored* |
| | conversation | 4.06 / 5 | *reviewer scored* |
| | register match, measured | — | **38/38** |
| | natural continuation | — | **32/37 · 86%** |
| | deferrals avoided | — | **38/38** |
| **Cost** | LLM calls per turn | 3.53 | **0.69** |
| | tokens per turn | 6,838 | **4,946** |
| | cost per turn | $0.0189 | **$0.0109** |

† One draft was blocked by the validator for having no citation, so nothing
uncited reached a girl. ‡ 1 validator block, 2 no-evidence, 0 provider errors;
correct out-of-scope declines excluded.

**The resonance rows are the honest gap.** The previous build ran a designed
human review — 132 responses, two models side by side and unlabelled, four
reviewers, one sheet per dimension. Those scores are people's judgement and this
build has no equivalent; its resonance rows are deterministic proxies, which
measure whether a property holds, not whether a reply is good. Reproducing that
review is the single most valuable next step.

**Safety is not usefulness.** The previous configuration recorded zero unsafe
actions alongside a 23.5% unusable rate. Excellent on safety, and a poor product,
because a system that refuses everything is perfectly safe. That build's own
review put it plainly: *"Service hallucination protection works. Service
fulfilment does not."* — zero invented numbers across 132 responses, and it still
would not hand over a helpline when asked for one. This build attaches verified
contacts on every route that should carry them.

Objective figures come from that project's recorded runs — `objective_v1.json`
for the 66-response evaluation and the four-system comparison for routing and
cost. Where an instrument differs, the row is directional rather than exact.

```bash
python -m pytest -q                                  # 176 tests
python scripts/eval_decision.py                      # routing and safeguarding
python scripts/eval_retrieval.py --compare-prepared  # retrieval
python scripts/eval_multiturn.py                     # conversations
python scripts/eval_mixed.py                         # mixed-intention messages
python scripts/eval_conversation.py --include-mixed  # conversation quality
python scripts/eval_toc.py                           # Theory-of-Change journeys
python scripts/eval_cost.py                          # tokens and cost
```

**Full write-up:**
**[`docs/Trusted_Aunti_Build_Report.pdf`](docs/Trusted_Aunti_Build_Report.pdf)**

---

## Two journeys, end to end

Girl Effect's Theory of Change runs **behavioural drivers → intent → service
access → behaviour change**. Knowledge is one driver of eight, so a system can
answer every question correctly and never move a girl toward a service. Two
conversations are scored against it on every run.

```bash
python scripts/eval_toc.py --show
```

**A girl worried after unprotected sex, reaching HIV testing:**

| She writes | Driver | Stage reached | |
|---|---|---|:--:|
| *"niaje aunti"* | rapport | rapport | |
| *"my friend says you can tell if someone has HIV by looking at them"* | knowledge | knowledge | 2 cited |
| *"we didnt use protection last month and i keep thinking about it"* | perceived risk | knowledge | |
| *"i should get tested but i am scared what they will say about me"* | self-efficacy | confidence | |
| *"tell me what actually happens when you go for an HIV test"* | **intent** | knowledge | 3 cited **+ contacts** |
| *"where can i actually go for one?"* | **service access** | service access | **+ contacts** |
| *"asante sana aunti, i will text them tomorrow"* | behaviour change | rapport | |

> *"That fear is real, and it's probably the biggest thing standing between you
> and getting tested, not the testing itself. A lot of girls worry more about
> being judged than about the result. What are you imagining they'll say?"*

**A girl held back by a myth and by family norms, reaching family planning** —
answered in the register she wrote in:

> **She:** *"watu wanasema family planning inaharibu mji wa mtoto. is that true?"*
>
> **Aunti:** *"Hiyo si kweli, na ni one of those misconceptions zinazoenea sana.
> Family planning haiharibu mji wa mtoto (uterus) au uwezo wa kupata mtoto
> baadaye. Njia nyingi za contraception ni reversible, meaning fertility inarudi
> haraka baada ya kuacha kutumia."*

Across both journeys, 14 turns: **stage reached as intended 14/14 · citation
where required 14/14 · refusals 0/14**, and each ends with a number she can text.

**An access question never ends in a refusal.** The answer to *"where can I go"*
lives in the verified table rather than in generated text, so the table can
answer it alone whatever happens to the draft.

---

## The three decisions that shaped it

**Deterministic first, models where they earn it.** The previous build's own
ablation isolated the cost of each component: an output validator cost +1
unhelpful refusal, an LLM evidence judge cost +6 more to prevent one unsafe case.
So this keeps deterministic validation and has no judge. Every removal has a
number behind it — and two components were *added* on the same basis.

**Detect broadly, escalate narrowly.** One safeguarding route, two severities.
Force, threat, assault and self-harm put verified contacts in front of her.
Pressure and conditional consent are recognised as safeguarding and answered as a
conversation, with contacts offered rather than pushed — because treating every
coercion signal as an emergency reads as being passed on, and at scale buries the
services in cases that were never emergencies.

**Service access is the point.** Girl Effect's Theory of Change runs behavioural
drivers → intent → **service access** → behaviour change. Knowledge is one driver
of eight, so a system that answers well and never gets her to a service has done
the easy half. Eight verified services cover eight routes, each with a source, a
checker and a date.

---

## Scope and limitations

**The evaluation sets are authored in-house** — 121 labelled messages and questions across four
sets, written alongside the system. A rigorous regression harness; testing with real
users is the next step.

**The corpus leans clinical** — 1,326 provider-guidance chunks against 58 written
for a young reader, which is what clause-level retrieval and the vocabulary
mappings bridge.

**Kiswahili carries a measured retrieval cost** of 0.062 similarity over five
matched pairs.

**Continuity is at 86%**, the newest metric and the one with most headroom.

---

## Layout

```
src/
  pipeline.py            one turn, start to finish
  decision/rules.py      six paths, ordered, safeguarding first
  conversation.py        six turns, one topic, one flag
  rag/                   chunking, retrieval, query preparation
  safety/                deterministic checks, approved text
  services.py            the verified service table
  observability.py       one event per turn, invariants at runtime
docs/                    architecture, decisions, build report
evaluation/              five sets, criteria fixed before each run
```

**Privacy.** The event log holds operational fields only — no message text, no
identifier for her. Embeddings run locally, so no question leaves the machine to
be encoded.
