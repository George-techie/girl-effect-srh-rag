"""Multi-turn evaluation: does a turn survive being asked in a conversation?

    python scripts/eval_multiturn.py
    python scripts/eval_multiturn.py --show-passages

Every other evaluation in this repo scores questions asked cold, one at a time.
A girl does not do that. She moves -- contraception, what she wants to be,
something he said, where she can actually go -- and the turns that carry the
conversation are the shortest ones: *"and does it hurt?"*, *"is it free?"*.

This replays whole journeys and scores each turn twice: once as the system saw
it before (message alone) and once with the conversation available. No LLM --
this measures routing and retrieval, which is where the failure was.

The expected-path labels are written per turn *in the context of the journey*,
which is the only place they mean anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, conversation as conv
from src.decision import rules
from src.rag import query_prep, retrieval

JOURNEYS = Path(__file__).resolve().parents[1] / "evaluation" / "journeys_v1.json"


def load() -> list[dict]:
    data = json.loads(JOURNEYS.read_text(encoding="utf-8"))
    return [j for j in data["journeys"] if not j["id"].startswith("_")]


def run_turn(message: str, conversation: conv.Conversation | None) -> dict:
    """One turn, deterministically. Mirrors the pipeline's order exactly."""
    decision = rules.decide(message)
    resolved = conv.resolve(message, conversation,
                            retrieves=decision.retrieves)
    prepared = query_prep.prepare(resolved.text, restate=decision.restate)

    hits = []
    if decision.path not in (rules.OUT_OF_SCOPE, rules.CHAT, rules.SAFEGUARDING):
        hits = retrieval.search(prepared.text, k=config.RETRIEVAL_TOP_K)

    return {
        "path": decision.path,
        "resolved": resolved.resolved,
        "antecedent": resolved.antecedent,
        "query": prepared.text,
        "top_section": hits[0].metadata["section_title"] if hits else None,
        "top_tag": hits[0].metadata["citation_tag"] if hits else None,
        "top_sim": round(hits[0].similarity, 3) if hits else None,
        "sections": [h.metadata["section_title"] for h in hits],
    }


def replay(journey: dict, with_context: bool) -> list[dict]:
    conversation = conv.Conversation() if with_context else None
    rows = []
    for turn in journey["turns"]:
        result = run_turn(turn["message"], conversation)
        if conversation is not None:
            conversation.record_her(turn["message"], result["path"])
            conversation.record_aunti("(reply)", result["path"])
        rows.append({**turn, **result})
    return rows


def forbidden_hit(row: dict) -> str | None:
    """Did a passage the turn must not be answered from come back at all?

    Not a stylistic check. "and does it hurt?" answered from the female
    sterilization passage is a 15-year-old being told about a permanent
    procedure she did not ask about and cannot undo.
    """
    for phrase in row.get("must_not_retrieve", []):
        for section in row["sections"]:
            if phrase.lower() in section.lower():
                return section
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show-passages", action="store_true")
    args = ap.parse_args()

    journeys = load()
    totals = {"turns": 0, "path_alone": 0, "path_ctx": 0,
              "forbidden_alone": 0, "forbidden_ctx": 0, "resolved": 0}

    for journey in journeys:
        alone = replay(journey, with_context=False)
        ctx = replay(journey, with_context=True)

        print("\n" + "=" * 88)
        print(f"{journey['id']} — {journey['description']}")
        print("=" * 88)

        for a, c in zip(alone, ctx):
            totals["turns"] += 1
            ok_a = a["path"] == c["expected_path"]
            ok_c = c["path"] == c["expected_path"]
            totals["path_alone"] += ok_a
            totals["path_ctx"] += ok_c
            totals["resolved"] += c["resolved"]

            bad_a, bad_c = forbidden_hit(a), forbidden_hit(c)
            totals["forbidden_alone"] += bool(bad_a)
            totals["forbidden_ctx"] += bool(bad_c)

            flag = "" if ok_c else "   <-- WRONG PATH"
            print(f"\n  She: {c['message']}")
            print(f"       expected {c['expected_path']:14} "
                  f"alone -> {a['path']:14} with context -> {c['path']:14}{flag}")
            if c["resolved"]:
                print(f"       resolved against: \"{c['antecedent'][:58]}\"")
            if a["top_section"] or c["top_section"]:
                mark_a = "  !! FORBIDDEN" if bad_a else ""
                mark_c = "  !! FORBIDDEN" if bad_c else ""
                print(f"       alone   {a['top_sim']}  {str(a['top_section'])[:46]}{mark_a}")
                print(f"       context {c['top_sim']}  {str(c['top_section'])[:46]}{mark_c}")
            if args.show_passages and c["sections"]:
                for s in c["sections"]:
                    print(f"            · {s[:70]}")

    n = totals["turns"]
    print("\n" + "=" * 88)
    print(f"ACROSS {len(journeys)} JOURNEYS, {n} TURNS")
    print("=" * 88)
    print(f"  correct path      alone {totals['path_alone']}/{n} "
          f"({totals['path_alone']/n:.3f})     "
          f"with context {totals['path_ctx']}/{n} ({totals['path_ctx']/n:.3f})")
    print(f"  forbidden passage alone {totals['forbidden_alone']}/{n}"
          f"                with context {totals['forbidden_ctx']}/{n}")
    print(f"  turns resolved against an antecedent: {totals['resolved']}/{n}")

    print("\n  Criteria fixed before the run:")
    for label, ok, got in [
        ("1 no forbidden passage retrieved", totals["forbidden_ctx"] == 0,
         f"{totals['forbidden_ctx']}"),
        ("2 path accuracy >= 0.95 with context",
         totals["path_ctx"] / n >= 0.95, f"{totals['path_ctx']/n:.3f}"),
        ("3 context is never worse than alone",
         totals["path_ctx"] >= totals["path_alone"]
         and totals["forbidden_ctx"] <= totals["forbidden_alone"],
         f"path {totals['path_alone']}->{totals['path_ctx']}, "
         f"forbidden {totals['forbidden_alone']}->{totals['forbidden_ctx']}"),
    ]:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:40} {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
