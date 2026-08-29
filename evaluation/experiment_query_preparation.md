# Experiment 3 — deterministic query preparation

**Question.** Experiment 2 measured a vocabulary gap and an oracle ceiling. Can
a table of string mappings — no model, no tokens, no latency — recover a useful
share of that ceiling without dragging anything backwards?

**Run.** `python scripts/eval_retrieval.py --compare-prepared`
31 questions, top-5, BAAI/bge-m3, no role bonus.

## The design, and the two constraints it inherited

Her words stay in the query and the corpus's vocabulary is **appended**. A
replacement discards the signal that was already working; an expansion can only
add, which is what makes a wrong mapping cheap — it contributes an unused phrase
rather than a wrong query.

Both gating constraints came from Experiment 2 rather than from taste:

- **Factual and access turns only.** Restating a support turn pulled retrieval
  from material written for her toward policy literature *about* her.
- **After the decision, never before.** A deliberately out-of-scope question
  retrieved *more* confidently once restated (0.668 → 0.691). Deciding on a
  rewritten query means deciding on words she never said.

11 of 31 questions had any mapping applied. The other 20 are untouched by
construction, not by luck.

## Result

|                  | natural | prepared | oracle |  delta |
|------------------|--------:|---------:|-------:|-------:|
| **Adequate@5**   |   0.880 |    0.960 |  1.000 | +0.080 |
| Hit@5            |   0.926 |    0.963 |  0.926 | +0.037 |
| Recall@5         |   0.599 |    0.586 |  0.630 | −0.012 |
| MRR              |   0.883 |    0.920 |  0.864 | +0.037 |
| knowledge MRR    |   1.000 |    1.000 |  1.000 |  0.000 |
| control MRR      |   0.667 |    0.667 |  0.667 |  0.000 |
| attitude MRR     |   0.750 |    0.833 |  1.000 | +0.083 |
| identity MRR     |   0.417 |    0.750 |  1.000 | +0.333 |
| youth-facing top |   0.290 |    0.258 |  0.032 | −0.032 |

**Agency mean 0.611 → 0.750**, against an oracle of 0.889. The cheap version
recovers about half the distance to a ceiling written by hand with the answers
already known.

### Adoption criteria, fixed before the run

| | Criterion | Result | |
|---|---|---|---|
| A | no drop in Adequate@5 | 0.880 → 0.960 | **pass** |
| B | no drop in Hit@5 | 0.926 → 0.963 | **pass** |
| C | at most 1 per-question regression | 0 regressed | **pass** |
| D | some measured gain somewhere | MRR 0.883 → 0.920 | **pass** |

Two questions moved, both up: ATT_04 (0.00 → 0.33, the *mji wa mtoto* infertility
myth) and IDN_02 (0.33 → 1.00). Two gained evidence adequacy, ATT_04 and OUT_01.
Nothing moved down.

**All four boundary cases are bit-identical to baseline** — 0.627, 0.658, 0.668,
0.588 — because they route to `out_of_scope` or `support` and the gate never
opens. That is the constraint from Experiment 2 doing its job in the shipped
system rather than in a note.

## What is not being claimed

**Recall@5 fell 0.012.** One question's worth of one gold source, inside the
noise of a 31-question set. It is reported because it moved, not because it
means anything; the metric that matters here is whether a passage that *answers*
her came back, and that rose 8 points.

**The mappings are labelled `evidenced` or `extrapolated` in the source.** Three
come from measured failures with scores recorded in Experiments 1 and 2. Seven
are the same *kind* of gap written from the corpus's own section titles — not
from running queries and keeping whatever scored well. Tuning a table against
the set you then report on measures the tuning, not the layer. The distinction
is kept in the code so a reviewer can discount the second group.

**The oracle is still ahead on adequacy and agency, and that gap is real.** It
is also unavailable: it was written by a person who already knew which passage
was the right one.

## Why not a model call

A rewriting model would have to beat 0.880 → 0.960 with zero regressions, and
then keep beating it on turns nobody tested, while adding a call to every
factual question and a second thing that can fail. Nothing measured suggests it
would. If the mapping table stops paying — a new corpus, a different register —
that is the moment to try one, with this as the baseline to beat.
