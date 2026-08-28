# Experiment 2 — oracle query restatement

**Status: criteria fixed before the run. Results appended below.**

## What is being tested

Experiment 1 showed the agency questions fail because the girl's phrasing does
not match the corpus's vocabulary, not because the wrong source answers them.
`"age of consent for family planning services in Kenya"` reaches the right Kenya
MoH passage at **0.711**; `"I'm 17. Can I get family planning without my parents
agreeing?"` reaches **0.565** and never surfaces it.

This experiment asks one question:

> If the same intent is expressed in the corpus's vocabulary, does retrieval
> improve enough to justify having a restatement mechanism at all?

**This is an oracle, not a design.** The restatements are hand-written with
knowledge of what the corpus contains. That is deliberate — an oracle measures
the *ceiling* of a mechanism, so that a mechanism which cannot pay off even with
perfect input is rejected before anything is built. If it does pay off, the next
question is a different one: how much of the gain an automatic restatement can
recover on questions nobody wrote a restatement for.

**Contamination, stated up front.** While diagnosing Experiment 1 I searched the
corpus with clinical phrasings and saw that *"informed consent for adolescents
and youth"* is the target passage for `CTL_01` and `CTL_02`. Those two
restatements are therefore written with the answer already known. That is the
strongest possible form of the oracle and the weakest possible evidence for
production. The other 29 were written from the question's intent and general
clinical vocabulary without running a query first.

## The architectural point being tested with it

The restatement is **for retrieval only**. Her own words go to the generator.

```
her message
   ├── original text ───────────────────→ generator
   └── retrieval restatement ───────────→ vector search → evidence
```

A system that answers a seventeen-year-old in Ministry-of-Health register
because that register retrieves better has solved the wrong problem.

## Success criteria — fixed before running

| # | Criterion | Threshold |
|---|---|---|
| 1 | Hit@5 does not meaningfully degrade | ≥ 0.90 (baseline 0.926) |
| 2 | Knowledge driver holds | MRR ≥ 0.90 (baseline 1.000) |
| 3 | **Agency drivers improve meaningfully** | mean of control / attitude / identity rises by **≥ 0.15**, and at least **2 of 3** improve individually |
| 4 | Overall MRR stable or better | ≥ 0.863 (baseline 0.883, allowing 0.02) |

Criterion 3 is the one the experiment exists for. 1, 2 and 4 are guardrails: a
restatement that fixes agency questions by wrecking factual ones has not earned
anything.

Baseline for comparison, unchanged from `evaluation/README.md`:

| | Hit@5 | Rec@5 | MRR | knowledge | control | attitude | identity |
|---|---|---|---|---|---|---|---|
| baseline | 0.926 | 0.599 | 0.883 | 1.000 | 0.667 | 0.750 | 0.417 |

Agency mean at baseline: **(0.667 + 0.750 + 0.417) / 3 = 0.611**.
Criterion 3 therefore requires **≥ 0.761**.

## Boundary cases

The six boundary questions are restated too, and they are watched for the
opposite reason. If restatement makes an out-of-scope or safeguarding question
retrieve *more* confidently, that is a finding against putting restatement in
front of the decision layer — the decision has to be made on what she actually
said.

---

## Results

**All four criteria pass. The mechanism is real — and the experiment found a
condition on it that matters more than the verdict.**

| | baseline | oracle | delta |
|---|---|---|---|
| Hit@5 | 0.926 | 0.926 | +0.000 |
| Recall@5 | 0.599 | 0.630 | +0.031 |
| MRR | 0.883 | 0.864 | −0.019 |
| knowledge MRR | 1.000 | 1.000 | +0.000 |
| **attitude MRR** | 0.750 | **1.000** | **+0.250** |
| **self identity MRR** | 0.417 | **1.000** | **+0.583** |
| perceived control MRR | 0.667 | 0.667 | +0.000 |
| youth-facing top result | 29% | **3%** | **−26pp** |

Agency mean **0.611 → 0.889 (+0.278)**; criterion 3 required ≥ 0.761.

The Kiswahili question is the clean confirmation. `ATT_04` went from **0.00 to
1.00**: *"Ni kweli ati family planning inaharibu mji wa mtoto?"* retrieved a
policy report, while *"contraception damage to the uterus or womb infertility
myth"* retrieved the myth-correcting passages immediately. The vocabulary-gap
hypothesis is confirmed.

### The biggest win is invisible to the metric

`CTL_01` — *"I'm 17. Can I get family planning without my parents agreeing?"* —
scored **1.00 before and 1.00 after**, so it appears in no delta anywhere. What
actually happened:

```
her words   0.565  WHO_HB  Serving Diverse Groups
            0.544  KE_FPG  Benefits of Informed Choice

restated    0.733  KE_FPG  Informed consent for adolescents and youth
            0.652  KE_FPG  PRIORITY AREAS
            0.644  KE_FPG  FP Services for Adolescents and Youth
```

The baseline retrieved a passage that does not answer the question, from a
source that happened to be in the gold set — so it scored a perfect hit.
**Source-level gold labels cannot tell the right document from the right
answer.** That is why perceived control shows +0.000 while being the driver the
mechanism most clearly fixes. It is a limitation of this evaluation, not a
result about restatement.

### Where restatement actively hurts

Three questions got worse, and they have something in common.

```
SUP_03  "I am pregnant and scared to tell anyone. What happens now?"
  her words   UNICEF_SAFE   0.670  I was raped and I am worried that no one…
              UNICEF_PARENT 0.618  I'm not ready to become a father…
  restated    KE_FPG        0.658  Informed consent for adolescents and youth
              WHO_HB        0.646  All Contraceptives Are Safe for Young People

BND_06  "My boyfriend forced me and I did not want to. I think I might be pregnant."
  her words   UNICEF_PARENT 0.654  I'm not ready to become a father…
              UNICEF_SAFE   0.570  I was raped and I am worried that no one…
  restated    WHO_HB        0.656  Violence Against Women
              UNFPA_SWP     0.617  The long-term value of ending gender-based violence
```

For a disclosure, restatement swapped youth support material written in her
register for policy literature *about* violence. `SOC_01` and `SUP_01` moved the
same way, and the youth-facing share of top results collapsed from 29% to 3% —
which is what restating into clinical vocabulary must do, by construction.

### And it makes out-of-scope questions more confident

| boundary case | baseline | oracle |
|---|---|---|
| "Which pill should I take?" | 0.627 | **0.676** |
| "My periods have been irregular for three months" | 0.668 | **0.691** |

Menstruation was deliberately cut from scope, and restatement pushes it further
above the in-scope questions. Restatement must therefore run **after** the
decision to answer, never before it — deciding on a rewritten query means
deciding on words she never said.

## Verdict

**Accepted as a mechanism, conditionally.** Restatement closes the vocabulary
gap it was proposed for: decisively on the Kiswahili myth and both identity
questions, and on `CTL_01` in a way this evaluation cannot score.

It is **not** something to apply to every turn:

| turn | query to use | why |
|---|---|---|
| factual · access · myth | **restatement** | the corpus's vocabulary is the authoritative one |
| support · disclosure | **her own words** | the youth sources are already in her register; restatement pulls toward policy literature |
| out of scope | **decide first** | restatement raises confidence on questions that should not be answered |

So the thing that decides *whether to restate* is the same thing that decides
*whether to answer at all*, and it needs her original message for both. That is
an argument for the decision layer arriving with evidence behind it rather than
because routers are conventional.

## What this does not establish

- **The restatements are hand-written by the same person who wrote the questions
  and the gold labels.** This is the ceiling of the mechanism, not a measurement
  of any implementation. Whether automatic restatement recovers most of this
  gain on questions nobody prepared for is a separate experiment, and the honest
  expectation is that it recovers less.
- `CTL_01` and `CTL_02` were written already knowing the target passage.
- 31 questions. `identity` is two of them, so its +0.583 is two questions moving.
- Recall@5 rose (+0.031) while MRR fell (−0.019): restatement pulls in more of
  the gold set but ranks the first hit slightly lower on average.
