"""Build the corpus: PDFs -> sections -> chunks -> Chroma.

    python scripts/ingest.py --dry-run     parse, chunk, report, write JSONL
    python scripts/ingest.py               the same, then embed and index

The dry run exists because the expensive, slow and hard-to-inspect step is
embedding, and almost every ingestion mistake is visible before it. Chunk counts
per source, token distributions and section titles tell you whether extraction
worked; a vector store tells you nothing until you query it.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config
from src.rag import chunking, indexing, loaders, registry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and chunk, but do not embed or index")
    ap.add_argument("--source", help="limit to one source_id, for debugging")
    args = ap.parse_args()

    problems = registry.validate()
    if problems:
        print("Registry problems:\n  " + "\n  ".join(problems))
        return 1

    sources = [s for s in registry.indexable()
               if not args.source or s.source_id == args.source]
    if not sources:
        print(f"No source matching {args.source!r}")
        return 1

    print(f"corpus {config.CORPUS_VERSION} · {config.EMBEDDING_MODEL}")
    print(f"chunk target {config.CHUNK_TARGET_TOKENS}, max "
          f"{config.CHUNK_MAX_TOKENS}, overlap {config.CHUNK_OVERLAP_TOKENS}\n")

    header = f"{'Source':38} {'Role':18} {'Pages':>6} {'Sect':>6} {'Chunks':>7} {'Mean tok':>9}"
    print(header)
    print("-" * len(header))

    all_chunks: list[chunking.Chunk] = []
    for source in sources:
        sections = loaders.load_sections(source)
        chunks = chunking.chunk_source(source, sections)
        all_chunks.extend(chunks)

        mean = statistics.mean([c.token_count for c in chunks]) if chunks else 0
        print(f"{source.citation_tag[:38]:38} {source.document_role:18} "
              f"{source.total_pages:6} {len(sections):6} {len(chunks):7} {mean:9.1f}")

    if not all_chunks:
        print("\nNo chunks produced — extraction failed.")
        return 1

    tokens = [c.token_count for c in all_chunks]
    print("-" * len(header))
    print(f"{'TOTAL':38} {'':18} {sum(s.total_pages for s in sources):6} "
          f"{'':6} {len(all_chunks):7} {statistics.mean(tokens):9.1f}")
    print(f"\ntokens: min {min(tokens)}, median {statistics.median(tokens):.0f}, "
          f"max {max(tokens)} (cap {config.CHUNK_MAX_TOKENS})")

    over = [c for c in all_chunks if c.token_count > config.CHUNK_MAX_TOKENS]
    if over:
        print(f"WARNING: {len(over)} chunks over the cap — they will be truncated "
              f"by the encoder, which silently loses their tail.")

    written = indexing.save_chunks_jsonl(all_chunks)
    print(f"wrote {written} chunks to {config.CHUNKS_FILE}")

    if args.dry_run:
        print("\ndry run — nothing embedded.")
        return 0

    print(f"\nembedding on {indexing.resolve_device()} …")
    indexing.reset_index()
    n = indexing.index_chunks(all_chunks)
    print(f"indexed {n} chunks into {config.CHROMA_DIR}")
    print(indexing.index_stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
