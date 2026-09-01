"""Theory-of-Change journeys, end to end.

    python scripts/eval_toc.py            # score both journeys
    python scripts/eval_toc.py --show     # print every reply in full

Girl Effect's Theory of Change runs **behavioural drivers → intent → service
access → behaviour change**. Knowledge is one driver of eight, so a system can
answer every question correctly and still never move a girl toward a service.
No retrieval metric would show that. This does.

Each turn declares the stage it should reach and whether a verified contact
should be in the reply. **This costs model calls** — it runs the real pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import observability, pipeline, services
from src.conversation import Conversation
from src.safety import responses

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evaluation" / "toc_journeys_v1.json"

REFUSALS = {responses.BLOCKED, responses.NO_EVIDENCE, responses.TECHNICAL}
ALL_CONTACTS = None  # filled at run time


def contacts_in(text: str) -> list[str]:
    global ALL_CONTACTS
    if ALL_CONTACTS is None:
        ALL_CONTACTS = [s.contact for s in services._load()]
    return [c for c in ALL_CONTACTS if c in text]


def run(journey: dict, show: bool) -> list[dict]:
    conversation = Conversation()
    rows = []
    for turn in journey["turns"]:
        reply = pipeline.answer(turn["message"], conversation=conversation)
        stage = observability.STAGE.get(reply.path, "unknown")
        found = contacts_in(reply.text) + contacts_in(reply.followup or "")

        row = {
            **turn,
            "path": reply.path,
            "got_stage": stage,
            "got_contact": bool(found),
            "contacts": found,
            "cited": len(reply.sources),
            "refused": reply.text in REFUSALS,
            "calls": reply.trace.get("llm_calls", 0),
            "text": reply.text,
        }
        row["stage_ok"] = turn["stage"] in ("any", stage)
        row["contact_ok"] = row["got_contact"] == turn["expect_contact"]
        row["cite_ok"] = (not turn.get("must_cite")) or row["cited"] > 0
        rows.append(row)

        if show:
            print(f"\n  SHE: {turn['message']}")
            print(f"  [{turn['driver']} → {stage} · {reply.path} · "
                  f"{row['calls']} call(s)"
                  + (f" · {row['cited']} cited" if row["cited"] else "")
                  + (f" · contacts {found}" if found else "") + "]")
            print(f"  AUNTI: {reply.text}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    journeys = [j for j in data["journeys"] if not j["id"].startswith("_")]

    all_rows = []
    for journey in journeys:
        print("\n" + "=" * 82)
        print(f"{journey['id']} — {journey['goal']}")
        print("=" * 82)
        rows = run(journey, args.show)
        all_rows += rows

        print(f"\n  {'driver':18}{'stage reached':17}{'contact':9}{'cited':7}")
        print("  " + "-" * 62)
        for r in rows:
            flags = []
            if not r["stage_ok"]:
                flags.append(f"stage wanted {r['stage']}")
            if not r["contact_ok"]:
                flags.append("contact expected" if r["expect_contact"]
                             else "unexpected contact")
            if not r["cite_ok"]:
                flags.append("no citation")
            if r["refused"]:
                flags.append("REFUSED")
            mark = "  ".join(flags)
            print(f"  {r['driver']:18}{r['got_stage']:17}"
                  f"{('yes' if r['got_contact'] else '-'):9}"
                  f"{(str(r['cited']) if r['cited'] else '-'):7}"
                  f"{'  ' + mark if mark else ''}")

    n = len(all_rows)
    ok_stage = sum(r["stage_ok"] for r in all_rows)
    ok_contact = sum(r["contact_ok"] for r in all_rows)
    ok_cite = sum(r["cite_ok"] for r in all_rows)
    refused = sum(r["refused"] for r in all_rows)
    reached = [r for r in all_rows if r["expect_contact"] and r["got_contact"]]

    print("\n" + "=" * 82)
    print(f"ACROSS {len(journeys)} JOURNEYS, {n} TURNS")
    print("=" * 82)
    print(f"  stage reached as intended     {ok_stage}/{n}")
    print(f"  contact present when expected {ok_contact}/{n}")
    print(f"  citation when required        {ok_cite}/{n}")
    print(f"  refusals                      {refused}/{n}")
    print(f"  turns that put a real number in front of her: {len(reached)}")

    print("\n  Criteria fixed before the run:")
    for label, ok, got in [
        ("1 every journey reaches service access",
         all(any(r["got_contact"] for r in run_rows) for run_rows in
             [all_rows[:len(journeys[0]['turns'])],
              all_rows[len(journeys[0]['turns']):]]),
         f"{len(reached)} turns with contacts"),
        ("2 no refusals anywhere", refused == 0, f"{refused}"),
        ("3 contacts appear only where intended", ok_contact == n,
         f"{ok_contact}/{n}"),
        ("4 cited wherever a fact was claimed", ok_cite == n, f"{ok_cite}/{n}"),
    ]:
        print(f"    [{'PASS' if ok else 'FAIL'}]  {label:40} {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
