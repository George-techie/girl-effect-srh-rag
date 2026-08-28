"""Deterministic turn decision. No model, no retrieval, no history.

One job: given her message, decide which of five paths it takes, and whether the
retrieval query should be restated. Experiments 1 and 2 earned exactly this much
and no more.

    factual        answerable from the corpus  ·  restate the query
    access         where, cost, consent, rules ·  restate the query
    support        feeling, fear, shame        ·  keep her words
    safeguarding   harm disclosed or coerced   ·  keep her words, safety path
    out_of_scope   do not retrieve

**Ordered, not scored.** Safeguarding is checked first and can veto everything
below it, because the cost of reading a disclosure as an ordinary question is
not comparable to the cost of the reverse. Out-of-scope is checked next, because
a question that must not be answered must not reach retrieval regardless of how
answerable it looks — Experiment 2 measured a deliberately out-of-scope question
retrieving at 0.691, above most in-scope ones.

The remaining three are checked in order of how sharply they are marked:
access has the clearest surface forms, support the next, and factual is the
fallback. That ordering is a claim being tested, not a proven design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.language import glossary

FACTUAL = "factual"
ACCESS = "access"
SUPPORT = "support"
SAFEGUARDING = "safeguarding"
OUT_OF_SCOPE = "out_of_scope"

#: Paths whose retrieval query is restated into the corpus's vocabulary.
#: Experiment 2: restatement helps these and actively harms the other two.
RESTATED = frozenset({FACTUAL, ACCESS})


@dataclass
class Decision:
    path: str
    reason: str
    matched: list[str] = field(default_factory=list)

    @property
    def restate(self) -> bool:
        return self.path in RESTATED

    @property
    def retrieves(self) -> bool:
        return self.path != OUT_OF_SCOPE


def _res(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


# --- 1 · safeguarding --------------------------------------------------------
# Three families, because they fail differently.

#: Explicit harm. The easy half — violence, force, abuse, exploitation.
_HARM = _res(
    r"\b(rape[ds]?|raped|forced? me|force[sd]? me|made me have sex|"
    r"made me sleep with)\b",
    r"\b(hits?|beats?|hurts?|slaps?|punche[sd])\s+me\b",
    # No Kiswahili variants here on purpose. `hunipiga` and its forms live in
    # the reviewed lexicon, which reaches this pattern two ways: as a risk tag,
    # and by normalising the message to "hits me" before it is scanned. An
    # inline copy would drift from the lexicon the reviewer maintains.
    r"\btouch\w*\s+me\b.{0,44}\b(not (to )?tell|don'?t tell|secret|keep it)\b",
    r"\b(uncle|teacher|stepfather|step-?dad|father|brother|cousin|neighbou?r)\b"
    r".{0,60}\b(touch\w*|come[s]? into my room|meet (me )?alone|sleep with)\b",
    r"\bsend (him|them) (photos|pictures|nudes)\b|\bsend me money\b.{0,40}\bphotos\b",
    r"\b(marry|married)\b.{0,40}\b(making me|forced|arrange)\b|"
    r"\b(making me|forcing me|force me) (to )?marry\b",
    r"\bdon'?t want to be here\b|\bend (it|my life)\b|\bkill myself\b",
)

#: **Reproductive coercion.** A safeguarding category the previous build did not
#: have and did not need, because contraception was out of scope there. Here it
#: is the centre of the use case, and it is the family a keyword list misses:
#: "if you really loved me you wouldn't make me use a condom" contains no force,
#: no threat and no abuse term -- only a condition placed on her consent.
#:
#: The corpus supports treating it as safeguarding rather than as a question.
#: WHO's *Violence Against Women* section names coercive sex alongside forced
#: sex; its adolescents section tells providers to refer when a client discloses
#: "gender-based violence, including sexual violence, force, or coercion"; and
#: Kenya's guidelines define informed choice as consent free of "force, fraud,
#: deceit, duress, bias, or other forms of coercion".
#:
#: Four documented forms, all of which arrive sounding like relationship talk:
_REPRODUCTIVE_COERCION = _res(
    # 1 · consent made conditional
    r"\bif (you|u) (really )?love[d]? me\b",
    r"\b(won'?t|will not|refuses? to) (use|wear) (a )?condom\b.{0,50}"
    r"\b(if|unless|or)\b",
    r"\b(unless|if) (i|you) (don'?t|do not|refuse)\b.{0,40}"
    r"\b(fail|leave|hurt|tell|beat)\b",

    # 2 · contraceptive sabotage, including removing a condom during sex
    r"\b(took|takes|take|slipped|slips) (it|the condom) off\b",
    r"\bremove[ds]? the condom\b|\bwithout (me knowing|telling me)\b",
    r"\b(hid|hides|threw away|throws away|flushed)\b.{0,24}\b(my )?(pills?|"
    r"contracepti\w+|injection)\b",
    r"\bpoked holes?\b|\btampered with\b",

    # 3 · pressure to stop, or not to start
    r"\b(stop|quit|come off) (taking |using )?(the )?(pill|family planning|"
    r"contraception|injection|implant)\b.{0,50}\b(leave|threat|make|force|else|"
    r"angry|beat)\b",
    r"\b(leave|dump) me\b.{0,50}\bstop (taking|using)\b",
    r"\b(won'?t|will not|does ?n'?t) (let|allow) me (to )?(use|take|get)\b",
    r"\bforbids? me\b|\bhanitaki nitumie\b",

    # 4 · pregnancy coercion
    r"\b(wants?|forcing|forces|making) me to (get|be(come)?) pregnant\b",
    r"\bmust have (his|a) baby\b|\bwants? me to have his baby\b.{0,30}"
    r"\b(or|else|threat)\b",

    # general threats attached to any of the above
    r"\b(threaten|threatens|threatened)\b",
    r"\b(he|she|they)\s+(said|says|will)\b.{0,40}"
    r"\b(leave me|dump me|tell everyone|fail me|report me)\b",
    r"\bpressur(e|es|ed|ing) me\b|\bwon'?t take no\b|\bkeeps? asking me to\b",
)

#: Someone else's disclosure. Classifiers reliably under-detect these because
#: the grammar is third-person even when the content is identical.
_THIRD_PARTY = _res(
    r"\b(my friend|a friend|my sister|my cousin|someone i know)\b"
    r".{0,80}\b(raped|forced|hits?|beats?|touch|comes? into her room|"
    r"sleep with|hurt(s|ing)? her)\b",
)

# --- 2 · out of scope --------------------------------------------------------
_OUT_OF_SCOPE = _res(
    # Prescribing and dosing: topically in scope, out of scope as an action.
    r"\bwhich (pill|method|one) should i (take|use|choose)\b",
    r"\bhow many (mg|milligrams|tablets|pills)\b|\bwhat dose\b|\bdosage\b",
    r"\bwhat should i take for\b",
    # Diagnosis.
    r"\bwhat'?s wrong with me\b|\bwhat is wrong with me\b",
    r"\b(do i have|have i got)\b.{0,30}\?",
    # Cut from scope: menstruation as a standalone concern, mental health.
    r"\b(my )?periods?\b.{0,40}\b(irregular|late|missed|stopped|heavy|painful)\b",
    r"\b(irregular|missed|late)\b.{0,20}\bperiods?\b",
    r"\bfeeling (very )?(low|down|depressed|sad)\b|\bcan'?t sleep\b|"
    r"\bcannot sleep\b|\bdepress(ed|ion)\b|\banxious\b|\banxiety\b",
    # Law, and anything simply not this service's job.
    r"\bis (abortion|it) legal\b|\blegal in kenya\b|\bwhat does the law\b",
    r"\bwrite my\b.{0,24}\b(homework|essay|assignment)\b|\bdo my homework\b",
    r"\bcapital of\b|\bwho is the president\b|\bweather\b",
)

#: Rescues a menstrual symptom that is attributed to a method -- the corpus
#: covers bleeding changes on contraception, and D47 sits one word away from
#: D39, which it must not be confused with.
#:
#: **Scoped to the menstruation patterns only.** Applied to the whole
#: out-of-scope family it also rescued prescribing, diagnosis and dosing, since
#: "which pill should I take" mentions a method too. That took out-of-scope
#: recall to 0.500 on the first run.
_MENSTRUAL_OUT_OF_SCOPE = _res(
    r"\b(my )?periods?\b.{0,40}\b(irregular|late|missed|stopped|heavy|painful)\b",
    r"\b(irregular|missed|late)\b.{0,20}\bperiods?\b",
    r"\bbleed\w*\b.{0,30}\bbetween periods?\b",
)

_METHOD_ATTRIBUTED = _res(
    r"\b(pill|implant|injection|iud|coil|contracepti\w+|family planning)\b",
)

# --- 3 · access --------------------------------------------------------------
_ACCESS = _res(
    r"\bwhere (can|do) i (get|go|find)\b|\bnaweza pata\b.{0,30}\bwapi\b",
    r"\bwhere.{0,30}\b(clinic|chemist|pharmacy|hospital|get condoms)\b",
    r"\bwithout (my )?(parents?|mum|mother|dad|father|guardian)\b",
    r"\b(parental|parents?'?) (consent|permission|agreeing|knowing)\b",
    r"\bcan (a |the )?(nurse|doctor|clinic|they) refuse\b",
    r"\bdo i need\b.{0,30}\b(money|id|permission|consent|to be married)\b",
    r"\bis (it|family planning|contraception) free\b|\bhow much does it cost\b",
    r"\bwhat will they ask me\b|\bwhat happens (at|when i go to) the clinic\b",
    r"\bwithout (my mum|my mother|anyone) (finding out|knowing)\b",
    r"\b(am i|are we) (old enough|allowed)\b",
)

# --- 4 · support -------------------------------------------------------------
#: Feeling rather than question. Checked before `factual` because a girl saying
#: she is frightened has not asked for information, and Experiment 2 measured
#: what happens when these turns are restated: her words retrieve the youth
#: material, the restatement retrieves policy literature.
_SUPPORT = _res(
    r"\bi'?m (so |really |very )?(scared|afraid|frightened|worried|ashamed|"
    r"embarrassed|nervous|anxious about|stupid|confused)\b",
    r"\bi feel\b|\bi'?m feeling\b|\bnaogopa\b|\bninaogopa\b",
    r"\bi (keep )?worry(ing)?\b|\bi don'?t know who to (talk|turn) to\b",
    r"\bwill (think|judge|say)\b.{0,30}\b(i'?m|me)\b|\bpeople will think\b",
    r"\bthey'?ll think\b|\beveryone (will|would) think\b",
    r"\b(would|will) (throw me out|kill me|be furious|be angry|disown)\b",
    r"\bthank you\b|\bthanks\b|\bthat helped\b|\basante\b",
    r"\bis it normal to feel\b|\bam i normal for feeling\b",
    r"\bhe'?ll leave me\b|\bwill leave me\b|\bdoesn'?t like condoms\b",
)


def _hits(patterns: tuple[re.Pattern[str], ...], text: str) -> list[str]:
    return [p.pattern[:44] for p in patterns if p.search(text)]


def decide(message: str) -> Decision:
    """Classify a turn. Ordered checks; the first family to fire wins.

    The Kenyan glossary contributes two things, and both are unions with the
    rules rather than agreements with them — any signal is enough to flag,
    because a missed disclosure and a false alarm are not comparable costs.

      1. its **risk tags**, which are a deterministic finding in their own right
      2. its **normalised text**, scanned by the English families alongside the
         original, so that "chali yangu hunipiga" reaches the pattern for
         "hits me" without that pattern needing a Kiswahili variant bolted on
    """
    text = " ".join(message.split())

    gloss = glossary.scan(text)
    normalised = glossary.normalise(text)
    # Only worth scanning twice when the glossary actually changed something.
    variants = (text,) if normalised == text else (text, normalised)

    if gloss.risk_tags:
        return Decision(
            SAFEGUARDING,
            f"safeguarding · glossary risk tag",
            sorted(gloss.risk_tags),
        )

    for name, family in (("harm", _HARM), ("reproductive coercion", _REPRODUCTIVE_COERCION),
                         ("third-party", _THIRD_PARTY)):
        matched = [m for v in variants for m in _hits(family, v)]
        if matched:
            return Decision(SAFEGUARDING, f"safeguarding · {name}", matched)

    matched = _hits(_OUT_OF_SCOPE, text)
    if matched:
        # A menstrual symptom attributed to a method is in scope: the corpus
        # covers bleeding changes on contraception. Without this, D47 and D39
        # collapse into one another. Prescribing, dosing and diagnosis are not
        # rescued -- they mention methods too, and they stay out of scope.
        if _hits(_MENSTRUAL_OUT_OF_SCOPE, text) and _hits(_METHOD_ATTRIBUTED, text):
            return Decision(FACTUAL, "out-of-scope phrasing, but attributed to a method")
        return Decision(OUT_OF_SCOPE, "out of scope", matched)

    matched = _hits(_ACCESS, text)
    if matched:
        return Decision(ACCESS, "access", matched)

    matched = _hits(_SUPPORT, text)
    if matched:
        return Decision(SUPPORT, "support", matched)

    return Decision(FACTUAL, "no other family matched — treated as factual")
