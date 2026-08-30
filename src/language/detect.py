"""Which register she is writing in. Deterministic, no model.

Ported from the previous build, where it worked and was then left behind in this
one. The cost of leaving it behind was visible in a single exchange:

    She:  "mabeste wangu wote wanakaa they are having sex. but mimi i just
           want to study to help my family"
    It:   four paragraphs of careful English

The prompt layer already had a note for exactly that message — *"she has been
writing in the mixed Kenyan register ... **answer in that same mixed register.**
Do not switch her to English"* — and the pipeline was passing an empty language
label, so every turn fell back to *"She wrote in English. Answer in clear Kenyan
English."* The instruction was right, the input to it was blank, and nothing
failed loudly.

**This is a signal, not a determination.** It is a word-list heuristic. It exists
so the generator can mirror her register and so results can be sliced by
language; it is not a claim that the system is good in Kiswahili. That remains a
measurement question, and the retrieval side already has a number for it:
asking in Kiswahili costs −0.062 similarity.
"""

from __future__ import annotations

import re

KENYAN_ENGLISH = "kenyan_english"
KISWAHILI = "kiswahili"
SHENG_CODE_SWITCH = "sheng_code_switch"
MIXED = "mixed"
UNKNOWN = "unknown"

#: High-frequency Kiswahili function words. Function words rather than content
#: words, because they are far less likely to turn up incidentally in English.
_SWAHILI = frozenset({
    "na", "ya", "wa", "kwa", "ni", "si", "katika", "kama", "lakini", "sana",
    "hii", "hiyo", "huyu", "yangu", "yako", "yake", "wangu", "wako", "nini",
    "nani", "wapi", "lini", "kwanini", "je", "sitaki", "nataka",
    "naskia", "nina", "una", "ana", "tuna", "wana", "kuwa", "kuna", "hapa",
    "pale", "sasa", "leo", "jana", "kesho", "asante", "pole", "habari",
    "mimi", "wewe", "yeye", "sisi", "nyinyi", "wao", "mtu", "watu", "mwili",
    "hedhi", "damu", "maumivu", "msaada", "rafiki", "mama", "baba", "dada",
    # Added for this scope. The old list was built for a corpus about periods
    # and low mood; these are the words that come up when the subject is sex,
    # contraception and relationships.
    "mpenzi", "mchumba", "kondom", "mimba", "kuzuia", "uzazi", "ngono",
    "kufanya", "wanakaa", "wanafanya", "anataka", "nataka", "sitaki",
})

#: Sheng is characterised less by a fixed lexicon than by code-switching and by
#: borrowed English verbs taking Swahili morphology. Indicative, not definitive.
_SHENG = frozenset({
    "sasa", "poa", "fiti", "buda", "manze", "aki", "kuja", "mzee", "chali",
    "msee", "dem", "boyz", "form", "noma", "bwana", "wacha", "sema", "niaje",
    "mambo", "vipi", "kunanga", "mrembo", "ndio", "bro", "beshte", "gani",
    "mabeste", "siste", "mresh", "odi", "keja", "githaa", "sare",
})

#: An English verb stem carrying Swahili subject/tense prefixes — "anacheki",
#: "ananitext", "wanakaa". The clearest code-switch signal available, and the
#: reason it is weighted ahead of raw marker counts.
_BORROWED_VERB = re.compile(
    r"\b(?:a|ni|u|tu|wa|m)(?:na|li|ta|me)?"
    r"(?:cheki|text|call|post|block|share|save|chat|search|reply|type|"
    r"date|date|plan|check|confuse|stress|disturb|prefer|kaa)\w*\b",
    re.IGNORECASE,
)


def detect(text: str) -> str:
    """A shallow register signal. A hint for the generator, nothing more."""
    tokens = re.findall(r"[a-z']+", (text or "").lower())
    if not tokens:
        return UNKNOWN

    swahili = sum(1 for t in tokens if t in _SWAHILI)
    sheng = sum(1 for t in tokens if t in _SHENG)
    borrowed = len(_BORROWED_VERB.findall(text))

    share = (swahili + sheng + borrowed) / len(tokens)

    # Borrowed-verb morphology is the strongest signal, so it decides on its own.
    if borrowed or (sheng and share >= 0.12):
        return SHENG_CODE_SWITCH
    if share >= 0.45:
        return KISWAHILI
    if share >= 0.12:
        return MIXED
    return KENYAN_ENGLISH
