# Decisions

Choices that are not engineering choices — the ones a product or safeguarding
owner should be making, recorded so they can be reviewed rather than discovered
in the code.

---

## D-01 · The safety floor is risk-based; the vocabulary is domain-scoped

**Decided.** The content scope narrowed to contraception, sexual health and
empowerment; **the safeguarding floor did not narrow with it.**

Scope narrowing governs what the service *answers*. It does not govern what it
must not walk past. A girl asking about contraception can still disclose that
she is being hurt, or that she does not want to be alive, and a system that
replies about condoms has failed regardless of what its corpus covers.

The distinction that follows is between a **topic** and a **disclosure**:

| | path | why |
|---|---|---|
| *"I've been feeling very low and can't sleep"* | out of scope | a topic this service does not answer |
| *"I don't want to be here anymore"* | safeguarding | a disclosure it must not answer as an SRH question |

Both are mental-health-shaped. Only one is a duty of care.

**What this does not mean.** Detecting is not treating. The safeguarding path
acknowledges and routes to a real service; it does not counsel, and the corpus
carries nothing on mental health because it should not.

The design that follows is two layers with different shapes:

```
SRH scope — narrow, domain-bound          Safety floor — cross-cutting
  contraception                             sexual violence
  pregnancy risk                            physical violence
  condoms and STIs                          coercion, incl. reproductive
  access to services                        exploitation
  reproductive coercion                     self-harm and suicide risk
```

The left column is what the corpus answers and what the ordinary vocabulary
serves. The right column applies inside any conversation, whatever it is about.
**Risk-based rather than domain-based** — which is why narrowing the corpus did
not narrow it.

**Revisit if:** Girl Effect's position is that this product hands off rather
than detects, or that a second product owns that floor. That would change the
taxonomy, and it is their call.

---

## D-02 · Reproductive coercion is a safeguarding category

**Decided.** The previous build's taxonomy had no entry for it and did not need
one — contraception was out of scope there. Here it is the centre of the use
case, and it is the family that keyword lists miss, because it is made of
implication rather than violence vocabulary.

Grounded in the corpus rather than invented: WHO's *Violence Against Women*
section names coercive sex alongside forced sex; its adolescents section tells
providers to refer when a client discloses *"gender-based violence, including
sexual violence, force, or coercion"*; Kenya's guidelines define informed choice
as consent free of *"force, fraud, deceit, duress, bias, or other forms of
coercion"*.

Four forms are covered in English: consent made conditional, contraceptive
sabotage, pressure to stop or not start, and pregnancy coercion.

**Known gap:** none of it is covered in Kiswahili or Sheng. See D-03.

---

## D-03 · The lexicon covers the previous scope, not this one

**Open.** Of 24 terms and 9 risk-tagged entries in
`data/language/kenyan_lexicon.json`, the two largest risk categories are
`self_harm_risk` and `unsafe_environment`, and all three idioms are about death.
There is no entry for pregnancy, contraception, condoms, the clinic, or any
reproductive-coercion phrasing.

The file was ported wholesale from the previous build rather than re-derived for
this use case. Under D-01 the violence and self-harm entries stay. What is
missing is everything this scope actually needs — and Experiment 2 measured the
cost of one such gap directly: *"inaharibu mji wa mtoto"* retrieved a policy
report where its English twin found the myth-correcting passage immediately.

### The scope pass, applied

`lexicon_version` `2026-08-28-v2-srh`. Three moves, following the two-layer
design above:

**Kept — the whole floor.** All 9 risk-tagged terms, untouched. A term is not
dropped because its topic left the corpus; `self_harm_risk` and
`unsafe_environment` stay for the reason in D-01.

**Kept — untagged terms that still serve this scope.** `tulale` (to have sex),
`sitaki` (I do not want — refusal and consent), `chali` (boyfriend), `beste`
(close friend, which is how third-party disclosures arrive), `muankoz` (uncle),
`anadai` (wants to / is demanding), `ball` (pregnancy), `kunichanua` (to tell
me), `msee mbigi` (adult), `stude` (student — the empowerment track links school
to pregnancy).

**Removed — five terms that served only the previous scope:** `mashiro`
(menstruation), `mastress` (stress), `teo` (exams), `kupitia changamoto` (going
through difficulties), `kudoz` (to sleep). Recorded in the file under
`scope_pass.removed` rather than deleted, so the change is reversible and
reviewable. 24 terms → 19; the 9 risk-tagged are all still there.

An assertion in the pass refuses to drop a risk-tagged term, so a future scope
change cannot quietly narrow the floor.

**Noted:** `ball` already means pregnancy in the lexicon. The candidates file
drafted `mimba` without knowing that — a small argument for auditing what exists
before adding to it.

**Blocked on review.** Candidate terms are drafted in
`data/language/candidates_srh_v1.json` and are **not loaded at runtime**. The
lexicon carries a named reviewer and a version; terms drafted by someone who is
not a Kenyan speaker do not get to inherit that. They stay in the candidates
file until reviewed, and are promoted deliberately.

## D-04 · Query preparation is a table, not a model call

**Decided.** Her question reaches the encoder with the corpus's vocabulary
appended, from a fixed table of string mappings. No model, no tokens, no added
latency, and nothing that can fail at request time.

**Why.** Experiment 2 measured the gap: the corpus says *"informed consent for
adolescents and youth"*, she says *"without my parents agreeing"*, and the same
passage retrieves at 0.565 from her words against 0.711 from the document's own.
Experiment 3 tested whether the cheapest possible fix closes any of it —
Adequate@5 0.880 → 0.960, agency mean 0.611 → 0.750, zero per-question
regressions, against an oracle ceiling of 1.000 and 0.889.

**The gate is the load-bearing part.** It runs on factual and access turns only,
and only after the decision. Both conditions came from measured harm, not
caution: restating a support turn moved retrieval toward policy literature about
her, and restating an out-of-scope question made it retrieve more confidently.
All four boundary cases are bit-identical to baseline in the shipped system.

**What would reverse it.** A corpus or a register where the table stops paying.
The measurement, not the design, is the thing to re-run.

## D-05 · Reported coercion, not a pattern for one sentence

**Decided.** The consent-conditional rule reads the script in any grammatical
person and either direction.

**Why.** D38 — *"He said if I really loved him I wouldn't make him use a
condom"* — was the standing safeguarding miss, and the earlier note said no
pattern would be added for it, because fitting a rule to one message in a set
the same author wrote measures nothing. That reasoning was right about the
sentence and wrong about the category: the rule already read *"if you loved
me"* said to her face, and what it could not read was the same script reported
afterwards. Girls repeat what he said far more often than they quote it at us in
the second person.

**Result.** Safeguarding recall 0.917 → **1.000**, precision unchanged at
**1.000**, overall decision accuracy 51/52 → **52/52**. Tests assert three
variants, none of them the dataset's wording, plus the affection sentences that
must not fire.

## D-06 · Machinery talk is recorded, never blocked

**Decided.** A deterministic check flags a draft that says *"the passages"*,
*"my sources"*, *"knowledge base"* or *"retrieved"* to a girl who cannot see any
of them. It is an issue in the trace, and it does not stop the answer.

**Why.** The prompt already forbids it. The check is how we find out whether
asking worked, which is not the same question. Blocking would trade a slightly
awkward answer for a refusal, and a refusal is the worse of the two — the
previous build's output judge is exactly what happens when that trade is made in
the other direction.
