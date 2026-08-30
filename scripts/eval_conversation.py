"""Experiment 5 — conversation quality, scored without a judge.

    python scripts/eval_conversation.py
    python scripts/eval_conversation.py --show      # print every reply

Replays whole journeys through the real pipeline and scores each reply against
the properties this build has committed to. **This costs model calls.** Roughly
one or two per turn on the turns that reach a model; safeguarding turns cost
nothing.

**Why there is no LLM judge here.** The previous build had one and it refused a
girl's compliment. Twice. Everything below is a property we defined and can
check by reading the text, which means the score means the same thing on every
run and a reviewer can verify any single row by hand. Warmth is not on the list,
because we cannot measure it honestly and pretending otherwise would be worse
than admitting the gap.

The metrics, and what each one is protecting:

  grounded turns citing     every health claim traceable to a passage
  register match            she wrote in Sheng and was answered in Sheng
  continuity                the reply gives her somewhere to go next
  no standing offer         "I'm here if you want to talk" is not a follow-up
  no deferral               it does not offer to look up what it is holding
  no machinery talk         she never hears the word "passage"
  answered                  she got something usable, not a refusal
  safeguarding tier         urgent gets contacts, a concern gets an offer
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import pipeline
from src.conversation import Conversation
from src.language import detect
from src.safety import checks, responses

ROOT = Path(__file__).resolve().parents[1]
JOURNEYS = ROOT / "evaluation" / "journeys_v1.json"

#: Passive closers. Warm, and they hand the conversation back to her.
STANDING_OFFER = re.compile(
    r"\b(i'?m|i am) (here|listening)\b"
    r"|\bwhenever you'?re ready\b|\bwhen you'?re ready\b"
    r"|\bif you (ever )?want to talk\b|\bfeel free to\b"
    r"|\bwe can talk about (anything|whatever)\b",
    re.IGNORECASE,
)

#: A menu handed back to her instead of a thread followed.
MENU = re.compile(
    r"\bwhich (one|of (these|them))\b.{0,40}\b(want|like|prefer)\b"
    r"|\bwould you (like|prefer) (to hear about )?(the )?\w+ or\b",
    re.IGNORECASE,
)

REFUSALS = {responses.BLOCKED, responses.NO_EVIDENCE, responses.TECHNICAL}

#: Turns where a closing question would be wrong, not missing.
CLOSING = re.compile(r"^\s*(thanks|thank you|asante|bye|goodbye|kwaheri)\b",
                     re.IGNORECASE)


def ends_with_question(text: str) -> bool:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return bool(lines) and lines[-1].rstrip().endswith("?")


def register_of(text: str) -> str:
    return detect.detect(text)


def score_turn(message: str, reply, *, k: int) -> dict:
    text = reply.text
    trace = reply.trace
    grounded = trace.get("contract") == "grounded"
    her = register_of(message)
    mine = register_of(text)

    return {
        "path": reply.path,
        "grounded": grounded,
        "cited": bool(reply.sources) if grounded else None,
        # A code-switched message should not come back in flat English. English
        # in, English out is also a match.
        "register_match": (
            None if her in (detect.UNKNOWN,) else
            (mine != detect.KENYAN_ENGLISH) if her != detect.KENYAN_ENGLISH
            else True
        ),
        "her_register": her,
        "my_register": mine,
        "continuity": (
            None if CLOSING.match(message) else ends_with_question(text)
        ),
        # A standing offer is only a failure when she is still in the
        # conversation. When she has just said thanks or goodbye, a warm closer
        # is the correct ending and a question would be pestering -- the same
        # distinction the persona rule makes.
        "standing_offer": (
            None if CLOSING.match(message)
            else bool(STANDING_OFFER.search(text))
        ),
        "menu": bool(MENU.search(text)),
        "deferral": bool(checks.DEFERRAL.search(text)) if grounded else False,
        "machinery": bool(checks.MACHINERY.search(text)),
        "dashes": len(checks.DASH.findall(text)),
        "answered": text not in REFUSALS,
        "llm_calls": trace.get("llm_calls", 0),
        "latency_ms": trace.get("latency_ms", 0),
        "tier": trace.get("tier"),
        "services": trace.get("services"),
    }


def rate(rows: list[dict], key: str) -> tuple[int, int]:
    judged = [r for r in rows if r.get(key) is not None]
    return sum(bool(r[key]) for r in judged), len(judged)


def pct(hit: int, total: int) -> str:
    return f"{hit}/{total}  {hit / total:.0%}" if total else "     n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--journeys", type=Path, default=JOURNEYS)
    ap.add_argument("--include-mixed", action="store_true",
                    help="also score the mixed-intention messages as one-turn "
                         "conversations, for a larger sample")
    args = ap.parse_args()

    data = json.loads(args.journeys.read_text(encoding="utf-8"))
    journeys = [j for j in data["journeys"] if not j["id"].startswith("_")]

    if args.include_mixed:
        # Real messy messages, scored one at a time. A journey of length one is
        # still a conversation as far as every metric here is concerned, and it
        # widens the sample where it is thinnest: mixed intention.
        mixed = json.loads(
            (ROOT / "evaluation" / "mixed_turns_v1.json").read_text(
                encoding="utf-8"))["messages"]
        journeys += [{"id": m["id"], "description": m["category"],
                      "turns": [{"message": m["message"]}]} for m in mixed]

    rows: list[dict] = []
    for journey in journeys:
        conversation = Conversation()
        if args.show:
            print("\n" + "=" * 84)
            print(f"{journey['id']} — {journey['description']}")
        for turn in journey["turns"]:
            reply = pipeline.answer(turn["message"], conversation=conversation)
            row = score_turn(turn["message"], reply, k=5)
            row["journey"] = journey["id"]
            row["message"] = turn["message"]
            rows.append(row)
            if args.show:
                print(f"\n  SHE: {turn['message']}")
                print(f"  [{row['path']} · {row['her_register']} -> "
                      f"{row['my_register']} · {row['llm_calls']} call(s)]")
                print(f"  AUNTI: {reply.text}")

    n = len(rows)
    print("\n" + "=" * 84)
    print(f"CONVERSATION QUALITY · {len(journeys)} journeys · {n} turns")
    print("=" * 84)

    print("\n  GROUNDING")
    print(f"    {'grounded turns that cite a source':38}"
          f"{pct(*rate(rows, 'cited'))}")
    print(f"    {'turns that reached the corpus':38}"
          f"{sum(1 for r in rows if r['grounded'])}/{n}")

    print("\n  HER LANGUAGE")
    print(f"    {'reply matches her register':38}"
          f"{pct(*rate(rows, 'register_match'))}")
    switched = [r for r in rows if r["her_register"] != detect.KENYAN_ENGLISH]
    if switched:
        ok = sum(1 for r in switched if r["register_match"])
        print(f"    {'  of the code-switched turns':38}{ok}/{len(switched)}")

    print("\n  CONVERSATION")
    print(f"    {'gives her somewhere to go next':38}"
          f"{pct(*rate(rows, 'continuity'))}")
    so_hit, so_n = rate(rows, "standing_offer")
    print(f"    {'free of a passive standing offer':38}"
          f"{pct(so_n - so_hit, so_n)}")
    print(f"    {'free of a menu handed back to her':38}"
          f"{pct(n - sum(r['menu'] for r in rows), n)}")

    print("\n  REGISTER DISCIPLINE")
    for label, key in [("free of machinery talk", "machinery"),
                       ("free of a deferral", "deferral")]:
        print(f"    {label:38}{pct(n - sum(r[key] for r in rows), n)}")
    dashes = sum(r["dashes"] for r in rows)
    print(f"    {'dashes used as punctuation':38}{dashes} across {n} turns")

    print("\n  DID SHE GET AN ANSWER")
    print(f"    {'usable reply':38}{pct(*rate(rows, 'answered'))}")

    print("\n  SAFEGUARDING")
    safe = [r for r in rows if r["path"] == "safeguarding"]
    if safe:
        with_services = sum(1 for r in safe if isinstance(r["services"], list))
        print(f"    {'safeguarding turns':38}{len(safe)}")
        print(f"    {'  reached verified services':38}"
              f"{with_services}/{len(safe)}")
        print(f"    {'  needed no model call':38}"
              f"{sum(1 for r in safe if not r['llm_calls'])}/{len(safe)}")

    print("\n  COST AND SPEED")
    calls = sum(r["llm_calls"] for r in rows)
    lats = [r["latency_ms"] for r in rows if r["latency_ms"]]
    # The first turn that touches the encoder pays for loading it. The app warms
    # it at startup so a girl never does; reporting it here would measure the
    # harness rather than the service.
    warm = sorted(lats)[:-1] if len(lats) > 2 else lats
    print(f"    {'model calls':38}{calls}  ({calls / n:.2f} per turn)")
    print(f"    {'turns needing no model at all':38}"
          f"{pct(sum(1 for r in rows if not r['llm_calls']), n)}")
    if lats:
        print(f"    {'median latency':38}{statistics.median(warm):.0f} ms")
        print(f"    {'slowest warm turn':38}{max(warm):.0f} ms")
        print(f"    {'cold encoder load (excluded)':38}{max(lats):.0f} ms"
              "   warmed at app startup")

    print("\n  Not measured here, on purpose: whether the reply is warm, kind or")
    print("  well judged. Those need a person. The previous build used an LLM")
    print("  judge for them and it refused a girl's compliment, twice.")

    failures = [r for r in rows
                if r["standing_offer"] is True or r["menu"] or r["deferral"]
                or r["machinery"] or not r["answered"]
                or (r["cited"] is False)]
    if failures:
        print(f"\n  {len(failures)} turn(s) failed at least one check")
        for r in failures:
            flags = [f for f, on in [
                ("no citation", r["cited"] is False),
                ("standing offer", r["standing_offer"] is True),
                ("menu", r["menu"]), ("deferral", r["deferral"]),
                ("machinery", r["machinery"]), ("refused", not r["answered"]),
            ] if on]
            print(f"    {r['journey']:20} {', '.join(flags):34} "
                  f"{r['message'][:34]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
