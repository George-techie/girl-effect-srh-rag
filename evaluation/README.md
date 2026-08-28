# Retrieval evaluation

31 questions, scored against the corpus with no LLM in the loop.

```bash
python scripts/eval_retrieval.py --show-misses --save
```

## Why the questions are shaped this way

Girl Effect's Theory of Change (whitepaper §1.1) puts eight **behavioural
drivers** between a girl and a service, and **Knowledge is one of them**:

> self identity · social identity · outcome expectations · perceived social
> support · self-efficacy · attitude · perceived control · knowledge

The chain they describe runs *drivers → intent → service access → behaviour
change*, and their own example of success is a girl reaching the point where she
can say **"I understand the importance of speaking to a doctor about my sexual
health."**

A retrieval set made only of factual questions measures one driver of eight and
reports it as if it were the product. So every question here is tagged with the
driver it targets, and the results are broken down by driver.

Six further questions are **boundary cases** with no gold source: prescribing,
diagnosis, two topics deliberately cut from scope, and two safeguarding
disclosures. They exist to show what retrieval does when it should not answer.

## Results · top-5 · BAAI/bge-m3

| | |
|---|---|
| **Hit@5** | **0.926** — at least one gold source returned |
| Recall@5 | 0.599 — share of the gold set returned |
| **MRR** | **0.883** — the first gold source usually ranks first |

Gold labels are **source-level**: the question is whether the right document
came back, not whether the best paragraph in it ranked first. That makes Hit@5
an optimistic upper bound, and it is reported as one.

### By behavioural driver

| Driver | n | Hit@5 | MRR |
|---|---|---|---|
| perceived control | 3 | **0.667** | 0.667 |
| attitude | 4 | **0.750** | 0.750 |
| self identity | 2 | 1.000 | **0.417** |
| knowledge | 3 | 1.000 | 1.000 |
| self-efficacy | 3 | 1.000 | 1.000 |
| outcome expectations | 3 | 1.000 | 1.000 |
| social identity | 2 | 1.000 | 1.000 |
| perceived social support | 3 | 1.000 | 1.000 |
| service access | 2 | 1.000 | 1.000 |

**Knowledge scores 1.000 / 1.000. The three weakest are attitude, perceived
control and self identity** — the drivers about agency, judgement and whether
this is even for her. A retriever measured only on factual questions would look
flawless and would be failing exactly the questions the Theory of Change says
matter most.

### Who answers her

| | Top result | All 155 retrieved |
|---|---|---|
| clinical boundary (provider manuals) | **65%** | 72% |
| youth answer | 29% | 20% |
| evidence | 6% | 8% |

Two of eight documents are 486 and 216 pages of provider guidance; the youth
booklets are 17. So the material written *for her* is outnumbered roughly 20:1,
and two thirds of her questions are answered from a clinician's manual. The
facts are right. The reader they were written for is not her.

`document_role` is already in the metadata. Nothing filters on it yet — this is
the measurement that says it should.

## The Kiswahili gap

The one clean miss in the set was the Kiswahili phrasing of a question whose
English twin scored 1.000. Tested as five matched pairs:

| Question | English | Kiswahili | Δ | Same source? |
|---|---|---|---|---|
| contraception and infertility | 0.676 | **0.547** | **−0.129** | **no** |
| where to get family planning | 0.691 | 0.607 | −0.084 | **no** |
| too young to use family planning | 0.658 | 0.588 | −0.070 | yes |
| condoms and HIV | 0.738 | 0.697 | −0.041 | yes |
| scared to ask at the chemist | 0.608 | 0.623 | +0.015 | yes |

bge-m3 handles **direct translation** well — four of five still found a sensible
source. It breaks on **idiomatic Sheng**: *"inaharibu mji wa mtoto"* is a
metaphor, not a literal phrase, and that question retrieved a policy report
instead of the myth-correcting passages its English twin found immediately.

Mean cost of asking in Kiswahili rather than English: **−0.062 similarity**, and
a different source answering in two of five cases.

## What the boundary cases show

Every one returns a confident result. Retrieval has no way to decline.

| | Top hit | Similarity |
|---|---|---|
| "Which pill should I take?" | *Take a missed hormonal pill as soon as…* | 0.627 |
| "Rash and headaches since the implant. What is wrong?" | *New Problems That May Require Switching Methods* | 0.658 |
| "My periods have been irregular for three months" | *No monthly bleeding* | **0.668** |
| "I feel very low and cannot sleep" | *I am not a good mother, I feel like giving up* | 0.588 |

The third is worth pausing on: menstruation was **deliberately cut from scope**,
and it retrieves at 0.668 — higher than most questions that are in scope. No
similarity threshold separates them.

The fourth is worse. A girl saying she feels low and cannot sleep is offered a
passage about being a failing mother.

And in the middle of an ordinary identity question — *"Am I too young to be
thinking about protecting myself?"* — the **second** result is *"I was raped and
I am worried that no one will believe me."*

None of these is a retrieval bug. Retrieval did its job: it found the nearest
text. It is the argument for one component above the retriever whose only job is
deciding **whether to answer** — and for it to run *before* retrieval, since the
scores give it nothing to work with.

## What this evaluation does not establish

- **One author wrote the questions, the gold labels and the scoring.** That is
  weaker than independent labelling and the numbers should be read accordingly.
  Labels were assigned from each document's scope before any query was run, not
  adjusted to match what came back — but a second person choosing them would be
  worth more than that assurance.
- **`CTL_03` is scored as a miss and may not be one.** "My boyfriend says he
  does not like condoms — do I have any say?" returned *Bringing Up Condom Use*
  from the WHO handbook, which is topically right; the gold set asked for the
  youth sources. It is left scored as a miss rather than relabelled after the
  fact, and the disagreement is itself the finding: the passage is relevant and
  written for a clinician counselling a client.
- **Answer quality is not measured here.** This is retrieval only. Whether a
  reply built on these passages is accurate, safe and usable by a
  sixteen-year-old is a separate question needing a generator and human readers.
- **31 questions is small.** Differences of one question are noise.
