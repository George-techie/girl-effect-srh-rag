"""Tokens, calls and cost per turn — the numbers an engineering lead budgets on.

    python scripts/eval_cost.py

Runs the decision benchmark's 52 messages through the whole pipeline and reports
what they actually consumed. **This costs money.** It is the only evaluation
here that does, on purpose: everything else is deterministic.

Comparable by construction with the previous build's recorded runs, which used
51 cases and the same price table. The scope and corpus differ, so the honest
comparison is the shape of the cost -- calls and tokens per turn -- rather than
a claim that the same questions got cheaper.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import pipeline
from src.conversation import Conversation
from src.llm.client import call_log

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "decisions_v1.jsonl"

#: OpenRouter list prices, USD per million tokens (input, output). The same
#: table the previous build priced its runs with, so the two are comparable.
PRICE = {
    "anthropic/claude-sonnet-5": (2.00, 10.00),
    "openai/gpt-5.4-mini": (0.75, 4.50),
}

#: The previous build's own recorded runs, 4 August 2026, 51 cases each.
#: evaluation/results/three_system_v2.json and system_bplus.json.
PREVIOUS = {
    "A  no safeguarding layer": (0.98, 200828, None),
    "B  safeguarding, no judge": (2.65, 196272, None),
    "C  plus evidence judge": (3.53, 348749, None),
    "B+ full, five model roles": (3.78, 438535, 0.9658),
}
PREVIOUS_CASES = 51


def main() -> int:
    rows = [json.loads(l) for l in DATASET.open(encoding="utf-8") if l.strip()]
    print(f"Running {len(rows)} messages through the full pipeline...\n")

    latencies = []
    for i, row in enumerate(rows, 1):
        reply = pipeline.answer(row["message"], conversation=Conversation())
        latencies.append(reply.trace.get("latency_ms", 0))
        print(f"\r  {i}/{len(rows)}", end="", flush=True)
    print("\n")

    # Priced per call, because each call knows its own model.
    calls = len(call_log.calls)
    prompt = sum(c.prompt_tokens for c in call_log.calls)
    completion = sum(c.completion_tokens for c in call_log.calls)
    total = prompt + completion

    cost = 0.0
    for call in call_log.calls:
        pin, pout = PRICE.get(call.model, PRICE["anthropic/claude-sonnet-5"])
        cost += call.prompt_tokens / 1e6 * pin
        cost += call.completion_tokens / 1e6 * pout

    by_role: dict[str, int] = {}
    for call in call_log.calls:
        by_role[call.role] = by_role.get(call.role, 0) + 1

    n = len(rows)
    print("=" * 78)
    print(f"COST AND CONSUMPTION · {n} messages · full pipeline")
    print("=" * 78)
    print(f"\n  {'model calls':32}{calls:>10}   {calls / n:.2f} per turn")
    print(f"  {'turns needing no model':32}"
          f"{sum(1 for l in latencies if l == 0):>10}")
    print(f"  {'prompt tokens':32}{prompt:>10,}")
    print(f"  {'completion tokens':32}{completion:>10,}")
    print(f"  {'total tokens':32}{total:>10,}   {total / n:,.0f} per turn")
    print(f"  {'cost':32}{'$' + format(cost, '.4f'):>10}   "
          f"${cost / n:.4f} per turn")
    warm = sorted(latencies)[:-1] if len(latencies) > 2 else latencies
    print(f"  {'median latency':32}{statistics.median(warm):>10,.0f} ms")
    if by_role:
        roles = ", ".join(f"{r} {c}" for r, c in sorted(by_role.items()))
        print(f"\n  calls by role: {roles}")

    print("\n" + "=" * 78)
    print("AGAINST THE PREVIOUS BUILD")
    print(f"(its own recorded runs, {PREVIOUS_CASES} cases, same price table)")
    print("=" * 78)
    print(f"\n  {'configuration':30}{'calls/turn':>12}{'tokens':>12}"
          f"{'tokens/turn':>13}{'cost':>10}")
    print("  " + "-" * 75)
    for label, (c, t, usd) in PREVIOUS.items():
        money = f"${usd:.4f}" if usd else "-"
        print(f"  {label:30}{c:>12.2f}{t:>12,}{t / PREVIOUS_CASES:>13,.0f}"
              f"{money:>10}")
    print(f"  {'THIS BUILD':30}{calls / n:>12.2f}{total:>12,}"
          f"{total / n:>13,.0f}{'$' + format(cost, '.4f'):>10}")

    b_plus_calls, b_plus_tokens, b_plus_cost = PREVIOUS["B+ full, five model roles"]
    print(f"\n  Against B+, the previous full profile:")
    print(f"    calls per turn   {b_plus_calls:.2f} -> {calls / n:.2f}"
          f"   ({b_plus_calls / max(calls / n, 0.01):.1f}x fewer)")
    print(f"    tokens per turn  {b_plus_tokens / PREVIOUS_CASES:,.0f} -> "
          f"{total / n:,.0f}")
    if b_plus_cost:
        print(f"    cost per turn    ${b_plus_cost / PREVIOUS_CASES:.4f} -> "
              f"${cost / n:.4f}")

    print("\n  Scope and corpus differ between the builds, so this is not the")
    print("  same questions getting cheaper. What it does show is the shape of")
    print("  the cost: one model call on the turns that need one, none at all")
    print("  on the turns that do not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
