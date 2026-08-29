"""Read the event log and say what is wrong with the service.

    python scripts/inspect_events.py
    python scripts/inspect_events.py --violations
    python scripts/inspect_events.py --file data/events.jsonl

A dashboard nobody reads is not observability, so this prints the small number
of things that would actually change a decision, and puts anything anomalous at
the top rather than the bottom.

Three questions, in the order they matter:

  1. Is anything violating an invariant?   a component has stopped doing what
                                           its name says
  2. How often does she get nothing?       blocks, refusals, insufficient
                                           evidence -- the failure that looks
                                           like success in a latency chart
  3. Where do conversations stop?          Girl Effect's Theory of Change ends
                                           at service access, so a service where
                                           everyone asks questions and nobody
                                           reaches the service question is
                                           failing at its actual purpose
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import observability


def pct(n: int, total: int) -> str:
    return f"{n / total:6.1%}" if total else "     -"


def bar(share: float, width: int = 24) -> str:
    filled = round(share * width)
    return "#" * filled + "." * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--violations", action="store_true",
                    help="list every violating event and stop")
    args = ap.parse_args()

    events = observability.read(args.file)
    if not events:
        print(f"No events in {args.file or observability.EVENTS}.\n"
              "Run the app or an evaluation first — events are written per turn.")
        return 0

    n = len(events)

    # --- 1 · invariants ------------------------------------------------------
    violations = collections.Counter(
        name for e in events for name in e.get("violations", []))
    offenders = [e for e in events if e.get("violations")]

    print("=" * 78)
    print(f"{n} turns")
    print("=" * 78)

    if violations:
        print("\nINVARIANT VIOLATIONS — a component is not doing what its name says")
        for name, count in violations.most_common():
            print(f"  {count:5}  {pct(count, n)}  {name}")
    else:
        print("\n  No invariant violations.")

    if args.violations:
        for e in offenders:
            print(f"\n  turn {e.get('turn')} · {e['path']} · {e['violations']}")
            if "message" in e:
                print(f"    she: {e['message'][:70]}")
        return 0

    # --- 2 · does she get an answer -----------------------------------------
    blocked = sum(e["blocked"] for e in events)
    insufficient = sum(e["insufficient"] for e in events)
    errors = sum(bool(e.get("error")) for e in events)
    deflected = sum(e["path"] == "out_of_scope" for e in events)
    nothing = blocked + insufficient + errors

    print("\nDID SHE GET AN ANSWER")
    print(f"  {'blocked by the validator':32}{blocked:5}{pct(blocked, n)}")
    print(f"  {'no evidence in the corpus':32}{insufficient:5}{pct(insufficient, n)}")
    print(f"  {'provider or technical error':32}{errors:5}{pct(errors, n)}")
    print(f"  {'declined as out of scope':32}{deflected:5}{pct(deflected, n)}")
    print(f"  {'-> got nothing usable':32}{nothing:5}{pct(nothing, n)}")
    if nothing:
        print("\n  This is the number that looks fine on a latency chart. Every one")
        print("  of these turns was fast, cheap, and gave her nothing.")

    # --- 3 · where conversations go ------------------------------------------
    stages = collections.Counter(e["stage"] for e in events)
    print("\nWHERE THE TURNS GO — Theory of Change stage, not just route")
    order = ["rapport", "knowledge", "confidence", "service_access",
             "safeguarding", "deflected", "none", "unknown"]
    for stage in order:
        count = stages.get(stage, 0)
        if not count:
            continue
        print(f"  {stage:16}{count:5}{pct(count, n)}  {bar(count / n)}")

    reached = stages.get("service_access", 0)
    if not reached:
        print("\n  Nobody reached a service question. The Theory of Change ends at")
        print("  service access — a service that answers well and never gets her")
        print("  there has done the easy half.")

    # --- retrieval and context ----------------------------------------------
    grounded = [e for e in events if e.get("n_retrieved")]
    if grounded:
        sims = [e["top_similarity"] for e in grounded if e.get("top_similarity")]
        uncited = sum(1 for e in grounded if not e["n_sources"]
                      and not e["blocked"] and not e["insufficient"])
        youth = sum(1 for e in grounded if e.get("top_role") == "youth_answer")
        print("\nRETRIEVAL")
        print(f"  {'turns that searched':32}{len(grounded):5}")
        if sims:
            print(f"  {'median top similarity':32}{statistics.median(sims):5.3f}")
            weak = sum(1 for s in sims if s < 0.55)
            print(f"  {'top similarity below 0.55':32}{weak:5}{pct(weak, len(sims))}")
        print(f"  {'answered from youth material':32}{youth:5}{pct(youth, len(grounded))}")
        print(f"  {'answered citing nothing':32}{uncited:5}{pct(uncited, len(grounded))}")

    dependent = sum(e.get("dependent", False) for e in events)
    resolved = sum(e.get("resolved", False) for e in events)
    prepared = sum(e.get("query_prepared", False) for e in events)
    if dependent or prepared:
        print("\nCONVERSATION")
        print(f"  {'follow-up fragments':32}{dependent:5}{pct(dependent, n)}")
        print(f"  {'  of those, resolved':32}{resolved:5} {pct(resolved, max(dependent, 1))}")
        print(f"  {'queries given corpus vocabulary':32}{prepared:5}{pct(prepared, n)}")
        if dependent > resolved:
            print(f"\n  {dependent - resolved} fragment(s) found no antecedent and went to the")
            print("  encoder bare. That is the shape of the trimmed-topic defect.")

    # --- cost and speed ------------------------------------------------------
    calls = sum(e.get("llm_calls", 0) for e in events)
    lats = [e["latency_ms"] for e in events if e.get("latency_ms")]
    print("\nCOST AND SPEED")
    print(f"  {'model calls':32}{calls:5}   ({calls / n:.2f} per turn)")
    print(f"  {'turns needing no model at all':32}"
          f"{sum(1 for e in events if not e.get('llm_calls')):5}"
          f"{pct(sum(1 for e in events if not e.get('llm_calls')), n)}")
    if lats:
        ordered = sorted(lats)
        print(f"  {'median latency':32}{statistics.median(lats):5.0f} ms")
        print(f"  {'p95 latency':32}"
              f"{ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]:5.0f} ms")

    issues = collections.Counter(
        i.split(":")[0] for e in events for i in e.get("issues", []))
    if issues:
        print("\nNON-FATAL ISSUES — recorded and still sent")
        for name, count in issues.most_common(8):
            print(f"  {count:5}  {name[:60]}")

    if not observability.TRACE_MESSAGES:
        print("\n  Message text is not recorded. Set TRACE_MESSAGES=1 to include it")
        print("  while debugging locally — see the note in src/observability.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
