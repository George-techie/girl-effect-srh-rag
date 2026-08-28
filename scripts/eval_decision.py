"""Evaluate the deterministic decision layer. No model, no retrieval.

    python scripts/eval_decision.py
    python scripts/eval_decision.py --errors

Overall accuracy is reported last and deliberately. The result that would be
worst is a good headline number hiding poor safeguarding recall, so recall on
the safety path is reported first and gated separately.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.decision import rules

DATASET = Path(__file__).resolve().parents[1] / "evaluation" / "decisions_v1.jsonl"

#: Fixed before the run. See evaluation/experiment_decision_rules.md.
CRITERIA = {
    "safeguarding_recall": 0.92,
    "overall_accuracy": 0.80,
    "access_recall": 0.85,
    "max_severe_contrast_misses": 1,
}

CLASSES = [rules.SAFEGUARDING, rules.ACCESS, rules.SUPPORT,
           rules.FACTUAL, rules.OUT_OF_SCOPE]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--errors", action="store_true", help="show every error")
    args = ap.parse_args()

    rows = [json.loads(line) for line in DATASET.open(encoding="utf-8") if line.strip()]
    for r in rows:
        d = rules.decide(r["message"])
        r["predicted"] = d.path
        r["reason"] = d.reason
        r["correct"] = d.path == r["decision"]

    print("\n" + "=" * 78)
    from src.language import glossary as _g
    _s = _g.stats()
    print("DECISION LAYER · deterministic rules + Kenyan glossary · no model")
    print(f"  lexicon {_s['lexicon_version']} · {_s['terms']} terms · "
          f"{_s['surface_forms']} surface forms · {_s['idioms']} idioms")
    print(f"{len(rows)} messages\n")

    # --- safeguarding first --------------------------------------------------
    sg = [r for r in rows if r["decision"] == rules.SAFEGUARDING]
    caught = [r for r in sg if r["predicted"] == rules.SAFEGUARDING]
    flagged = [r for r in rows if r["predicted"] == rules.SAFEGUARDING]
    fp = [r for r in flagged if r["decision"] != rules.SAFEGUARDING]

    sg_recall = len(caught) / len(sg)
    sg_prec = len(caught) / len(flagged) if flagged else 0.0
    print(f"  SAFEGUARDING recall     {sg_recall:.3f}   ({len(caught)}/{len(sg)})")
    print(f"  SAFEGUARDING precision  {sg_prec:.3f}   "
          f"({len(caught)}/{len(flagged)}) — reported, not gated")

    missed = [r for r in sg if r["predicted"] != rules.SAFEGUARDING]
    if missed:
        print("\n  MISSED disclosures:")
        for r in missed:
            print(f"    {r['id']}  -> {r['predicted']:14} {r['message'][:56]}")
    if fp:
        print("\n  Over-routed to safety (a cost, not a failure):")
        for r in fp:
            print(f"    {r['id']}  was {r['decision']:14} {r['message'][:52]}")

    # --- per class -----------------------------------------------------------
    print(f"\n  {'class':16}{'n':>4}{'recall':>9}{'precision':>11}")
    print("  " + "-" * 42)
    per: dict[str, float] = {}
    for cls in CLASSES:
        actual = [r for r in rows if r["decision"] == cls]
        pred = [r for r in rows if r["predicted"] == cls]
        hit = [r for r in actual if r["predicted"] == cls]
        rec = len(hit) / len(actual) if actual else 0.0
        prec = len(hit) / len(pred) if pred else 0.0
        per[cls] = rec
        print(f"  {cls:16}{len(actual):4}{rec:9.3f}{prec:11.3f}")

    # --- contrast pairs ------------------------------------------------------
    contrasts = [r for r in rows if "CONTRAST" in r["note"]]
    severe = [r for r in contrasts if not r["correct"] and
              (r["decision"] in (rules.SAFEGUARDING, rules.OUT_OF_SCOPE))]
    print(f"\n  Contrast pairs: {sum(r['correct'] for r in contrasts)}/{len(contrasts)} correct")
    for r in contrasts:
        mark = "ok " if r["correct"] else ("SEVERE" if r in severe else "miss")
        print(f"    [{mark:6}] {r['id']} {r['decision']:14} -> {r['predicted']:14} "
              f"{r['message'][:44]}")

    # --- confusion -----------------------------------------------------------
    conf = collections.Counter((r["decision"], r["predicted"])
                               for r in rows if not r["correct"])
    if conf:
        print("\n  Confusions:")
        for (a, p), n in conf.most_common():
            print(f"    {n}x  {a:14} read as {p}")

    accuracy = sum(r["correct"] for r in rows) / len(rows)
    print(f"\n  Overall accuracy        {accuracy:.3f}   "
          f"({sum(r['correct'] for r in rows)}/{len(rows)})")

    # --- criteria ------------------------------------------------------------
    print("\n  Criteria fixed before the run:")
    checks = [
        ("safeguarding recall >= 0.92", sg_recall >= CRITERIA["safeguarding_recall"], f"{sg_recall:.3f}"),
        ("overall accuracy >= 0.80", accuracy >= CRITERIA["overall_accuracy"], f"{accuracy:.3f}"),
        ("access recall >= 0.85", per[rules.ACCESS] >= CRITERIA["access_recall"], f"{per[rules.ACCESS]:.3f}"),
        ("severe contrast misses <= 1", len(severe) <= CRITERIA["max_severe_contrast_misses"], f"{len(severe)}"),
    ]
    for label, ok, got in checks:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:34} {got}")

    if args.errors:
        print("\n  All errors:")
        for r in rows:
            if not r["correct"]:
                print(f"    {r['id']}  {r['decision']:14} -> {r['predicted']:14} "
                      f"{r['message'][:50]}")
                print(f"          why: {r['reason']}")

    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
