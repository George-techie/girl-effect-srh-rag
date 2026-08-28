"""Vector index over the approved corpus.

Embeddings run locally via sentence-transformers. This is partly a constraint —
OpenRouter has no embeddings endpoint — and partly a deliberate privacy choice:
retrieval happens entirely on-device, so a user's question only leaves the
machine at the generation step, and only after the safety layers have cleared it.

Chroma is used for the store because the workload is small (low thousands of
chunks) and the feature that actually matters here is metadata filtering, which
is what enforces domain routing and document-role separation at query time.
"""

from __future__ import annotations

import json
import shutil
import time
from typing import Any, Iterable, Sequence

import chromadb
from chromadb.config import Settings

from src import config
from src.rag.chunking import Chunk

COLLECTION_NAME = config.COLLECTION

_embedder = None


def resolve_device() -> str:
    """Pick the compute device, honouring an explicit override.

    `EMBEDDING_DEVICE=auto` prefers CUDA when it is genuinely available, which
    is the difference between a 19-minute and a sub-minute index rebuild.
    """
    requested = config.EMBEDDING_DEVICE.lower()
    if requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def get_embedder():
    """Load the sentence-transformers model once per process."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        device = resolve_device()
        _embedder = SentenceTransformer(config.EMBEDDING_MODEL, device=device)

        if device.startswith("cuda"):
            # bge-m3 is 568M parameters; at fp32 it and its activations do not
            # leave room on a 4GB card once sequences get long. fp16 halves the
            # weights and is standard for embedding inference.
            _embedder = _embedder.half()
    return _embedder


def _batch_size_for(device: str) -> int:
    """Conservative batches on GPU — long sequences dominate memory, not count."""
    return 8 if device.startswith("cuda") else 16


def embed_passages(texts: Sequence[str], batch_size: int | None = None) -> list[list[float]]:
    model = get_embedder()
    device = resolve_device()
    prefixed = [config.EMBEDDING_PASSAGE_PREFIX + t for t in texts]
    vectors = model.encode(
        prefixed,
        batch_size=batch_size or _batch_size_for(device),
        normalize_embeddings=True,
        show_progress_bar=len(prefixed) > 200,
        convert_to_numpy=True,
    )
    # fp16 vectors must be widened before Chroma stores them as float64.
    return [[float(x) for x in row] for row in vectors]


def embed_query(text: str) -> list[float]:
    model = get_embedder()
    vector = model.encode(
        config.EMBEDDING_QUERY_PREFIX + text,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return vector.tolist()


def get_client() -> chromadb.ClientAPI:
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(config.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )


def get_collection(create: bool = False):
    client = get_client()
    if create:
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            # Cosine matches the normalised embeddings produced above.
            metadata={"hnsw:space": "cosine"},
        )
    return client.get_collection(name=COLLECTION_NAME)


def reset_index() -> None:
    """Delete the persisted index so a re-ingest starts clean.

    Windows will not unlink a file another process has open, and a running
    Streamlit session holds the index. Dropping the collection through the API
    is tried first because it works regardless of file handles; the directory
    removal is a fallback for a corrupt or half-written store.
    """
    if not config.CHROMA_DIR.exists():
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        return

    client = get_client()
    existing = {getattr(c, "name", c) for c in client.list_collections()}
    if COLLECTION_NAME not in existing:
        # Nothing indexed yet, so there is nothing to reset -- and returning
        # here is what makes a first ingest work at all on Windows. Opening the
        # client above creates chroma.sqlite3, and the handle this process now
        # holds blocks the rmtree fallback below, so a *fresh* directory could
        # never be reset: every first run died on PermissionError.
        return

    try:
        client.delete_collection(COLLECTION_NAME)
        return
    except Exception:  # noqa: BLE001 - fall back to removing the directory
        pass

    for attempt in range(3):
        try:
            shutil.rmtree(config.CHROMA_DIR)
            break
        except PermissionError as exc:
            if attempt == 2:
                raise PermissionError(
                    f"Cannot rebuild the index: {exc.filename} is locked by "
                    "another process. Stop any running Streamlit app "
                    "(`app.py`) or Python session holding the index, then "
                    "retry."
                ) from exc
            time.sleep(1.0)

    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def index_chunks(chunks: Sequence[Chunk], batch_size: int = 64) -> int:
    """Embed and store chunks. Returns the number indexed."""
    if not chunks:
        return 0

    collection = get_collection(create=True)
    total = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        collection.add(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            embeddings=embed_passages([c.text for c in batch]),
            metadatas=[c.metadata() for c in batch],
        )
        total += len(batch)
    return total


def save_chunks_jsonl(chunks: Iterable[Chunk], path=None) -> int:
    """Write chunks to disk so they can be inspected without the vector store."""
    target = path or config.CHUNKS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            record = chunk.metadata()
            record["text"] = chunk.text
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def index_stats() -> dict[str, Any]:
    """Per-source and per-domain counts, for the ingestion report."""
    try:
        collection = get_collection()
    except Exception:
        return {"indexed": False}

    got = collection.get(include=["metadatas"])
    metadatas = got.get("metadatas") or []

    by_source: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_role: dict[str, int] = {}
    tokens = 0

    for meta in metadatas:
        by_source[meta.get("source_id", "?")] = by_source.get(meta.get("source_id", "?"), 0) + 1
        by_role[meta.get("document_role", "?")] = by_role.get(meta.get("document_role", "?"), 0) + 1
        for domain in str(meta.get("domains", "")).split("|"):
            if domain:
                by_domain[domain] = by_domain.get(domain, 0) + 1
        tokens += int(meta.get("token_count", 0) or 0)

    return {
        "indexed": True,
        "total_chunks": len(metadatas),
        "total_tokens": tokens,
        "mean_tokens": round(tokens / len(metadatas), 1) if metadatas else 0,
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "by_domain": dict(sorted(by_domain.items(), key=lambda kv: -kv[1])),
        "by_document_role": by_role,
    }
