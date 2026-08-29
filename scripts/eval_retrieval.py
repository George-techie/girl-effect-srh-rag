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
from src.decision import rules
from src.rag import query_prep, retrieval

QUESTIONS = Path(__file__).resolve().parents[1] / "evaluation" / "questions_v1.jsonl"


def load_questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.open(encoding="utf-8") if line.strip()]


RESTATEMENTS = Path(__file__).resolve().parents[1] / "evaluation" / "restatements_v1.json"


ADEQUACY = Path(__file__).resolve().parents[1] / "evaluation" / "adequacy_v1.json"


def load_restatements() -> dict[str, str]:
    data = json.loads(RESTATEMENTS.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_adequacy() -> dict[str, list[str]]:
    data = json.loads(ADEQUACY.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


_ADEQUACY = load_adequacy()


def is_adequate(qid: str, texts: list[str]) -> bool | None:
    """Did any retrieved passage plausibly *answer* the question?

    Source-level gold labels say whether the right document came back. They
    cannot say whether the passage inside it was the one that answers her --
    CTL_01 scored a perfect hit while retrieving "Serving Diverse Groups", which
    does not. This is the floor under that: a phrase check, deliberately coarse,
    reproducible across runs, and blind to which source supplied the text.
    """
    phrases = _ADEQUACY.get(qid)
    if not phrases:
        return None
    blob = " ".join(texts).lower()
    return any(p.lower() in blob for p in phrases)


def evaluate(questions: list[dict], k: int, role_bonus: float = 0.0,
             restate: bool = False, prepare: bool = False) -> list[dict]:
    """Score each question.

    With `restate`, the *retrieval* query is the hand-written restatement while
    the question itself is untouched. That split is the point: her words are
    what a generator would answer; the restatement only ever reaches the
    encoder.

    With `prepare`, the query is what the shipped deterministic layer actually
    builds -- her words plus appended corpus vocabulary -- gated on the same
    condition the pipeline gates it on, so this measures the feature rather
    than an idealised version of it.
    """
    rewrites = load_restatements() if restate else {}
    rows: list[dict] = []

    for q in questions:
        query = rewrites.get(q["id"], q["question"]) if restate else q["question"]
        if prepare:
            decision = rules.decide(q["question"])
            query = query_prep.prepare(q["question"],
                                       restate=decision.restate).text
        hits = retrieval.search(query, k=k, role_bonus=role_bonus)
        metas = [h.metadata for h in hits]
        adequate = is_adequate(q["id"], [h.text for h in hits])
        dists = [1 - h.similarity for h in hits]

        retrieved = [h.source_id for h in hits]
        gold = set(q["gold_sources"])

        # Rank of the first gold source, 1-indexed; 0 when none appeared.
        rank = next((i for i, s in enumerate(retrieved, 1) if s in gold), 0)

        rows.append({
            **q,
            "query_used": query,
            "retrieved": retrieved,
            "roles": [m["document_role"] for m in metas],
            "tags": [m["citation_tag"] for m in metas],
            "sections": [m["section_title"] for m in metas],
            "top_similarity": round(1 - dists[0], 3) if dists else 0.0,
            "hit": bool(gold) and rank > 0,
            "recall": (len(gold & set(retrieved)) / len(gold)) if gold else None,
            "rr": (1 / rank) if rank else 0.0,
            "adequate": adequate,
        })
    return rows


def summarise(rows: list[dict]) -> dict:
    """The handful of numbers the role-preference experiment turns on."""
    scored = [r for r in rows if r["gold_sources"]]
    by_driver = collections.defaultdict(list)
    for r in scored:
        by_driver[r["driver"]].append(r)

    tops = collections.Counter(r["roles"][0] for r in rows if r["roles"])
    all_roles = collections.Counter(role for r in rows for role in r["roles"])
    total = sum(all_roles.values())

    def driver_mrr(name: str) -> float:
        g = by_driver.get(name, [])
        return statistics.mean(r["rr"] for r in g) if g else float("nan")

    judged = [r for r in scored if r["adequate"] is not None]
    return {
        "adequate": statistics.mean(r["adequate"] for r in judged) if judged else 0.0,
        "hit": statistics.mean(r["hit"] for r in scored),
        "recall": statistics.mean(r["recall"] for r in scored),
        "mrr": statistics.mean(r["rr"] for r in scored),
        "knowledge_mrr": driver_mrr("knowledge"),
        "control_mrr": driver_mrr("perceived_control"),
        "attitude_mrr": driver_mrr("attitude"),
        "identity_mrr": driver_mrr("self_identity"),
        "youth_top": tops.get("youth_answer", 0) / max(len(rows), 1),
        "youth_all": all_roles.get("youth_answer", 0) / max(total, 1),
        "clinical_top": tops.get("clinical_boundary", 0) / max(len(rows), 1),
    }


def sweep(questions: list[dict], k: int, bonuses: list[float]) -> None:
    print("\n" + "=" * 92)
    print(f"ROLE-PREFERENCE SWEEP · top-{k}")
    print("A soft score bonus on sources written for her. "
          "0.000 is plain cosine search.\n")
    cols = ("bonus", "Hit@5", "Rec@5", "MRR", "know", "control", "attitude", "identity",
            "youth top", "clin top")
    print("  " + "".join(f"{c:>10}" for c in cols))
    print("  " + "-" * 100)
    for b in bonuses:
        m = summarise(evaluate(questions, k, role_bonus=b))
        print(f"  {b:>10.3f}" + "".join(f"{m[key]:>10.3f}" for key in
              ("hit", "recall", "mrr", "knowledge_mrr", "control_mrr",
               "attitude_mrr", "identity_mrr")) +
              f"{m['youth_top']:>10.0%}{m['clinical_top']:>10.0%}")
    print("\n  youth top / clin top = share of questions whose FIRST result")
    print("  came from that role. 31 questions, so one is 3 percentage points.")


def compare(questions: list[dict], k: int) -> None:
    """Baseline against oracle restatement, with the criteria fixed beforehand."""
    base = evaluate(questions, k)
    orac = evaluate(questions, k, restate=True)
    b, o = summarise(base), summarise(orac)

    print("\n" + "=" * 84)
    print(f"ORACLE RESTATEMENT · top-{k}")
    print("Hand-written retrieval queries. An upper bound, not a design.\n")

    keys = [("adequate", "Adequate@5"), ("hit", "Hit@5"), ("recall", "Recall@5"), ("mrr", "MRR"),
            ("knowledge_mrr", "knowledge MRR"), ("control_mrr", "control MRR"),
            ("attitude_mrr", "attitude MRR"), ("identity_mrr", "identity MRR"),
            ("youth_top", "youth-facing top")]
    print(f"  {'':22}{'baseline':>10}{'oracle':>10}{'delta':>10}")
    print("  " + "-" * 52)
    for key, label in keys:
        d = o[key] - b[key]
        print(f"  {label:22}{b[key]:10.3f}{o[key]:10.3f}{d:+10.3f}")

    agency_b = (b["control_mrr"] + b["attitude_mrr"] + b["identity_mrr"]) / 3
    agency_o = (o["control_mrr"] + o["attitude_mrr"] + o["identity_mrr"]) / 3
    improved = sum(o[k_] > b[k_] for k_ in
                   ("control_mrr", "attitude_mrr", "identity_mrr"))

    print("\n  Criteria fixed before the run:")
    checks = [
        ("1 Hit@5 >= 0.90", o["hit"] >= 0.90, f"{o['hit']:.3f}"),
        ("2 knowledge MRR >= 0.90", o["knowledge_mrr"] >= 0.90, f"{o['knowledge_mrr']:.3f}"),
        (f"3 agency mean >= 0.761 and 2 of 3 up",
         agency_o >= 0.761 and improved >= 2,
         f"{agency_o:.3f}, {improved}/3 up"),
        ("4 overall MRR >= 0.863", o["mrr"] >= 0.863, f"{o['mrr']:.3f}"),
    ]
    for label, ok, got in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:38} {got}")
    print(f"\n  agency mean {agency_b:.3f} -> {agency_o:.3f}  ({agency_o - agency_b:+.3f})")

    # --- per-question movement ----------------------------------------------
    print(f"\n  {'question':10}{'driver':24}{'base':>7}{'oracle':>8}  movement")
    print("  " + "-" * 74)
    for rb, ro in zip(base, orac):
        if not rb["gold_sources"]:
            continue
        d = ro["rr"] - rb["rr"]
        if abs(d) < 1e-9:
            continue
        arrow = "improved" if d > 0 else "WORSE"
        print(f"  {rb['id']:10}{rb['driver']:24}{rb['rr']:7.2f}{ro['rr']:8.2f}  {arrow}")

    print(f"\n  {'boundary':10}{'':24}{'base sim':>9}{'oracle':>8}")
    print("  " + "-" * 74)
    for rb, ro in zip(base, orac):
        if rb["gold_sources"]:
            continue
        d = ro["top_similarity"] - rb["top_similarity"]
        flag = "  <-- more confident" if d > 0.02 else ""
        print(f"  {rb['id']:10}{rb['question'][:24]:24}"
              f"{rb['top_similarity']:9.3f}{ro['top_similarity']:8.3f}{flag}")


def compare_prepared(questions: list[dict], k: int) -> None:
    """Natural / shipped deterministic layer / oracle, side by side.

    The oracle column is a ceiling written by hand with the answer already
    known. The deterministic column is what a girl actually gets. They are not
    expected to meet, and the question this answers is only whether the cheap
    version moves toward the ceiling without dragging anything backwards.
    """
    base = evaluate(questions, k)
    prep = evaluate(questions, k, prepare=True)
    orac = evaluate(questions, k, restate=True)
    b, p, o = summarise(base), summarise(prep), summarise(orac)

    print("\n" + "=" * 84)
    print(f"DETERMINISTIC QUERY PREPARATION · top-{k}")
    print("Her words, plus corpus vocabulary appended, on factual and access "
          "turns only.\n")

    keys = [("adequate", "Adequate@5"), ("hit", "Hit@5"), ("recall", "Recall@5"),
            ("mrr", "MRR"), ("knowledge_mrr", "knowledge MRR"),
            ("control_mrr", "control MRR"), ("attitude_mrr", "attitude MRR"),
            ("identity_mrr", "identity MRR"), ("youth_top", "youth-facing top")]
    print(f"  {'':22}{'natural':>10}{'prepared':>10}{'oracle':>10}{'delta':>9}")
    print("  " + "-" * 61)
    for key, label in keys:
        print(f"  {label:22}{b[key]:10.3f}{p[key]:10.3f}{o[key]:10.3f}"
              f"{p[key] - b[key]:+9.3f}")

    def agency(m):
        return (m["control_mrr"] + m["attitude_mrr"] + m["identity_mrr"]) / 3

    print(f"\n  agency mean  {agency(b):.3f} natural -> {agency(p):.3f} prepared "
          f"-> {agency(o):.3f} oracle")

    touched = sum(1 for q in questions
                  if query_prep.prepare(
                      q["question"], restate=rules.decide(q["question"]).restate
                  ).restated)
    print(f"  {touched} of {len(questions)} questions had any mapping applied. "
          "The rest are untouched by construction.")

    print("\n  Adoption criteria, fixed before the run:")
    regressions = [(rb["id"], rb["rr"], rp["rr"])
                   for rb, rp in zip(base, prep)
                   if rb["gold_sources"] and rp["rr"] < rb["rr"] - 1e-9]
    adequacy_drop = p["adequate"] < b["adequate"] - 1e-9
    for label, ok, got in [
        ("A no drop in Adequate@5", not adequacy_drop,
         f"{b['adequate']:.3f} -> {p['adequate']:.3f}"),
        ("B no drop in Hit@5", p["hit"] >= b["hit"] - 1e-9,
         f"{b['hit']:.3f} -> {p['hit']:.3f}"),
        ("C at most 1 per-question regression", len(regressions) <= 1,
         f"{len(regressions)} regressed"),
        ("D some measured gain somewhere",
         p["adequate"] > b["adequate"] or p["mrr"] > b["mrr"],
         f"MRR {b['mrr']:.3f} -> {p['mrr']:.3f}"),
    ]:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:38} {got}")

    print(f"\n  {'question':10}{'driver':24}{'natural':>8}{'prep':>7}  movement")
    print("  " + "-" * 74)
    moved = False
    for rb, rp in zip(base, prep):
        if not rb["gold_sources"] or abs(rp["rr"] - rb["rr"]) < 1e-9:
            continue
        moved = True
        print(f"  {rb['id']:10}{rb['driver']:24}{rb['rr']:8.2f}{rp['rr']:7.2f}  "
              f"{'improved' if rp['rr'] > rb['rr'] else 'WORSE'}")
    if not moved:
        print("  no question changed rank")

    print(f"\n  {'question':10}{'adequacy natural -> prepared'}")
    print("  " + "-" * 74)
    for rb, rp in zip(base, prep):
        if rb["adequate"] is None or rb["adequate"] == rp["adequate"]:
            continue
        print(f"  {rb['id']:10}{str(rb['adequate']):>6} -> {str(rp['adequate']):<6}"
              f"  {'GAINED' if rp['adequate'] else 'LOST'}")

    print(f"\n  {'boundary':10}{'':24}{'natural':>9}{'prep':>8}")
    print("  " + "-" * 74)
    for rb, rp in zip(base, prep):
        if rb["gold_sources"]:
            continue
        d = rp["top_similarity"] - rb["top_similarity"]
        flag = "  <-- more confident" if d > 0.02 else ""
        print(f"  {rb['id']:10}{rb['question'][:24]:24}"
              f"{rb['top_similarity']:9.3f}{rp['top_similarity']:8.3f}{flag}")


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
    ap.add_argument("--role-bonus", type=float, default=0.0)
    ap.add_argument("--sweep", action="store_true",
                    help="compare role-preference strengths and stop")
    ap.add_argument("--restate", action="store_true",
                    help="use the hand-written retrieval restatements")
    ap.add_argument("--compare-restatement", action="store_true",
                    help="baseline against oracle restatement, and stop")
    ap.add_argument("--prepare", action="store_true",
                    help="use the shipped deterministic query preparation")
    ap.add_argument("--compare-prepared", action="store_true",
                    help="natural vs deterministic vs oracle, and stop")
    args = ap.parse_args()

    questions = load_questions()

    if args.compare_prepared:
        compare_prepared(questions, args.k)
        return 0

    if args.sweep:
        sweep(questions, args.k, [0.0, 0.02, 0.04, 0.06, 0.08, 0.12, 0.20])
        return 0

    if args.compare_restatement:
        compare(questions, args.k)
        return 0

    rows = evaluate(questions, args.k, role_bonus=args.role_bonus,
                    restate=args.restate, prepare=args.prepare)
    report(rows, args.k, args.show_misses)

    if args.save:
        out = Path(__file__).resolve().parents[1] / "evaluation" / "results" / f"retrieval_k{args.k}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
