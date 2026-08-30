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

import os
from dataclasses import dataclass
from typing import Any

from src import config
from src.rag import indexing, query_prep


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


#: Below this similarity the encoder has found nothing, not something weak.
#: Set from the observed noise band rather than swept: the purely emotional
#: control message tops out at 0.540 and genuine evidence sits at 0.57-0.71.
EVIDENCE_FLOOR = float(os.getenv("EVIDENCE_FLOOR", "0.55"))


def search_message(message: str, *, k: int | None = None,
                   role_bonus: float = 0.0) -> tuple[list[Hit], list[str]]:
    """Retrieve for a whole message by searching each clause separately.

    A girl sends a message, not a query, and the message often carries several
    intentions at once: a pill myth, her body, her boyfriend, another girl's
    name, and how all of it makes her feel. Embedded as one vector those average
    out, and the emotional material wins because there is more of it. Measured
    on a real message, the whole-paragraph query returned passages about mood and
    sex drive at 0.561 while the passage that answers her -- *"Do COCs cause
    women to gain or lose a lot of weight?"* -- was nowhere in the top five.

    So each clause is searched on its own and the results are pooled. **No
    clause is classified and no word list decides which one is the health
    question** -- the similarity scores do that, which is the whole point. A
    clause about Shasha retrieves nothing above the noise and loses; a clause
    about pills retrieves the pill passage and wins.

    Returns the hits and the clauses that were searched, so a trace can show
    which part of her message the evidence came from.

    **Retrieval only.** The generator still receives her entire message. The
    emotional half is not dropped from the conversation, only from the query.
    """
    k = k or config.RETRIEVAL_TOP_K
    parts = query_prep.clauses(message)
    if not parts:
        return search(message, k=k, role_bonus=role_bonus), [message]

    # The whole message stays in the pool. If it happens to be the best query,
    # nothing is lost by splitting -- which is what makes this safe to always do.
    pooled: dict[str, Hit] = {}
    for part in [message, *parts]:
        hits = search(part, k=k, role_bonus=role_bonus)
        # A clause whose best match sits in the noise band has no evidence in
        # this corpus, and its hits must not fill seats in the pool. Measured:
        # the purely emotional control message tops out at 0.540, and the
        # passage "I was raped and I am worried that no one will believe me"
        # is a strong attractor for any distressed text -- it was arriving at
        # 0.538-0.565 beside a question about the pill. Dropping the clause
        # rather than the passage is the right cut, because the passage is fine
        # and the clause is what had nothing to ask.
        if not hits or hits[0].similarity < EVIDENCE_FLOOR:
            continue
        for hit in hits:
            if hit.similarity < EVIDENCE_FLOOR:
                continue
            key = f"{hit.metadata.get('citation_tag')}#{hit.text[:60]}"
            if key not in pooled or hit.score > pooled[key].score:
                pooled[key] = hit

    ranked = sorted(pooled.values(), key=lambda h: h.score, reverse=True)
    # Returning fewer than k is a real answer. The grounded contract then
    # declines to cite thin evidence, which is the behaviour it already has.
    return ranked[:k], parts
