"""Retrieval inspection. No LLM anywhere in this file.

    python scripts/search.py "can contraception make me infertile"
    python scripts/search.py "condoms and HIV" -k 8 --full

The point is to be able to answer "did the corpus even contain this?" separately
from "did the model say something sensible?". Conflating those two questions is
how a retrieval problem gets fixed with prompt changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.rag import indexing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", nargs="+")
    ap.add_argument("-k", type=int, default=config.RETRIEVAL_TOP_K)
    ap.add_argument("--full", action="store_true", help="print whole chunks")
    args = ap.parse_args()

    query = " ".join(args.query)
    collection = indexing.get_collection()

    res = collection.query(
        query_embeddings=[indexing.embed_query(query)],
        n_results=args.k,
        include=["documents", "metadatas", "distances"],
    )

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]

    print(f'\n"{query}"\n{"=" * 78}')
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        # Chroma reports cosine distance; similarity is the readable direction.
        print(f"\n{i}. {meta['citation_tag']}   similarity {1 - dist:.3f}")
        print(f"   p.{meta['page_pdf']} · {meta['section_title'][:66]}")
        print(f"   {meta['document_role']} · {meta['domains']}")
        body = doc if args.full else " ".join(doc.split())[:240] + "…"
        print(f"\n   {body}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
