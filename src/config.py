"""Settings for the refined SRH corpus.

Deliberately small. The previous build's config carried model profiles, judge
thresholds, response budgets and tracing modes; none of that belongs in an
ingestion layer, and this file stops at what turns eight PDFs into a searchable
index.

Chunking defaults are carried over from the previous project's 12-configuration
sweep, which found Hit@5 flat from 400-650 tokens and no benefit from overlap.
That sweep ran on a different corpus -- mostly narrative guides, where this one
is heavily question-and-answer -- so these are a sensible starting point rather
than a validated setting for this corpus. Re-earn them on the new question set
before quoting them as evidence.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORPUS = ROOT / "corpus"
RAW = CORPUS / "raw"
REGISTRY_CSV = CORPUS / "registry" / "source_registry.csv"

PROCESSED = ROOT / "data" / "processed"
CHUNKS_FILE = PROCESSED / "chunks.jsonl"

CORPUS_VERSION = os.getenv("CORPUS_VERSION", "2026-08-28-srh-v1")

# --- content categories ------------------------------------------------------
# Broad and few on purpose. Six labels a person can hold in their head, not a
# taxonomy that needs a document to explain it.
CONTRACEPTION = "contraception"
HIV_STI = "hiv_sti"
SAFETY_RELATIONSHIPS = "safety_relationships"
YOUNG_PARENTHOOD = "young_parenthood"
EMPOWERMENT = "empowerment"
SRHR_RIGHTS = "srhr_rights"

DOMAINS = (
    CONTRACEPTION,
    HIV_STI,
    SAFETY_RELATIONSHIPS,
    YOUNG_PARENTHOOD,
    EMPOWERMENT,
    SRHR_RIGHTS,
)

# --- document roles ----------------------------------------------------------
# The one governance distinction kept from the previous build, because it earned
# its place there and matters more here.
#
# Two of the eight sources are provider guidance: a 486-page WHO handbook whose
# title says "for providers", and Kenya's national service-delivery guidelines.
# They belong in the corpus -- they are the authority on what is true and on what
# Kenyan practice actually is -- but a sixteen-year-old asking "can this make me
# infertile" should be answered from the youth Q&A, not from a dosing table.
#
# Task 1 only stores the role. Nothing filters on it yet; that decision belongs
# after retrieval evaluation, not before it.
YOUTH_ANSWER = "youth_answer"          # written for young people, in their register
EVIDENCE = "evidence"                  # rights and outcomes framing
CLINICAL_BOUNDARY = "clinical_boundary"  # provider guidance; when to seek care

DOCUMENT_ROLES = (YOUTH_ANSWER, EVIDENCE, CLINICAL_BOUNDARY)

# --- embeddings --------------------------------------------------------------
#: BAAI/bge-m3, run locally. Multilingual, which is the reason: the audience
#: code-switches, and the corpus and the query both stay on the machine.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "auto")

#: bge-m3 needs no instruction prefix. E5 models do, so the check stays.
EMBEDDING_QUERY_PREFIX = "query: " if "e5" in EMBEDDING_MODEL.lower() else ""
EMBEDDING_PASSAGE_PREFIX = "passage: " if "e5" in EMBEDDING_MODEL.lower() else ""


def _index_slug(model: str) -> str:
    return model.replace("/", "__")


CHROMA_DIR = PROCESSED / "chroma" / _index_slug(EMBEDDING_MODEL)
COLLECTION = os.getenv("COLLECTION", "girl_effect_srh_corpus")

# --- chunking ----------------------------------------------------------------
CHUNK_TARGET_TOKENS = int(os.getenv("CHUNK_TARGET_TOKENS", "500"))
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", "650"))
CHUNK_MIN_TOKENS = int(os.getenv("CHUNK_MIN_TOKENS", "60"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "0"))

# --- retrieval ---------------------------------------------------------------
#: One query, cosine, top 5. No threshold, no reranking, no hybrid search --
#: those are only worth adding if evaluation shows this baseline failing.
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))


def describe() -> dict[str, object]:
    return {
        "corpus_version": CORPUS_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_device": EMBEDDING_DEVICE,
        "collection": COLLECTION,
        "chroma_dir": str(CHROMA_DIR),
        "chunk_target": CHUNK_TARGET_TOKENS,
        "chunk_max": CHUNK_MAX_TOKENS,
        "chunk_overlap": CHUNK_OVERLAP_TOKENS,
    }
