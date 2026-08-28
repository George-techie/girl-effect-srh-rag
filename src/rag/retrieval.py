"""Retrieval, with an optional preference for who the source was written for.

Plain cosine search treats a 486-page clinician's handbook, a policy report and
a 17-page youth booklet as interchangeable whenever their similarity is close.
For a product a sixteen-year-old reads, they are not interchangeable — but they
are also not ranked, because for contraindications or emergency contraception
the clinical handbook genuinely is the better evidence.

So the preference is a **soft score bonus, not a filter**. Every source stays
reachable; when two passages are close, the one written for her wins. The size
of the bonus is a measured choice, not a guess — see `scripts/eval_retrieval.py
--sweep`.

Ordering, and why:

    youth_answer       written for her, in her register        full bonus
    evidence           written about her situation, for policy  half
    clinical_boundary  written for a clinician                  none

`evidence` sits in the middle rather than level with `youth_answer` because
UNFPA and WHO briefs are written for programme staff. They carry the rights and
outcomes framing the use case needs, and they are still not her voice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src import config
from src.rag import indexing


@dataclass
class Hit:
    """One retrieved passage, with both scores kept.

    `similarity` is what the encoder actually reported; `score` is what ranked
    it. Keeping them apart means a result list can always be audited for how
    much of its order came from the preference rather than from the text.
    """

    text: str
    metadata: dict[str, Any]
    similarity: float
    score: float

    @property
    def source_id(self) -> str:
        return str(self.metadata["source_id"])

    @property
    def role(self) -> str:
        return str(self.metadata["document_role"])

    @property
    def citation_tag(self) -> str:
        return str(self.metadata["citation_tag"])


def role_weights(bonus: float) -> dict[str, float]:
    return {
        config.YOUTH_ANSWER: bonus,
        config.EVIDENCE: bonus / 2,
        config.CLINICAL_BOUNDARY: 0.0,
    }


def search(
    query: str,
    *,
    k: int | None = None,
    role_bonus: float = 0.0,
    fetch_k: int | None = None,
) -> list[Hit]:
    """Top-k passages for a query.

    With `role_bonus=0` this is plain cosine search and the fetch pool is
    irrelevant. With a bonus, a wider pool is fetched first so the preference
    has something to promote — re-ranking only the top 5 could never surface a
    youth passage sitting at rank 8.
    """
    k = k or config.RETRIEVAL_TOP_K
    pool = fetch_k or (config.RETRIEVAL_FETCH_K if role_bonus else k)

    res = indexing.get_collection().query(
        query_embeddings=[indexing.embed_query(query)],
        n_results=max(pool, k),
        include=["documents", "metadatas", "distances"],
    )

    weights = role_weights(role_bonus)
    hits = [
        Hit(
            text=doc,
            metadata=meta,
            similarity=1 - dist,
            score=(1 - dist) + weights.get(str(meta["document_role"]), 0.0),
        )
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]
