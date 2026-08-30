"""Experiment 4 — clause-level retrieval on mixed-intention messages.

    python scripts/eval_mixed.py
    python scripts/eval_mixed.py --show

Every other evaluation here uses clean single-sentence questions. Girls do not
write those. They write a health question wrapped in a boyfriend, another girl's
name, a plan for school and how all of it feels, and one embedding of that
paragraph averages the lot.

Compares two ways of forming the retrieval query, on the same 15 messages:

  whole    embed the entire message as one query          (what shipped)
  clause   embed each clause separately and pool by score (the candidate)

No LLM. This measures retrieval only, which is where the failure was.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.rag import retrieval

DATA = Path(__file__).resolve().parents[1] / "evaluation" / "mixed_turns_v1.json"


def load() -> list[dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return raw["messages"]


def titles(hits) -> list[str]:
    return [h.metadata["section_title"] for h in hits]


def scores(case: dict, hits) -> tuple[bool, str | None, float]:
    """Did the wanted evidence come back, and did anything unwanted come with it."""
    found = titles(hits)
    blob = " | ".join(found).lower()
    want = any(w.lower() in blob for w in case["want"]) if case["want"] else None
    bad = next((t for t in found
                for a in case["avoid"] if a.lower() in t.lower()), None)
    top = hits[0].similarity if hits else 0.0
    return want, bad, top


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true", help="print retrieved titles")
    args = ap.parse_args()

    cases = load()
    k = config.RETRIEVAL_TOP_K
    tally = {"whole": {"want": 0, "bad": 0, "judged": 0, "top": 0.0},
             "clause": {"want": 0, "bad": 0, "judged": 0, "top": 0.0}}
    rows = []

    for case in cases:
        whole = retrieval.search(case["message"], k=k)
        clause, parts = retrieval.search_message(case["message"], k=k)

        w_want, w_bad, w_top = scores(case, whole)
        c_want, c_bad, c_top = scores(case, clause)
        rows.append((case, w_want, w_bad, w_top, c_want, c_bad, c_top,
                     len(parts), whole, clause))

        for name, want, bad, top in (("whole", w_want, w_bad, w_top),
                                     ("clause", c_want, c_bad, c_top)):
            if want is not None:
                tally[name]["judged"] += 1
                tally[name]["want"] += bool(want)
            tally[name]["bad"] += bool(bad)
            tally[name]["top"] += top

    n = len(cases)
    print("=" * 84)
    print(f"MIXED-INTENTION MESSAGES · {n} messages · top-{k}")
    print("=" * 84)
    print(f"\n  {'':34}{'whole':>10}{'clause':>10}{'delta':>9}")
    print("  " + "-" * 63)
    jw, jc = tally["whole"]["judged"], tally["clause"]["judged"]
    print(f"  {'wanted evidence retrieved':34}"
          f"{tally['whole']['want']}/{jw:<8}{tally['clause']['want']}/{jc:<8}"
          f"{tally['clause']['want'] - tally['whole']['want']:+9}")
    print(f"  {'unwanted passage pulled in':34}"
          f"{tally['whole']['bad']:>10}{tally['clause']['bad']:>10}"
          f"{tally['clause']['bad'] - tally['whole']['bad']:+9}")
    print(f"  {'mean top similarity':34}"
          f"{tally['whole']['top'] / n:>10.3f}{tally['clause']['top'] / n:>10.3f}"
          f"{(tally['clause']['top'] - tally['whole']['top']) / n:+9.3f}")

    print("\n  Adoption criteria, fixed before the run:")
    gained = tally["clause"]["want"] - tally["whole"]["want"]
    fewer_bad = tally["clause"]["bad"] <= tally["whole"]["bad"]
    for label, ok, got in [
        ("A more wanted evidence retrieved", gained > 0,
         f"{tally['whole']['want']} -> {tally['clause']['want']} of {jw}"),
        ("B no more unwanted passages", fewer_bad,
         f"{tally['whole']['bad']} -> {tally['clause']['bad']}"),
        ("C the emotional control stays clean",
         not scores(cases[-1], rows[-1][9])[1], "M15"),
    ]:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:36} {got}")

    print(f"\n  {'id':6}{'clauses':>8}  {'whole':>18}  {'clause':>18}")
    print("  " + "-" * 74)
    for case, w_want, w_bad, w_top, c_want, c_bad, c_top, nparts, wh, cl in rows:
        def mark(want, bad):
            if want is None:
                return "  n/a" + ("  BAD" if bad else "")
            return ("  hit" if want else " MISS") + ("  BAD" if bad else "")
        print(f"  {case['id']:6}{nparts:>8}  {w_top:8.3f}{mark(w_want, w_bad):>10}"
              f"  {c_top:8.3f}{mark(c_want, c_bad):>10}   {case['category'][:30]}")

    if args.show:
        for case, *_rest, wh, cl in rows:
            print(f"\n  {case['id']}  {case['message'][:76]}")
            print("     whole :", " | ".join(t[:30] for t in titles(wh)[:3]))
            print("     clause:", " | ".join(t[:30] for t in titles(cl)[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
