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

## D-07 · The phone check now fires on contacts, not on page numbers

**Decided.** The short-code half of the phone regex is the actual four-digit
Kenyan codes, plus `116` only where something nearby presents it as a number to
call.

**Why.** The old pattern `1(?:99|95|16)` matched **9 corpus chunks**, all of them
page references — *"see LNG-IUD for Women With HIV, p. 199"*, *"p. 116"*, a
journal page range. The phone check is fatal. A generated answer mentioning
p. 116 would have been blocked, and a girl would have received a refusal in place
of a correct, cited answer.

Both failure directions are now regression-tested, including an assertion that
**no corpus chunk matches at all** — the README's claim checked by the test suite
rather than believed.

**How it was found.** Not by a test, a judge or a review. By checking whether a
number written in the README was true. It was not, and the check that produced
the number was itself the defect.

## D-08 · Conversation state, not conversation memory

**Decided.** Six turns, one resolved topic, one disclosure flag, all derived by
rules. A dependent fragment gets its antecedent prepended for retrieval only.

**Why.** Replaying the journey a reviewer described — contraception, her
ambitions, coercion, seeking a service — broke four turns, two of them in
safety-relevant ways. *"And does it hurt?"* asked after a question about the
implant retrieved **female sterilization**; *"where can I go?"* asked after a
coercion disclosure retrieved **BTL**, which is permanent. A girl was going to be
answered about being sterilised because her follow-up had no subject in it.

**Three boundaries, each pinned by a test.** The decision still reads her words
alone — `rules.decide` takes a string and nothing else, so a disclosure cannot be
missed because of what came before it. Resolution touches the retrieval query
only. It is bounded and it forgets.

**What would reverse it.** Evidence that six turns is the wrong window, or that
prepending loses to substitution. Both are measurable with
`scripts/eval_multiturn.py`.

## D-09 · Topic outlives the transcript

**Decided.** The antecedent is a field on the conversation, updated as turns are
recorded, not something searched out of the turn window.

**Why.** It was derived from the window, and the window is trimmed. In the
reviewer's own journey she asked about the implant, talked about school,
disclosed coercion twice, and then asked *"where can I go?"* — by which point the
implant question had been trimmed away and the fragment resolved against nothing.
The subject of a conversation is not the same object as its transcript, and
sizing them together was the bug.

## D-10 · A message that names its own subject is never resolved

**Decided.** The content check runs before the backreference check in
`is_dependent`.

**Why.** *"What about the injection"* opens with a backreference *and* names a
method. Resolving it against a question about the implant put both methods in
one query and the implant won — she asked about one method and would have been
answered about another. Ordering the checks the other way was a one-line change
and it also fixed *"and the condom?"*, which had been dragged from MALE CONDOM
back to the pill's MODE OF ACTION.

## D-11 · Observability, and why it is not optional

**Decided.** One event per turn, invariants checked at runtime, a reader that
puts anomalies first. Violations are recorded, never raised.

**Why.** Three defects were found in this codebase in one afternoon and every
one was found by a person reading output by hand: the phone check firing on page
numbers, the topic trimmed before use, and `Decision.retrieves` disagreeing with
the pipeline. That is the normal failure mode of layered deterministic code — a
component stops doing what its name says, every answer still looks plausible, and
nothing counts. It does not scale past a demo, and what does not scale is what a
girl relies on.

Each invariant encodes a failure that has already happened here, including the
previous build's `urgent` flag — written to the trace, read by nothing, so a girl
at risk of self-harm saw less than one who disclosed something less dangerous.

**It paid for itself immediately.** A 39,479 ms first turn against a 5,406 ms
median (the encoder loading lazily inside her first question — now warmed at
startup), and the `access` turn returning no evidence, which is the Theory of
Change's terminal stage failing for a reason the corpus cannot fix.

**What would reverse it.** Nothing measured. This is the one component here
argued from a failure mode rather than a benchmark, and the argument is that you
cannot benchmark what you cannot see.

## D-12 · The event log is not a database of disclosures

**Decided.** Operational fields only by default — paths, timings, similarity,
flags, issue names. Her words are written only under an explicit
`TRACE_MESSAGES=1`, for a developer replaying a bug locally.

**Why.** An event log for a safeguarding product, kept by default, is a
surveillance database with a dashboard on top, and the girls most at risk from it
are the ones the product exists for. There is no identifier for her and no
session id that survives a restart. The default stream still answers every
operational question that matters — it can tell you fragments are failing to
resolve; it cannot tell you who said what.

## D-13 · "Where can I go?" after a disclosure is a request for help

**Decided.** An access turn with no subject of its own, in a conversation where
she has already disclosed, is answered from approved text — the help pathway,
no model call, no corpus.

**Why.** It was the worst-placed failure in the build and only a full rehearsal
found it. She disclosed coercion, asked *"where can I go?"*, and the fragment
resolved against her earlier question about the implant, searched implant
passages, found nothing about *where*, and returned the no-evidence refusal — at
the exact turn she asked for help. The following turn then apologised for it.

Two things were wrong at once: a stale topic survived across a disclosure, and
the `disclosed` flag existed while nothing consumed it. That second one is the
same defect as the previous build's `urgent` — a signal written and read by
nobody — which is why it is now one of the runtime invariants.

**The line.** A fragment is a request for help. A message naming its own subject
("where can I get the pill?") is still a real access question and is answered
from the corpus as before. She may well still want the pill.

## D-14 · Detect safeguarding broadly, escalate narrowly

**Decided.** One safeguarding route, two severities, no second classifier.

**urgent** — force, threat, assault, contraceptive sabotage, self-harm risk.
She gets safety guidance and verified contacts *in front of her*.

**concern** — pressure, conditional consent, "he keeps asking", "he gets upset
when I say no", "if you loved me you would". She gets acknowledgement, a plain
statement of what consent is, the decision left with her, and contacts
**offered** behind a tap.

**Why the concern tier exists.** *"My boyfriend is pressuring me to have sex"*
was being answered with the handoff text — *"I can't be the person who helps
you with this, someone real can"* — and that gets two things wrong at once. It
reads as being passed on when she came to talk. And it treats a conversation
she wanted to have as a referral event, which at any real scale buries the
services in cases that were never emergencies. The alternative failure is worse
and was also live: routing it to `factual` and answering coercion as though it
were a contraception decision.

**What it is not.** It is not automated reporting. Nothing contacts anyone on
her behalf. The numbers are options she may use, which is what keeps the
service hers rather than something pointed at her.

**Implementation cost: one boolean.** `Decision.urgent`, set by which family
fired. No taxonomy, no extra model call, no per-case scoring.

## D-15 · Self-harm was detected by a signal nothing ever set

**Decided.** `Decision.tags` carries stable risk names; `matched` carries regex
sources for the trace. They are separate fields.

**Why.** The pipeline asked `"self_harm_risk" in decision.matched`, and
`matched` held regex *source strings*. That tag only ever appeared there via
the glossary, so **every self-harm disclosure phrased in English got the
ordinary safeguarding reply instead of the urgent one with crisis numbers.**
*"I dont want to be here anymore"* received a message about being a digital
guide, and pulled sexual-violence services because a substring check for
`"harm"` matched `"safeguarding · harm"`.

Nothing errored. No test failed. The check read correctly at a glance. It is
the same defect as the previous build's `urgent` flag — a signal written and
read by nobody — running in the opposite direction, and it was found by a
person typing one sentence into the demo.

## D-16 · The self-harm contacts moved into the table

**Decided.** `responses.SELF_HARM` no longer contains phone numbers. They are
read from the verified table like every other contact.

**Why.** Two numbers were hardcoded in an approved string while the same two
sat in `services.csv`. Two copies, one authoritative, and no mechanism to keep
them agreeing. Now there is one source, and the rule the rest of the system
already follows — a contact is a table read, never text — has no exception.

## D-17 · Retrieve from the clause, not the paragraph

**Decided.** A multi-sentence message is split into clauses, each is searched
separately, and the results are pooled by score. A clause whose best match sits
below 0.55 contributes nothing.

**Why.** A girl sends a message, not a query, and it carries several intentions
at once. Embedded as one vector they average, and the emotional material wins
because there is more of it. Measured on a real demo message: whole-paragraph
retrieval returned mood and sex-drive passages at 0.561 while the passage that
answers her was absent from the top five, so the generator correctly refused to
cite anything and the fall-through rescued the turn as pure conversation. She
was asked to choose between the pill question and the Shasha question she had
already asked together.

**No clause is classified.** There is no word list deciding which clause is the
health question — the similarity scores do that. That is the whole point, and
it is what a word list could never do: the first attempt at this problem *was*
a word list, and tested on five phrasings written afterwards it fired on two.

**The floor matters as much as the split.** Without it, emotional clauses still
contributed weak hits that filled seats, including *"I was raped and I am
worried that no one will believe me"* arriving beside a question about the pill.
Dropping the clause is the right cut rather than blocking the passage — the
passage is fine, the clause had nothing to ask.

**Measured, Experiment 4**, 15 mixed messages, criteria fixed beforehand:
wanted evidence 8→9 of 14, unwanted passages 4→3, the purely emotional control
now retrieves nothing at all. Clean single-sentence questions are untouched
(they do not split): Hit@5 0.926, MRR 0.883, unchanged.

## D-18 · A query rewrite, but only when the free tiers have measurably failed

**Decided.** Three tiers. The deterministic table runs first, clause splitting
second, and a model call rewrites the query only when the pooled result is still
below 0.60. The rewritten result is kept only if it actually scores better.

**Why this reverses an earlier decision.** Experiment 3 concluded a string table
beat a model rewriter and that a rewriter should not be built. That conclusion
was over-generalised and a reviewer caught it: the table was measured on 31
questions that were single-sentence, English and well formed, and real messages
are none of those. On phrasings the table had not been written for it fired on
two of five, and one miss was severe — *"nasikia sindano inakufanya unenepe"*
retrieved a passage about rape at 0.538.

**Why a model is safe here specifically.** It writes a search string and never a
word she reads. The worst case is retrieving the wrong passages, and the
grounded contract already declines to cite those. A rewriter cannot put a
fabricated fact in her answer because it is not writing her answer.

**Measured.** Of 15 mixed messages, 7 were still weak after the free tiers. The
rewrite recovered 5 of them, including rewriting *"i heard pills make someone
anone"* into the corpus's own section heading — *"Do COCs cause women to gain
or lose a lot of weight?"* — taking 0.587 to 0.798. The purely emotional control
returned NONE and was not rescued, which is correct.

**What would reverse it.** A cheaper tier that closes the same gap. The rate to
watch is how often it fires: on clean questions almost never, on mixed messages
about half.

## D-19 · Conversation continuity: a standing offer is not a follow-up

**Decided.** After she shares a feeling, a goal, a relationship or anything
about her life, the reply ends with **one specific question built from something
she has already said** — not with a standing offer, and never with a menu.

**Why.** The answers were correct and the conversation was going nowhere.
*"Whenever you're ready to talk about it"* and *"we can talk about your
relationship or anything else"* are warm and completely passive: they hand the
conversation back and leave her to do the work of restarting it. She came here
rather than the other way round.

**The distinction that made it work.** *Deflecting a topic is not ending a
conversation.* She wrote *"Anyway, story for another day"* about the thing
plainly bothering her, and the system agreed with her and closed the thread.
But a girl who genuinely does not want to discuss something does not mention it.
Naming it gently and asking one specific question is how she finds out it is
allowed. A real goodbye is still received and not questioned.

**Measured** over four runs at temperature 0.3 on the turn that failed:
1/3 ended on a specific question before, 4/4 after, and *"thanks aunti, i am
good now, bye"* still ends cleanly with no question attached.

**Why it matters beyond tone.** The question the rule produces —
*"How do you think he'll take it if you tell him that's where your head is
at?"* — reaches back three turns to the boyfriend, leaves the decision with her,
and opens the door to whether he accepts a no. Girl Effect's Theory of Change
runs through self-efficacy and negotiation, not knowledge alone. A system that
answers perfectly and closes every thread is optimising for factual Q&A and
against the outcome.
