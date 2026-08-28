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

# Load .env before anything reads os.getenv below.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv is optional
    pass

CORPUS = ROOT / "corpus"
RAW = CORPUS / "raw"
REGISTRY_CSV = CORPUS / "registry" / "source_registry.csv"

DATA = ROOT / "data"
PROCESSED = DATA / "processed"
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

#: Candidates fetched before a role preference re-ranks them. Only used when a
#: bonus is applied -- re-ranking the top 5 alone could never promote a youth
#: passage sitting at rank 8, which is where they mostly sit.
RETRIEVAL_FETCH_K = int(os.getenv("RETRIEVAL_FETCH_K", "25"))

#: Soft preference for sources written for her rather than for a clinician.
#: 0.0 is plain cosine search. Set from the sweep in scripts/eval_retrieval.py;
#: see evaluation/README.md for the trade-off it was chosen on.
ROLE_BONUS = float(os.getenv("ROLE_BONUS", "0.0"))


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


# --- generation --------------------------------------------------------------
#: One model, one role. The previous build ran five; its own ablation showed the
#: simplest safe configuration scored highest, so this one generates and nothing
#: else. Claude for the same reason it was chosen there and for one that is not
#: ours: Girl Effect's own whitepaper reports their Kenyan content writers
#: evaluating nine models on Sheng and finding Claude "by far the strongest".
MODELS: dict[str, str] = {
    "generation": os.getenv("MODEL_GENERATION", "anthropic/claude-sonnet-5"),
}

GENERATION_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.3"))
CLASSIFIER_TEMPERATURE = float(os.getenv("CLASSIFIER_TEMPERATURE", "0.0"))

#: She is on a phone, possibly on limited data. A short answer she reads beats a
#: complete one she abandons.
RESPONSE_TARGET_WORDS = int(os.getenv("RESPONSE_TARGET_WORDS", "110"))
RESPONSE_MAX_WORDS = int(os.getenv("RESPONSE_MAX_WORDS", "150"))
RESPONSE_MIN_WORDS = int(os.getenv("RESPONSE_MIN_WORDS", "12"))

#: Kiswahili measured at 2.41 tokens per word against English at 1.22 in the
#: previous build. Budgeting in English units truncated Kiswahili answers
#: mid-sentence while English ones were fine.
TOKENS_PER_WORD = float(os.getenv("TOKENS_PER_WORD", "2.5"))
GENERATION_MAX_TOKENS = int(RESPONSE_MAX_WORDS * TOKENS_PER_WORD) + 120

PROMPTS_DIR = ROOT / "src" / "prompt_files"

#: A conversational turn is a chat message, not a paragraph.
CONVERSE_MIN_TARGET_WORDS = int(os.getenv("CONVERSE_MIN_TARGET_WORDS", "20"))
CONVERSE_TARGET_WORDS = int(os.getenv("CONVERSE_TARGET_WORDS", "55"))
CONVERSE_MAX_WORDS = int(os.getenv("CONVERSE_MAX_WORDS", "60"))
CONVERSE_MIN_WORDS = int(os.getenv("CONVERSE_MIN_WORDS", "4"))
CONVERSE_MAX_TOKENS = int(CONVERSE_MAX_WORDS * TOKENS_PER_WORD) + 80
RESPONSE_MIN_TARGET_WORDS = RESPONSE_MIN_WORDS
