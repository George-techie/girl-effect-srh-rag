"""What actually entered the corpus, by source.

    python scripts/inspect_corpus.py
    python scripts/inspect_corpus.py --source KE_FAQ --sections

Reads chunks.jsonl rather than Chroma, so extraction can be checked without
embedding anything.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", help="limit to one source_id")
    ap.add_argument("--sections", action="store_true", help="list section titles")
    ap.add_argument("--sample", type=int, default=0, help="print N sample chunks")
    args = ap.parse_args()

    if not config.CHUNKS_FILE.exists():
        print(f"{config.CHUNKS_FILE} not found — run scripts/ingest.py --dry-run")
        return 1

    rows = [json.loads(line) for line in config.CHUNKS_FILE.open(encoding="utf-8")]
    if args.source:
        rows = [r for r in rows if r["source_id"] == args.source]

    by_source = collections.defaultdict(list)
    for r in rows:
        by_source[r["citation_tag"]].append(r)

    print(f"{'Source':40} {'Chunks':>7} {'Tokens':>8} {'Median':>7} {'Max':>6}")
    print("-" * 72)
    for tag, group in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        toks = [r["token_count"] for r in group]
        print(f"{tag[:40]:40} {len(group):7} {sum(toks):8} "
              f"{statistics.median(toks):7.0f} {max(toks):6}")
    toks = [r["token_count"] for r in rows]
    print("-" * 72)
    print(f"{'TOTAL':40} {len(rows):7} {sum(toks):8} "
          f"{statistics.median(toks):7.0f} {max(toks):6}")

    roles = collections.Counter(r["document_role"] for r in rows)
    print("\nby role: " + " · ".join(f"{k} {v}" for k, v in roles.most_common()))
    cats = collections.Counter(c for r in rows for c in r["domains"].split("|"))
    print("by category: " + " · ".join(f"{k} {v}" for k, v in cats.most_common()))

    if args.sections:
        print()
        for r in rows:
            print(f"  p{r['page_pdf']:>4} {r['token_count']:>4}t  {r['section_title'][:70]}")

    for r in rows[: args.sample]:
        print(f"\n--- {r['chunk_id']} · {r['citation_tag']} · p{r['page_pdf']}")
        print(r["text"][:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
