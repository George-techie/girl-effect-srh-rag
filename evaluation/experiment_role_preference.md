# Experiment 1 — soft preference for youth-facing sources

**Result: not adopted.** `ROLE_BONUS` stays at `0.0`. The experiment did not
earn the change, and in failing it diagnosed the real problem.

```bash
python scripts/eval_retrieval.py --sweep
```

## The hypothesis

65% of top results came from clinician-facing material. The hypothesis was that
retrieval treats a 486-page provider handbook, a policy report and a 17-page
youth booklet as interchangeable whenever similarity is close — and that a
**soft** preference (a score bonus, never a filter) would put more of her
questions in front of material written for her, without costing factual quality.

Success was defined before the run, following the four conditions set out when
the experiment was commissioned:

1. Hit@5 roughly unchanged
2. Knowledge driver roughly unchanged
3. youth-facing top results up substantially
4. **agency-driver retrieval up**

## What happened

| bonus | Hit@5 | Rec@5 | MRR | knowledge | control | attitude | identity | youth top | clinical top |
|---|---|---|---|---|---|---|---|---|---|
| **0.000** | **0.926** | **0.599** | **0.883** | 1.000 | 0.667 | 0.750 | 0.417 | 29% | 65% |
| 0.020 | 0.926 | 0.586 | 0.864 | 1.000 | 0.667 | 0.750 | 0.417 | 39% | 58% |
| 0.040 | 0.926 | 0.586 | 0.791 | 0.833 | 0.333 | 0.750 | 0.267 | 52% | 45% |
| 0.060 | 0.889 | 0.574 | 0.688 | 0.778 | 0.250 | 0.583 | 0.125 | 61% | 35% |
| 0.080 | 0.815 | 0.519 | 0.648 | 0.778 | 0.167 | 0.583 | 0.125 | 65% | 29% |
| 0.120 | 0.815 | 0.506 | 0.599 | 0.611 | 0.167 | 0.417 | 0.125 | 74% | 16% |
| 0.200 | 0.778 | 0.481 | 0.581 | 0.611 | 0.167 | 0.383 | 0.125 | 74% | 16% |

**Three of four conditions were met at 0.02. The fourth was not.** Youth-facing
top results rose 29% → 39% with Hit@5 unchanged and every driver score
unchanged — but *unchanged* is the point. The agency drivers did not improve.
Perceived control stayed at 0.667, attitude at 0.750, self identity at 0.417.

Above 0.02 the preference does active harm: at 0.04 the knowledge driver drops
from 1.000 to 0.833 and perceived control halves to 0.333. The source mix keeps
improving while the retrieval gets worse — which is what makes the youth-share
column a bad thing to optimise on its own.

**Verdict.** A +10 point shift in source mix is three questions out of 31, for a
small but real cost in MRR (0.883 → 0.864) and recall (0.599 → 0.586), and it
does nothing for the weakness that motivated it. On a 31-question set written by
one author that is inside the noise. Not adopted.

## Why it could not have worked

The diagnosis was wrong, and the experiment is what showed it.

Look at where the agency questions actually land:

```
CTL_01  "I'm 17. Can I get family planning without my parents agreeing?"
   0.565  WHO · Contraception Clinical Guide   Serving Diverse Groups
   0.544  Kenya MoH · FP Guidelines            Benefits of Informed Choice
   0.536  WHO · Contraception Clinical Guide   Planning for FP After Delivery

CTL_02  "Can a nurse refuse me contraception because I am not married?"
   0.575  WHO · Contraception Clinical Guide   10. Rule out pregnancy.
   0.566  WHO · Contraception Clinical Guide   Medical Eligibility Criteria
   0.566  WHO · Contraception Clinical Guide   Do you have or have you ever had…
```

Nothing there answers the question. No amount of preferring youth sources helps,
because the youth booklets do not cover Kenyan access rules either.

But the content **is in the corpus**. Asked in the document's own vocabulary:

```
"age of consent for family planning services in Kenya"
   0.711  Kenya MoH · FP Guidelines   Informed consent for adolescents and youth
   0.684  Kenya MoH · FP Guidelines   FP Services for Adolescents and Youth

"marital status must not be a barrier to family planning services"
   0.649  Kenya MoH · FP Guidelines   GUIDING PRINCIPLES FOR THE FAMILY PLANNING…
   0.606  WHO · Contraception Clinical Guide   Human Rights: Family Planning Providers'…
```

**0.711 against 0.565 for the same underlying question.** The passage exists,
is authoritative, is Kenyan, and is unreachable from the words she would use.
The document says *"informed consent for adolescents and youth"*; she says
*"without my parents agreeing"*.

So the agency weakness is a **vocabulary gap**, not a source-role gap and not a
corpus gap. Three different problems that all look identical in a Hit@5 number.

## What this points at instead

**Query restatement**, not source weighting. Restating her question in the
corpus's own register before searching is the cheap fix — and it is the same
mechanism the previous build used, where the turn planner emitted a
`search_query` alongside its routing decision. That rationale now has
independent evidence on a new corpus.

It is also the same shape as the Kiswahili finding: *"inaharibu mji wa mtoto"*
fails for the same reason *"without my parents agreeing"* fails. Her words and
the corpus's words are different vocabularies, and the gap is wider the further
she gets from clinical English.

That does not justify a component on its own. It justifies **testing
restatement next**, and it means the decision layer — which has to read the
message anyway — can produce the restatement in the same pass rather than
needing a call of its own.

## Caveats

- 31 questions, one author for the questions, the gold labels and the scoring.
  Read the driver breakdowns as *"revealed a systematic weakness on
  agency-oriented questions that was invisible on factual ones"*, not as a
  population estimate.
- The sweep re-ranks a 25-candidate pool. A wider pool would let a large bonus
  reach further down, and would make the high-bonus rows worse, not better.
- `evidence` sources receive half the bonus, on the reasoning that UNFPA and WHO
  briefs are written for programme staff rather than for her. That ordering was
  not itself tested.
