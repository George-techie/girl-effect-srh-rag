# Girl Effect SRH — corpus and retrieval

A refined take on a safety-aware assistant for adolescent girls in Kenya,
narrowed to what Girl Effect actually works on: **contraception and sexual
health, and the empowerment outcomes that follow from them.**

**This repository currently contains one thing: eight governed PDFs turned into a
searchable vector index.** No chatbot, no routing, no agents, no judges, no UI.
Those come back only where evaluation shows they are needed.

---

## Why this repo is small

The previous build answered the same brief across four content tracks with five
model roles, two LLM judges and a six-configuration ablation. Its own benchmark
said that was too much: the simplest safe configuration scored the **highest**
action accuracy (0.882) with the **fewest** unhelpful refusals, and adding the
LLM evidence judge dropped accuracy to 0.745 while doubling refusals.

So the rule here is: **deterministic and free earns its place; a model asked for
a second opinion has to prove it.** Task 1 stops at retrieval, because retrieval
is the part that cannot be skipped.

---

## The corpus

Eight sources, chosen for authority and for who they were written for.

| Citation tag | Year | Role | Chunks |
|---|---|---|---|
| Kenya MoH · Contraception FAQs | 2023 | youth answer | 23 |
| UNICEF/UNFPA · HIV & Prevention | 2021 | youth answer | 15 |
| UNICEF/UNFPA · Young Parenthood | 2021 | youth answer | 12 |
| UNICEF/UNFPA · Safety & Relationships | 2021 | youth answer | 8 |
| UNFPA · SRHR Rights & Empowerment | 2024 | evidence | 287 |
| WHO · Contraception & Empowerment | 2020 | evidence | 22 |
| WHO · Contraception Clinical Guide | 2022 | clinical boundary | 1,005 |
| Kenya MoH · Family Planning Guidelines | 2018 | clinical boundary | 321 |

**1,693 chunks · 388,360 tokens · 962 pages · 0 chunks over the encoder cap**

The citation tag is the point. It travels into Chroma metadata and out to the
interface, so a girl sees `WHO · Contraception Clinical Guide` rather than
`family-planning-a-global-handbook-for-providers-2022`.

### The one governance field that survived

`document_role` separates **what she reads** from **what a clinician reads**.
Two sources are provider guidance — a 486-page WHO handbook whose title says
"for providers", and Kenya's national service-delivery guidelines. They belong
in the corpus because they settle what is true and what Kenyan practice is. They
are not the voice that should answer a sixteen-year-old asking whether
contraception will make her infertile.

Nothing filters on the role yet. It is recorded now because it is unrecoverable
later without re-ingesting, and the filtering decision belongs after retrieval
evaluation rather than before it.

---

## Quick start

```bash
pip install -r requirements.txt

python scripts/ingest.py --dry-run     # parse, chunk, report — no embedding
python scripts/ingest.py               # the same, then embed and index
python scripts/search.py "can contraception make me infertile"
python scripts/inspect_corpus.py --source KE_FAQ --sections
pytest tests/ -q
```

Embeddings are **BAAI/bge-m3, run locally** — multilingual, because the audience
code-switches, and neither the corpus nor the query leaves the machine.
Chunking is a 500-token target, 650 cap, **zero overlap**.

> Those chunk settings come from the previous project's 12-configuration sweep,
> which found Hit@5 flat from 400–650 and no benefit from overlap. **That sweep
> ran on a differently-shaped corpus** — mostly narrative guides, where this one
> is heavily question-and-answer. They are a sensible starting point, not a
> validated setting for this corpus.

---

## What ingestion found

Two extraction defects, both caught by reading the output rather than by a test.

**The Kenya MoH FAQ was corrupted.** That PDF encodes its `ti`/`ft`/`tt`
ligatures at Latin Extended-B codepoints, so extraction returned `Ɵme`, `aŌer`,
`transmiƩed`, `breasƞeeding` — 85 occurrences in the only Kenyan youth-facing
source in the corpus. It fails quietly, because the result still looks like
words. Each repair is confirmed against several words rather than inferred from
one, and a test now fails if any survive.

**One Q&A source lost its structure.** UNICEF *Staying Safe* produced 2 sections
from 17 pages where its siblings gave 12 and 17. The cause was a 20-word cap on
headings: youth Q&A booklets ask questions in her own words, and *"I feel
embarrassed and ashamed when my friends shout sexual comments at girls on the
street; how can I get them to stop?"* is 23 words. Every such question was
dropped into the body before the question rule could see it. Widening the cap
recovered structure across all three Q&A sources — but *Staying Safe* still
reaches only 5 sections, because it is laid out magazine-style and its questions
are not adjacent to their answers in the text layer. **Left as a known
limitation.** It is one source of eight, and fixing it means a special-case
parser for one PDF — worth doing if evaluation shows that source
underperforming, not before.

---

## What the smoke tests showed

Retrieval routes by **register**, which was not the expected result.

Asked clinically, the provider handbooks answer:

```
"Can contraception make me infertile?"
1. WHO · Contraception Clinical Guide          0.676
   p.417 · Contraceptives Do Not Cause Infertility
```

Asked the way a girl would ask, the youth Q&A wins outright:

```
"I'm not ready to have a baby. What can I do?"
1. UNICEF/UNFPA · Young Parenthood             0.701
   p.5 · I'm not ready to become a father. What can I do to prevent a pregnancy?
2. UNICEF/UNFPA · Young Parenthood             0.628
   p.3 · How do I know if I'm ready to have a baby?
```

**The open question for the next task.** 78% of chunks are provider guidance —
1,326 clinical against 58 youth-facing — because two documents run to 486 and
216 pages while the youth booklets are 17. Factual questions are therefore
usually answered from a clinician's handbook. That may be correct, since the
handbook is the authority on what is true. It may also mean the answers she gets
are accurate and written for the wrong reader. Retrieval evaluation on the
use-case question set decides which, and `document_role` is already in the
metadata if the answer turns out to be weighting or filtering by it.

---

## Layout

```
corpus/raw/                 the eight PDFs, named as they appear in citations
corpus/registry/            source_registry.csv — 8 rows, editable by anyone
src/config.py               settings; small on purpose
src/rag/registry.py         reads the CSV
src/rag/loaders.py          PyMuPDF extraction, heading recovery
src/rag/cleaning.py         running headers, ligature repair, hyphen joins
src/rag/chunking.py         section-aware, sentence-boundary, 500/650/0
src/rag/indexing.py         bge-m3 embeddings, persistent Chroma
scripts/                    ingest · search · inspect_corpus
tests/test_corpus.py        13 tests
```

Ingestion is ported from the previous repository rather than rewritten. The
registry is not: 462 lines of hand-written Python became a CSV and 120 lines of
code, because every document here is open-licence and none needs hand-picked
page ranges.

---

## Retrieval evaluation

31 questions, tagged by the **eight behavioural drivers** in Girl Effect's Theory
of Change rather than by generic RAG categories. Full write-up:
[`evaluation/README.md`](evaluation/README.md).

**Hit@5 0.926 · Recall@5 0.599 · MRR 0.883** (source-level gold labels, so
Hit@5 is an optimistic upper bound).

Three findings decide what gets built next:

**Knowledge scores 1.000. Agency does not.** The weakest drivers are *perceived
control* (0.667), *attitude* (0.750) and *self identity* (MRR 0.417) — the
questions about whether this is allowed, whether it is shameful, and whether it
is for her. A retriever measured only on factual questions looks flawless while
failing the drivers the Theory of Change says lead to service access.

**65% of top results come from provider manuals.** Two documents are 486 and 216
pages; the youth booklets are 17. The facts she gets are right and the reader
they were written for is a clinician. `document_role` is already in the
metadata — this is the measurement that says to use it.

**Asking in Kiswahili costs −0.062 similarity**, measured over five matched
pairs, and changes which source answers in two of five. Direct translation is
handled well; idiomatic Sheng is not — *"inaharibu mji wa mtoto"* is a metaphor,
and it retrieved a policy report where its English twin found the myth-correcting
passage immediately.

And every boundary case returns a confident result. "My periods have been
irregular for three months" — a topic deliberately cut from scope — retrieves at
**0.668, higher than most in-scope questions**. Asked "am I too young to be
thinking about protecting myself?", the second result is *"I was raped and I am
worried that no one will believe me."*

That is not a retrieval bug. Retrieval found the nearest text, which is its job.
It is the argument for one component above the retriever whose only job is
deciding **whether to answer** — running before retrieval, because the
similarity scores give it nothing to work with.

---

## Next

A single decision layer above retrieval, and a generator. Nothing else until
measurement asks for it.
