# How each decision is made

Eight stages, seven of them deterministic. For each one: **what happens, why it
exists, how it is implemented, and what happens when it fails.**

"Deterministic" here means ordered regex pattern families and word lists — no
scoring, no thresholds, no model. That choice is defended at the bottom, along
with its real weakness.

---

## 1 · Validate

**What happens.** Her message is checked for type and length, and runs of
whitespace are collapsed. Nothing else is touched — not case, punctuation,
spelling, emoji or Sheng. A register label is attached: English, Kiswahili,
mixed, or Sheng code-switch.

**Why it exists.** Two reasons. Nothing unusable should reach routing, the
encoder or a model. And the register label decides what language the reply comes
back in — a girl who writes *"but pia nataka kumaliza shule"* and receives flat
English has been told, without words, that she was speaking wrongly.

**How it is implemented.** `input_validation.validate()` — a type check, a length
check against `MAX_INPUT_CHARS`, and `" ".join(message.split())`. The register
label comes from `language/detect.py`: a count of Kiswahili function words and
Sheng markers, plus a regex for English verbs carrying Swahili morphology
(`ananitext`, `wanakaa`). **Two markers is the bar**, not a proportion of the
message — a proportion dilutes as a message gets longer, and one deliberate
Swahili clause is a signal rather than noise.

**When it fails.** Over-length and empty input get approved text and never reach
a model. A missed register label is the more likely failure and it is silent:
the reply comes back in English and nothing errors. It is caught by the register
metric in the conversation evaluation, currently 38/38.

---

## 2 · Safeguard

**What happens.** Every message is screened for harm, coercion or urgent risk
**before anything is routed or searched**. If the screen fires, nothing
downstream runs: no retrieval, no model call, no validator. She gets approved
text and verified contacts.

**Why it exists.** Retrieval cannot decline. A deliberately out-of-scope question
was measured retrieving at **0.668, higher than most in-scope questions**, so a
similarity threshold cannot tell you whether to answer. The decision has to be
made on her words, before anything is searched. And a girl who asks about the
pill and then says her boyfriend threatened her has not changed the subject.

**How it is implemented.** Two mechanisms in fixed order.

*The Kenyan lexicon* — 19 reviewed terms, 90 surface forms, 9 carrying a risk
tag. Each entry is a term plus its inflections:

```json
{"term": "hunipiga",
 "variants": ["ananipiga", "kunipiga", "amenipiga", "hunichapa", "kuchapwa"],
 "meaning": "hits me / beats me",
 "risk_tags": ["physical_violence"],
 "confidence": "high"}
```

| Term | Means | Risk tag |
|---|---|---|
| `hunipiga` | hits me / beats me | physical_violence |
| `huniguza` | touches me inappropriately | sexual_abuse |
| `kuondokea hii dunia` | to leave this world | self_harm_risk |
| `sitaki kukuwa kwa hii dunia` | I don't want to be in this world | self_harm_risk |
| `kuspread foto` | to share my photos around | exploitation |
| `sidai kuenda mtaa` | I'm afraid to go home | unsafe_environment |

A risk tag routes straight to safeguarding. The message is also **normalised** —
`hunipiga` rewritten to `hits me` — and **both the original and the normalised
text are scanned**, so a Sheng disclosure also reaches the English patterns.

*Then five regex families*, first match wins:

| Family | Patterns | Tier | An actual pattern |
|---|--:|---|---|
| `_SELF_HARM` | 6 | urgent | `(don't\|do not) want to be (here\|alive)` |
| `_HARM` | 6 | urgent | `(rape[ds]?\|forced? me\|made me have sex)` |
| `_SABOTAGE` | 4 | urgent | condom removed, pills hidden or tampered with |
| `_REPRODUCTIVE_COERCION` | 14 | concern | `if (i\|you\|she\|he) (really )?love[ds]? (me\|him\|her)` |
| `_THIRD_PARTY` | 3 | concern | she is reporting harm to someone else |

The order is the safety argument: self-harm is checked first so it can never be
read as ordinary harm and given the wrong contacts.

**When it fails.** Two directions, and they are not equally bad.

*A miss* — a disclosure phrased in words no pattern covers — is answered as an
ordinary question. Nothing errors. This is the failure the design fears most,
and the only defences are the breadth of the families and the lexicon.

*A false alarm* — an ordinary question read as a disclosure — costs her a
referral she did not need and reads as being passed on. Precision is currently
1.000 on the benchmark, so this is not happening in the measured set.

Recall is **gated** in the evaluation criteria at ≥ 0.92 and precision is
reported but not gated, because those two costs are not comparable.

---

## 3 · Route

**What happens.** If nothing safeguarding matched, the message is assigned one of
five remaining paths, which determines whether it reaches the corpus, which
contract the reply is written under, and whether verified contacts are attached.

**Why it exists.** Not every message should enter the retrieval pipeline. A
greeting has nothing to look up and nothing to cite; answering it under a
contract that requires a citation is how *"hello aunti"* became *"I had trouble
putting that answer together."* Roughly a third of turns reach no model at all,
which is also why safeguarding replies arrive in 0 ms.

**How it is implemented.** The same mechanism, in this order:

```
out_of_scope → access → chat → aspirations → support → factual
```

| Family | Patterns | What it catches |
|---|--:|---|
| `_OUT_OF_SCOPE` | 11 | `which (pill\|method) should i (take\|use)`, dosing, diagnosis |
| `_ACCESS` | 12 | `where (can\|do\|could\|should) (i\|we) …(get\|go\|find\|buy)` |
| `_CHAT` | 7 | greetings and thanks — **only on messages of ≤ 12 words** |
| `_ASPIRATION` | 7 | `i want to (be\|become) an? \w+`, school and career plans |
| `_SUPPORT` | 8 | `i('m\| am) …(scared\|worried\|ashamed\|nervous\|overwhelmed)` |
| `factual` | — | **the fallback.** Anything that matched nothing at all |

Three details, each of which exists because of a real failure:

**Intervening words are allowed.** The `(?:\w+\s+){0,3}?` between *"I am"* and the
feeling word is why *"i am **just super** scared"* reaches support. A fixed list
of intensifiers caught *"so scared"* and missed that one entirely.

**Small talk has to be small.** The chat patterns are anchored to the start of a
message, so without the 12-word cap a 48-word message opening with *"thanks for
the willingness to give me support"* was classified as a greeting and never
reached the corpus.

**An explicit question beats the feeling around it.** If `_SUPPORT` matches *and*
`_ASKING` matches — `tell me (what|how|about)`, `what happens`, `walk me
through` — the turn goes to `factual`. The grounded contract can acknowledge
**and** answer; the conversational one can only acknowledge.

**When it fails.** A wrong path is usually recoverable, and that is deliberate.
A message wrongly sent to `factual` retrieves, fails to cite anything, and falls
through to the conversational contract rather than refusing. A message wrongly
sent to `support` gets warmth but no facts — the worse of the two, and the reason
`_ASKING` exists.

---

## 4 · Resolve

**What happens.** A short follow-up like *"and does it hurt?"* is linked to the
subject of an earlier turn — **for retrieval only.** Her message reaches the
generator unchanged.

**Why it exists.** A fragment carries its meaning in the turn before it. Searched
alone, *"and does it hurt?"* asked after a question about the implant retrieved
**female sterilization**, and *"where can I go?"* after a coercion disclosure
retrieved **BTL**, which is permanent. That is not a degraded answer; it is an
answer to a different question, and in both cases the different question was
about being sterilised.

**How it is implemented.** `conversation.is_dependent()` — four tests, in order,
and the order is load-bearing:

```python
if len(text.split()) > 9:   return False   # long enough to stand alone
if _CONTENT.search(text):   return False   # names a method, body part, service
if _BACKREF.search(text):   return True    # "and", "what about", "is it"
return bool(_DANGLING.search(text)) or text.endswith("?")
```

`_CONTENT` is a word list: `implant · injection · depo · IUD · pill · condom ·
contraception · pregnant · period · fertility · HIV · STI · clinic · nurse ·
boyfriend · school · parents`. `_BACKREF` is the openings that point backwards.
`_DANGLING` is a pronoun with nothing in the message to refer to.

**Content is checked before backreference**, because *"what about the injection"*
opens with a backreference *and* names its own subject. Resolving it against an
earlier implant question put both methods in one query and the implant won — she
asked about one method and would have been answered about another.

**When it fails.** If no antecedent is available, the fragment is searched as-is
and usually retrieves weakly, which the evidence floor then catches. If it
resolves against a *stale* topic, the query drifts — which is why the topic is
stored separately from the six-turn window, and why it is not carried across a
safeguarding turn.

---

## 5 · Prepare

**What happens.** The retrieval query is expanded with the corpus's own
vocabulary, and long messages are split into clauses. Both are retrieval-only and
both run only on `factual` and `access` turns.

**Why it exists.** The corpus says *"informed consent for adolescents and youth"*.
She says *"without my parents agreeing"*. The passage exists, is Kenyan, is
authoritative — and retrieves at **0.565 from her words against 0.711 from the
document's own**. Same question, different register.

**How it is implemented.** A 10-entry mapping table, each entry labelled
`evidenced` or `extrapolated` in the source so a reviewer can discount the second
group:

```python
(r"\bwithout (my )?(parents?|mum|mother|dad|father|guardian)\b",
 "informed consent for adolescents and youth parental consent",
 "evidenced")
```

**Expansion, not replacement.** Her words stay in the query and the corpus's are
appended, so a mapping that does not apply contributes an unused phrase rather
than a wrong query.

Clause splitting runs on messages of ≥ 16 words, on sentence boundaries only,
with no attempt to classify which clause matters.

**When it fails.** A missing mapping means the query stays in her register and
retrieves weakly — which is what tier 3 of retrieval exists to catch. A wrong
mapping adds an unused phrase. The asymmetry is why the table is safe to be
wrong about.

---

## 6 · Retrieve

**What happens.** The query is embedded locally with BGE-M3 and searched against
Chroma by cosine similarity, returning the top five passages.

**There is no domain filter.** One collection, the whole corpus, every search.

**Why no filter.** An earlier version preferred youth-facing sources with a score
bonus; it was swept across seven strengths and **rejected** — it moved youth
material to the top without improving what the answers could support. Filtering
by domain has the same problem in a harder form: a girl's message rarely sits in
one domain, and a filter that guesses wrong removes the right passage entirely
rather than ranking it lower. Relevance is controlled by the query and by a
floor instead.

**How it is implemented.** Three tiers, cheapest first:

| Tier | Mechanism | Cost |
|---|---|---|
| 1 | the vocabulary table from stage 5 | free |
| 2 | each clause searched separately, results pooled by score | free |
| 3 | one model call rewrites the query — **only if tiers 1–2 return below 0.60** | 1 call |

**No word list decides which clause is the health question — the similarity
scores do.** A clause whose best match falls below **0.55** contributes nothing
to the pool. That floor is what stops *"I was raped and I am worried no one will
believe me"* arriving beside a question about the pill: the emotional clause
retrieves in the noise band, so it is dropped rather than ranked.

Tier 3 is the one place a model is safe inside retrieval, because **it writes a
search string and never a word she reads**. Its result is kept only if it scores
better than what the free tiers found.

**When it fails.** Weak retrieval produces no citation, and the grounded contract
then declines to answer rather than inventing one. On an `access` turn that is
not a dead end: the verified service table answers *"where can I go"* on its own,
because no document knows what is near her anyway.

---

## 7 · Generate

**What happens.** One hosted model call writes the reply, under one of two
contracts.

**Why two contracts.** A grounded answer is safe because every claim carries a
citation. A conversational reply is safe for the opposite reason: it makes no
claim at all. Holding a greeting to the first contract, or a health question to
the second, produces the two characteristic failures — a refused greeting, and a
warm reply that quietly drops the facts.

**How it is implemented.** The contract is chosen by **which path produced the
turn**, never inferred from whether citations happen to be present — an uncited
grounded answer would otherwise validate itself. `factual` and `access` are
grounded; `chat` and `support` are conversational. Safeguarding never reaches
this stage at all.

**When it fails.** A provider error returns approved text rather than a refusal,
because a technical failure that reads like *"we have nothing for you"* gives her
no reason to try again.

---

## 8 · Check

**What happens.** The draft is checked against the contract it was written under,
before anything is shown.

**Why it exists.** This is the deterministic half of the previous build's LLM
output judge — the half that checks things which are not matters of opinion.

**How it is implemented.** Regex over the draft:

| Fatal — the draft does not ship | Recorded, and sent anyway |
|---|---|
| a grounded answer with no citation | dashes used as punctuation |
| a citation pointing at a passage never retrieved | machinery talk — *"the passages"* |
| a citation marker on a turn that had no passages | offering to look up what it already holds |
| a phone-shaped string | disclaiming contacts it is about to be given |
| a claim of lived experience — *"I've been there"* | over the word limit |

**The asymmetry is deliberate.** A safety property blocks the reply; a register
property is counted and shipped. Blocking an answer over a dash is precisely how
the previous build's output judge came to refuse a girl's compliment, twice.

**When it fails.** If the only fatal problem is a missing citation and retrieval
was strong, the answer is regenerated once with the omission named; only a second
failure falls through to the conversational contract. Everything else fatal
blocks outright.

---

## The honest weakness

**Pattern families do not generalise, and the design assumes they will miss.**
Every intervening-word fix above came from a real miss found by a person typing a
real sentence — *"just super scared"*, *"where can i actually go"*, *"I just
feel"*. A longer word list would only move the boundary.

So the recovery paths matter more than the patterns:

- `factual` is the catch-all, so an unmatched message still gets answered
- a grounded turn that cannot cite falls through to the conversational contract
- an access turn that cannot cite still gets the verified service table
- an empty retrieval result on a fallback turn is answered conversationally

**The pattern families decide which contract is tried first, not whether she gets
an answer.** That is what makes an auditable mechanism affordable: a
safeguarding decision can be traced to the exact pattern that caught it, and
missing is survivable by construction.
