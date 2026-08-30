"""A second search, in the corpus's words, when the first one came back weak.

Experiment 3 concluded that a deterministic vocabulary table beat a model
rewriter and that a rewriter should therefore not be built. **That conclusion
was over-generalised, and this module exists because a reviewer caught it.**

The table was measured on 31 questions that were single-sentence, English, and
well formed. Real messages are none of those. Tested against phrasings the table
had not been written for, it fired on two of five, and one miss was severe:

    "nasikia sindano inakufanya unenepe"      (I hear the injection makes you fat)
        -> "I was raped and I am worried that no one will believe me"  0.538

That is not a gap a longer word list closes. Every term added is fitted to the
example in front of you, which is exactly the failure mode a word list has.

So: the table still runs first, because it is free and it works on clean
questions. This runs **only when the table's result was measurably weak**, which
keeps it rare, and it is the one place a second model call is clearly worth it.

**Why a model is safe here specifically.** It never writes anything she reads.
Its entire output is a search string. The worst case is that it retrieves the
wrong passages, and the grounded contract then refuses to cite them, which is
the behaviour that already exists for weak retrieval. A rewriter cannot invent a
fact into her answer, because it is not writing her answer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.llm.client import get_client
from src.prompt_files import loader
from src.rag import retrieval

#: Below this top similarity, the first search is treated as having failed.
#: 0.60 sits above the weak cluster that produced the miss above (0.538-0.575)
#: and below the band where deterministic retrieval was already answering
#: (0.65-0.75 on the evaluation set).
WEAK_BELOW = float(os.getenv("RESCUE_BELOW", "0.60"))

NONE = "NONE"


@dataclass
class Rescue:
    hits: list
    used: bool
    query: str | None = None
    before: float | None = None
    after: float | None = None
    error: str | None = None


def top_similarity(hits: list) -> float:
    return hits[0].similarity if hits else 0.0


def maybe_rescue(hits: list, message: str, *, k: int) -> Rescue:
    """Re-search in the corpus's vocabulary if the first attempt was weak.

    Returns the better of the two results, measured rather than assumed: if the
    rewrite retrieves no better than the original, the original stands.
    """
    before = top_similarity(hits)
    if before >= WEAK_BELOW:
        return Rescue(hits, used=False, before=before)

    try:
        prompt = loader.load("rewrite")
        response = get_client().complete(
            "generation",
            prompt.messages(message=message),
            temperature=0.0,      # a search string, not prose
            max_tokens=60,
        )
    except Exception as exc:  # noqa: BLE001
        # A failed rescue is not a failed turn. She gets the original result,
        # which is what she would have got anyway.
        return Rescue(hits, used=False, before=before, error=str(exc)[:120])

    query = response.text.strip().strip('"').splitlines()[0].strip()
    if not query or query.upper().startswith(NONE):
        # The rewriter says there is no answerable question in the message. That
        # is a real answer, and it matches what the grounded path will conclude.
        return Rescue(hits, used=False, before=before, query=NONE)

    rescued = retrieval.search(query, k=k)
    after = top_similarity(rescued)

    # Only keep it if it actually did better. The comparison is the point --
    # without it this is a second call that nobody has checked.
    if after <= before:
        return Rescue(hits, used=False, query=query, before=before, after=after)

    return Rescue(rescued, used=True, query=query, before=before, after=after)
