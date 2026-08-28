"""Retrieval evaluation against the use-case question set.

    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py -k 5 --show-misses

Measures three things, and reports them separately because they fail for
different reasons:

  1. Hit@k / Recall@k / MRR   did the right *source* come back at all
  2. by behavioural driver    Girl Effect's Theory of Change has eight drivers,
                              and Knowledge is one of them. A retriever tuned on
                              factual questions can look excellent while failing
                              every question about agency or stigma.
  3. by document role         whether a girl's question is being answered from
                              material written for her or from a provider manual

Gold labels are **source-level**, as in the previous project: the question is
whether the right document came back, not whether the best paragraph in it
ranked first. That makes Hit@k an optimistic upper bound, and it is reported as
one.

No LLM. This measures retrieval only.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.rag import indexing

QUESTIONS = Path(__file__).resolve().parents[1] / "evaluation" / "questions_v1.jsonl"


def load_questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.open(encoding="utf-8") if line.strip()]


def evaluate(questions: list[dict], k: int) -> list[dict]:
    collection = indexing.get_collection()
    rows: list[dict] = []

    for q in questions:
        res = collection.query(
            query_embeddings=[indexing.embed_query(q["question"])],
            n_results=k,
            include=["metadatas", "distances"],
        )
        metas = res["metadatas"][0]
        dists = res["distances"][0]

        retrieved = [m["source_id"] for m in metas]
        gold = set(q["gold_sources"])

        # Rank of the first gold source, 1-indexed; 0 when none appeared.
        rank = next((i for i, s in enumerate(retrieved, 1) if s in gold), 0)

        rows.append({
            **q,
            "retrieved": retrieved,
            "roles": [m["document_role"] for m in metas],
            "tags": [m["citation_tag"] for m in metas],
            "sections": [m["section_title"] for m in metas],
            "top_similarity": round(1 - dists[0], 3) if dists else 0.0,
            "hit": bool(gold) and rank > 0,
            "recall": (len(gold & set(retrieved)) / len(gold)) if gold else None,
            "rr": (1 / rank) if rank else 0.0,
        })
    return rows


def report(rows: list[dict], k: int, show_misses: bool) -> None:
    scored = [r for r in rows if r["gold_sources"]]
    boundary = [r for r in rows if not r["gold_sources"]]

    print(f"\n{'=' * 78}\nRETRIEVAL · top-{k} · {config.EMBEDDING_MODEL}")
    print(f"{len(rows)} questions — {len(scored)} with gold sources, "
          f"{len(boundary)} boundary cases with none by design\n")

    hit = statistics.mean(r["hit"] for r in scored)
    rec = statistics.mean(r["recall"] for r in scored)
    mrr = statistics.mean(r["rr"] for r in scored)
    print(f"  Hit@{k}     {hit:.3f}      at least one gold source returned")
    print(f"  Recall@{k}  {rec:.3f}      share of gold sources returned")
    print(f"  MRR        {mrr:.3f}      how highly the first gold source ranked")

    # --- by driver -----------------------------------------------------------
    print(f"\n{'By behavioural driver':38} {'n':>3} {'Hit':>6} {'MRR':>6} {'Top sim':>8}")
    print("-" * 66)
    by_driver = collections.defaultdict(list)
    for r in scored:
        by_driver[r["driver"]].append(r)
    for driver, group in sorted(by_driver.items(),
                                key=lambda kv: statistics.mean(r["hit"] for r in kv[1])):
        print(f"  {driver:36} {len(group):3} "
              f"{statistics.mean(r['hit'] for r in group):6.3f} "
              f"{statistics.mean(r['rr'] for r in group):6.3f} "
              f"{statistics.mean(r['top_similarity'] for r in group):8.3f}")

    # --- who is answering ----------------------------------------------------
    print(f"\n{'Where the top result came from':38} {'count':>6} {'share':>7}")
    print("-" * 54)
    tops = collections.Counter(r["roles"][0] for r in rows if r["roles"])
    for role, n in tops.most_common():
        print(f"  {role:36} {n:6} {n / len(rows):6.0%}")

    all_roles = collections.Counter(role for r in rows for role in r["roles"])
    total = sum(all_roles.values())
    print(f"\n{'Across all ' + str(total) + ' retrieved chunks':38} {'count':>6} {'share':>7}")
    print("-" * 54)
    for role, n in all_roles.most_common():
        print(f"  {role:36} {n:6} {n / total:6.0%}")

    # --- boundary cases ------------------------------------------------------
    print(f"\n{'=' * 78}\nBOUNDARY CASES — retrieval has no way to refuse\n")
    for r in boundary:
        print(f"  {r['id']}  sim {r['top_similarity']:.3f}  {r['question'][:58]}")
        print(f"          -> {r['tags'][0]} · {r['sections'][0][:48]}")
    print("\n  Every one returns something confident. That is not a retrieval")
    print("  failure — it is the argument for a component whose job is to")
    print("  decide whether to answer, sitting above the retriever.")

    if show_misses:
        misses = [r for r in scored if not r["hit"]]
        print(f"\n{'=' * 78}\nMISSES — no gold source in top {k}\n")
        for r in misses:
            print(f"  {r['id']} ({r['driver']})  {r['question']}")
            print(f"     wanted {r['gold_sources']}")
            print(f"     got    {r['retrieved']}")
            print(f"     top    {r['tags'][0]} · {r['sections'][0][:52]}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-k", type=int, default=config.RETRIEVAL_TOP_K)
    ap.add_argument("--show-misses", action="store_true")
    ap.add_argument("--save", action="store_true", help="write results JSON")
    args = ap.parse_args()

    questions = load_questions()
    rows = evaluate(questions, args.k)
    report(rows, args.k, args.show_misses)

    if args.save:
        out = Path(__file__).resolve().parents[1] / "evaluation" / "results" / f"retrieval_k{args.k}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
