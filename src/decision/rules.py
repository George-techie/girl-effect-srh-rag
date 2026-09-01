"""Deterministic turn decision. No model, no retrieval, no history.

One job: given her message, decide which of five paths it takes, and whether the
retrieval query should be restated. Experiments 1 and 2 earned exactly this much
and no more.

    chat           greeting, thanks, small talk ·  no corpus, claims nothing
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
CHAT = "chat"
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
    #: The regex sources that fired, for the trace. Debug detail, not semantics.
    matched: list[str] = field(default_factory=list)

    #: Force, threat, assault, something already done to her, or danger to her
    #: life. Verified contacts go in front of her rather than behind a tap.
    #: False on a coercion *concern*, which is still safeguarding and still
    #: acknowledged -- see `_URGENT_FAMILIES`.
    urgent: bool = False

    #: What kind of risk this is, in stable names the rest of the system can
    #: branch on: `self_harm_risk`, `sexual_violence`, `emotional_support`.
    #:
    #: Separate from `matched` because conflating them cost the most important
    #: behaviour in the build. The pipeline asked `"self_harm_risk" in
    #: decision.matched`, `matched` held regex source strings, and so a girl
    #: writing *"i dont want to be here anymore"* received the ordinary
    #: safeguarding reply rather than the urgent one with crisis numbers in it.
    #: Nothing errored, no test failed, and the check looked correct.
    tags: list[str] = field(default_factory=list)

    #: She asked for a service, a contact or a person -- in the same message.
    #: Orthogonal to `path`, never a replacement for it: "where can I get help
    #: if someone hurt me?" is a disclosure AND a request, and reading it as
    #: only one of the two is how she ends up being asked whether she wants
    #: help that she has just asked for.
    help_requested: bool = False

    @property
    def restate(self) -> bool:
        return self.path in RESTATED

    @property
    def is_fallback(self) -> bool:
        """`factual` reached by default rather than by matching anything.

        Worth distinguishing, because `factual` is the catch-all and everything
        unmatched lands in it — including messages that are not questions at
        all. *"Mabeste wangu wote wanakaa they are having sex, but mimi i just
        want to study to help my family"* matched no family, became factual, was
        held to a contract requiring a citation, and was refused.

        A turn that matched a factual pattern and then found no evidence should
        say so honestly. A turn that only landed here by default and found no
        evidence was never a lookup in the first place, and telling her the
        sources do not cover it answers a question she did not ask.
        """
        return self.path == FACTUAL and not self.matched

    @property
    def retrieves(self) -> bool:
        """Does this turn actually reach the corpus?

        Chat has nothing to look up, out-of-scope must not look, safeguarding
        is answered entirely from approved text, and support retrieves material
        about somebody else's situation -- see `grounded` for the measurement.
        Not searching those turns is also why they are fast.

        Safeguarding was missing from this list while the pipeline returned
        early anyway, so the property and the code disagreed and nothing
        noticed. It surfaced the moment something else started trusting it:
        follow-up resolution rewrote a girl's disclosure against her earlier
        question about the implant. Harmless there, because the query was
        discarded — but a property that lies is only ever harmless by accident.
        """
        return self.path not in (OUT_OF_SCOPE, CHAT, SAFEGUARDING, SUPPORT)

    @property
    def grounded(self) -> bool:
        """Whether the reply must cite. The contract is chosen by which path
        produced it, never inferred from whether citations happen to be there --
        an uncited grounded answer would otherwise validate itself.

        **Support is not grounded, and that was measured.** A support turn is
        about how she feels, and the corpus has no answer to "I'm scared" -- it
        has clinical guidance. Asked to ground those turns it returned, at
        similarities of 0.55-0.63:

            "I am so scared someone will see me at the clinic"
                -> "I was raped and I am worried that no one will believe me"
            "worried about starting sex, want to focus on becoming a nurse"
                -> "I'm not ready to become a father"

        Requiring a citation there forces one of two failures: cite that at her,
        or cite nothing and be blocked. The second is what happened -- a girl
        described two years with her boyfriend, her fear, and her dream of
        nursing, and got "I had trouble putting that answer together."

        So support takes the conversational contract, which is safe for the
        opposite reason to a grounded one: it makes no claim at all."""
        return self.path in (FACTUAL, ACCESS)


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
    r"\btouch\w*\s+me\b.{0,44}\b(not (to )?tell|don'?t tell|do not tell"
    r"|secret|keep it)\b",
    r"\b(uncle|teacher|stepfather|step-?dad|father|brother|cousin|neighbou?r)\b"
    r".{0,60}\b(touch\w*|come[s]? into my room|meet (me )?alone|sleep with)\b",
    r"\bsend (him|them) (photos|pictures|nudes)\b|\bsend me money\b.{0,40}\bphotos\b",
    r"\b(marry|married)\b.{0,40}\b(making me|forced|arrange)\b|"
    r"\b(making me|forcing me|force me) (to )?marry\b",
)

#: Suicidal ideation. Its own family, and checked before every other one.
#:
#: Split out because it is the single case where contacts arrive unprompted
#: rather than behind a tap, and the pipeline needs to recognise it without
#: pattern-matching on regex source. See `Decision.tags`.
#:
#: Contractions and their expansions both. "I don't want to be here" was caught
#: and "I do not want to be here" was not -- the same sentence, one apostrophe
#: apart, on the path where a miss costs the most.
_SELF_HARM = _res(
    r"\b(don'?t|do not) want to be (here|alive)\b",
    r"\bend (it all|it|my life)\b|\bkill myself\b|\btake my own life\b",
    r"\b(don'?t|do not) want to live\b|\bwant to die\b|\bbetter off without me\b",
    r"\bno (point|reason) (in )?(living|going on|carrying on)\b",
    r"\bhurt(ing)? myself\b|\bcut(ting)? myself\b",
    r"\bnataka kufa\b|\bnimechoka na maisha\b",
)

#: **Contraceptive sabotage**, including removing a condom during sex. Split out
#: of the coercion family because it is not pressure -- it is something already
#: done to her without her consent, and it carries a pregnancy and HIV/STI
#: exposure she does not yet know about. Urgent tier.
_SABOTAGE = _res(
    r"\b(took|takes|take|slipped|slips) (it|the condom) off\b",
    r"\bremove[ds]? the condom\b|\bwithout (me knowing|telling me)\b",
    r"\b(hid|hides|threw away|throws away|flushed)\b.{0,24}\b(my )?(pills?|"
    r"contracepti\w+|injection)\b",
    r"\bpoked holes?\b|\btampered with\b",
)

#: Which service route each safeguarding family draws contacts from.
_TAG_BY_FAMILY = {
    "harm": "sexual_violence",
    "sabotage": "sexual_violence",
    "reproductive coercion": "sexual_violence",
    "third-party": "emotional_support",
}

#: **Detect broadly, escalate narrowly.**
#:
#: One safeguarding route, two severities. The distinction is not a taxonomy and
#: it is not a second classifier -- it is which families fired.
#:
#: `urgent` means force, threat, assault, something already done to her, or
#: danger to her life. She gets safety guidance and verified contacts put in
#: front of her.
#:
#: Everything else is a *concern*: pressure, conditional consent, "he keeps
#: asking", "he gets upset when I say no". Those are real coercion signals and
#: they must be recognised as such -- but they are not emergencies, and treating
#: them as one has two costs. It buries her in referrals for a conversation she
#: wanted to have, and it turns a service that should be hers into a reporting
#: mechanism pointed at her. Contacts are offered there, not pushed.
_URGENT_FAMILIES = frozenset({"self-harm", "harm", "sabotage"})

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
    #
    # Any grammatical person, in either direction. D38 was the miss that forced
    # this: *"He said if I really loved him I wouldn't make him use a condom"*
    # is the same coercion script as "if you loved me you would", reported
    # afterwards instead of said to her face. Girls repeat what he said far more
    # often than they quote it at us in the second person, and a rule that only
    # reads direct address misses the way the disclosure actually arrives.
    r"\bif (i|you|u|she|we|he) (really |truly )?love[ds]? "
    r"(me|him|her|you|us|them)\b",
    r"\b(won'?t|will not|refuses? to) (use|wear) (a )?condom\b.{0,50}"
    r"\b(if|unless|or)\b",
    r"\b(unless|if) (i|you) (don'?t|do not|refuse)\b.{0,40}"
    r"\b(fail|leave|hurt|tell|beat)\b",

    # 3 · pressure to stop, or not to start
    r"\b(stop|quit|come off) (taking |using )?(the )?(pill|family planning|"
    r"contraception|injection|implant)\b.{0,50}\b(leave|threat|make|force|else|"
    r"angry|beat)\b",
    r"\b(leave|dump) me\b.{0,50}\bstop (taking|using)\b",
    r"\b(won'?t|will not|does ?n'?t|does not|do not) (let|allow) me "
    r"(to )?(use|take|get)\b",
    r"\bforbids? me\b|\bhanitaki nitumie\b",

    # 4 · pregnancy coercion
    r"\b(wants?|forcing|forces|making) me to (get|be(come)?) pregnant\b",
    r"\bmust have (his|a) baby\b|\bwants? me to have his baby\b.{0,30}"
    r"\b(or|else|threat)\b",

    # general threats attached to any of the above
    r"\b(threaten|threatens|threatened)\b",
    r"\b(he|she|they)\s+(said|says|will)\b.{0,40}"
    r"\b(leave me|dump me|tell everyone|fail me|report me)\b",
    r"\bpressur(e|es|ed|ing) me\b|\b(won'?t|will not) take no\b"
    r"|\bkeeps? asking me to\b",
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
    # Intervening words allowed, for the third time in this file. She writes
    # "where can i actually go to get it", "where do i even go", "where can i
    # just get them" -- and the fixed form matched none of them, so an access
    # question became `factual`, never reached the service table, and was
    # answered with "I don't have the clinic list in front of me". The whole
    # Theory of Change ends at this turn.
    r"\bwhere (can|do|could|should|would) (i|we|a girl|someone)\b"
    r"(\s+\w+){0,3}?\s+(get|go|find|buy|access)\b",
    r"\bwhere (to|do you) (get|go|find|buy)\b",
    r"\bnaweza pata\b.{0,30}\bwapi\b|\bnaenda wapi\b|\bnipate wapi\b",
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

# --- 4 · chat ----------------------------------------------------------------
#: Greetings, thanks, goodbyes. She has not asked anything, so there is nothing
#: to retrieve and nothing to cite -- and the grounded contract, which requires
#: a citation, blocks the reply for having none. "hello aunti" reaching a
#: fallback that says "I had trouble putting that answer together" is that bug.
#: Longest a message can be and still be only small talk. A greeting, a thanks
#: and a goodbye are short by nature; anything longer is a message that happens
#: to begin politely.
_CHAT_MAX_WORDS = 12

_CHAT = _res(
    r"^\s*(hi|hey|hello|hallo|niaje|sasa|mambo|habari|jambo|yo)\b",
    r"^\s*(good (morning|afternoon|evening))\b",
    r"\bhello aunti\b|\bhi aunti\b|\bhey aunti\b|\baunti\?*$",
    r"^\s*(thanks|thank you|asante|nashukuru)\b|\bthank you\b\s*[.!]?\s*$",
    r"^\s*(bye|goodbye|kwaheri|later|ok|okay|sawa)\s*[.!]?\s*$",
    # She says she is going to do it. The Theory of Change's last stage arrives
    # as a short sentence -- "sawa, nitaenda this weekend", "poa, i'll call
    # them" -- and it is not a question. Answering it with a cited paragraph
    # talks over the moment the whole conversation was for.
    #
    # Safe only because the chat family is gated to twelve words: a long message
    # that happens to open with "sawa" is not a goodbye.
    r"^\s*(sawa|poa|haya|nzuri|asante|thanks)\b.{0,60}"
    r"\b(nitaenda|nitajaribu|nitawapigia|nitatext|i'?ll go|i will go|"
    r"i'?ll call|i will call|i'?ll text|i will text|i'?ll try|i will try)\b",
    r"\bwho are you\b|\bwhat (can|do) you (do|help with)\b|\bwewe ni nani\b",
    r"^\s*\w{1,12}\s*[?!.]?\s*$",
)

#: What she wants for herself. Girl Effect's Theory of Change puts self-identity
#: and aspiration among the eight drivers of behaviour change, and this build
#: measured self-identity as its weakest retrieval driver (MRR 0.417). Part of
#: that is a corpus gap. Part of it is that these turns should never have gone
#: to the corpus at all.
#:
#: Deliberately tight frames. "I want to be a doctor" is an ambition; "I want to
#: be on the pill" is an access question, and only the article keeps them apart.
_ASPIRATION = _res(
    r"\bi want to (be|become) an? \w+",
    r"\bi (want|hope|plan|dream) to (finish|complete|go back to|stay in) "
    r"(school|college|university|form \w+)\b",
    r"\bmy dream is\b|\bwhen i (finish|complete) school\b",
    r"\bi('?m| am) the first in my (family|home)\b",
    r"\bi (passed|got into|was accepted)\b.{0,30}\b(school|college|university|"
    r"form \w+|exams?|kcse|kcpe)\b",
    r"\bnataka kuwa\b|\bndoto yangu\b",
    r"\bi want (a career|a better life|to make something of myself)\b",
)

#: An explicit request for information, however it is wrapped. Deliberately
#: narrow: she has to actually ask, not merely mention a topic. A girl saying
#: she is frightened is support; a girl saying she is frightened *and asking
#: what happens at the clinic* has asked a question, and the answer is the
#: reassurance.
_ASKING = _res(
    r"\btell me (what|how|about|more)\b|\bcan you tell me\b",
    r"\bwhat (happens|do they do|will they do|should i expect|to expect)\b",
    r"\bwhat (is|are) (it|they|the)\b.{0,30}\b(like|process)\b",
    r"\bhow (does|do) (it|they|this) (work|go)\b",
    r"\bwalk me through\b|\bexplain\b|\btalk me through\b",
    r"\bwhat do they ask\b|\bwhat will they ask\b",
    r"\bis it true\b|\bni kweli\b",
    r"\bwhat are my options\b|\bwhat can i (use|do|take)\b",
)

# --- 5 · support -------------------------------------------------------------
#: Feeling rather than question. Checked before `factual` because a girl saying
#: she is frightened has not asked for information, and Experiment 2 measured
#: what happens when these turns are restated: her words retrieve the youth
#: material, the restatement retrieves policy literature.
_SUPPORT = _res(
    # "i am" as well as "i'm". She types both, and only one was matched.
    #
    # The intensifier used to be a fixed list -- `(so |really |very )?` -- which
    # caught "i am so scared" and missed "i am just super scared", "i am super
    # scared" and "im just so worried". A girl wrote *"what if i get pregnant
    # and i become a young mother. i am just super scared"* and it fell through
    # to `factual`, was held to a contract requiring a citation for a feeling,
    # and was refused. Two words of intensifier decided whether she was heard.
    #
    # Any few words now sit between "I am" and the feeling. Over-matching here
    # costs a warm reply where a factual one would also have worked; under-
    # matching costs her the answer entirely, and those are not comparable.
    r"\bi('?m| am)\s+(?:\w+\s+){0,3}?(scared|afraid|frightened|worried|"
    r"ashamed|embarrassed|nervous|anxious|stressed|overwhelmed|lost|"
    r"stupid|confused|terrified|panicking)\b",
    # Same intervening-word problem as the intensifier above, found the same
    # way. "I just feel so alone since everyone at school found out" did not
    # match `\bi feel\b`, fell through to `factual`, and was told the sources
    # did not cover it.
    r"\bi (\w+ ){0,2}?feel\b|\bi'?m feeling\b|\bnaogopa\b|\bninaogopa\b",
    r"\bi (keep )?worry(ing)?\b|\bi don'?t know who to (talk|turn) to\b",
    r"\bwill (think|judge|say)\b.{0,30}\b(i'?m|me)\b|\bpeople will think\b",
    r"\bthey'?ll think\b|\beveryone (will|would) think\b",
    r"\b(would|will) (throw me out|kill me|be furious|be angry|disown)\b",
    # thanks / asante deliberately absent -- they are chat, not feeling, and
    # they were the reason "hello aunti" and "asante sana" were being answered
    # under the grounded contract and blocked for having no citation.
    r"\bis it normal to feel\b|\bam i normal for feeling\b",
    r"\bhe'?ll leave me\b|\bwill leave me\b|\bdoesn'?t like condoms\b",
)


#: An explicit request for a service, a contact or a person to talk to. This is
#: not a route -- it is a fact about the message that changes what the route
#: does. The previous build measured the failure it prevents: contacts were
#: looked up, ranked, put in state, and then held behind a button by a girl who
#: had already asked for them.
_HELP_REQUEST = _res(
    r"\bwhere (can|do|could) i (get|go|find|call)\b",
    r"\bwho (can|do|could) i (call|talk to|see|contact|ask)\b",
    r"\b(can|could) you (give|send|share) me\b.{0,24}"
    r"\b(number|contact|helpline|hotline|clinic|service)\b",
    r"\b(a|any|the) (number|helpline|hotline|contact)\b",
    r"\bneed (help|someone|somebody|to talk)\b",
    r"\bhelp me\b|\bi need help\b|\bnisaidie\b|\bnataka msaada\b",
    r"\bwapi\b|\bnaweza pata\b",
    r"\bwhere.{0,24}\b(clinic|chemist|pharmacy|hospital|counsell?or)\b",
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
    asked_for_help = bool(_hits(_HELP_REQUEST, text))

    gloss = glossary.scan(text)
    normalised = glossary.normalise(text)
    # Only worth scanning twice when the glossary actually changed something.
    variants = (text,) if normalised == text else (text, normalised)

    if gloss.risk_tags:
        return Decision(
            SAFEGUARDING,
            "safeguarding · glossary risk tag",
            sorted(gloss.risk_tags),
            tags=sorted(gloss.risk_tags),
            help_requested=asked_for_help,
        )

    # Self-harm first, and separately, because it is the one disclosure that
    # gets contacts without being asked. It used to live inside `_HARM`, and the
    # pipeline tested `"self_harm_risk" in decision.matched` -- but `matched`
    # holds regex source strings, so that tag only ever appeared via the
    # glossary. Every self-harm disclosure phrased in English therefore got the
    # ordinary safeguarding reply instead of the urgent one, and nothing failed.
    # A signal read but never set: the same defect as the previous build's
    # `urgent` flag, running in the opposite direction.
    matched = [m for v in variants for m in _hits(_SELF_HARM, v)]
    if matched:
        return Decision(SAFEGUARDING, "safeguarding · self-harm", matched,
                        tags=["self_harm_risk"], urgent=True,
                        help_requested=asked_for_help)

    for name, family in (("harm", _HARM), ("sabotage", _SABOTAGE),
                         ("reproductive coercion", _REPRODUCTIVE_COERCION),
                         ("third-party", _THIRD_PARTY)):
        matched = [m for v in variants for m in _hits(family, v)]
        if matched:
            return Decision(SAFEGUARDING, f"safeguarding · {name}", matched,
                            tags=[_TAG_BY_FAMILY[name]],
                            urgent=name in _URGENT_FAMILIES,
                            help_requested=asked_for_help)

    matched = _hits(_OUT_OF_SCOPE, text)
    if matched:
        # A menstrual symptom attributed to a method is in scope: the corpus
        # covers bleeding changes on contraception. Without this, D47 and D39
        # collapse into one another. Prescribing, dosing and diagnosis are not
        # rescued -- they mention methods too, and they stay out of scope.
        if _hits(_MENSTRUAL_OUT_OF_SCOPE, text) and _hits(_METHOD_ATTRIBUTED, text):
            return Decision(FACTUAL, "out-of-scope phrasing, but attributed to a method",
                            help_requested=asked_for_help)
        return Decision(OUT_OF_SCOPE, "out of scope", matched,
                        help_requested=asked_for_help)

    matched = _hits(_ACCESS, text)
    if matched:
        return Decision(ACCESS, "access", matched, help_requested=asked_for_help)

    # Chat before support. A greeting is short and warm and contains none of
    # the feeling words support looks for, but "asante sana" was matching
    # support's thanks pattern and being answered under the grounded contract.
    #
    # **Small talk has to actually be small.** The chat patterns are anchored to
    # the start of the message, so any message *beginning* with a pleasantry
    # matched however long it ran. A girl wrote 48 words -- she opened with
    # "thanks for the willingness to give me support", told us she had been
    # isolated, and then asked directly about HIV risks and signs -- and the
    # word "thanks" routed the whole thing to small talk. It never reached the
    # corpus, so the one question in it went unanswered.
    #
    # A greeting, a thanks and a goodbye are short by nature. Past this length
    # she is saying something, and whatever she opened with was manners.
    matched = _hits(_CHAT, text) if len(text.split()) <= _CHAT_MAX_WORDS else []
    if matched:
        return Decision(CHAT, "greeting or small talk", matched)

    # Her ambitions, on the conversational contract. Empowerment is in scope --
    # it is half of what this product is for -- but "I want to be a doctor, I'm
    # the first in my family to finish school" has nothing to retrieve and
    # nothing to cite. It was falling through to `factual`, which sent it to the
    # corpus and answered it under a contract requiring a citation, from
    # passages about contraception. The right reply says something back to her;
    # it does not look anything up.
    matched = _hits(_ASPIRATION, text)
    if matched:
        return Decision(CHAT, "her ambitions — nothing to look up", matched)

    matched = _hits(_SUPPORT, text)
    if matched:
        # **An explicit request for information wins over the feeling around
        # it**, because the grounded contract can do both and the conversational
        # one cannot. A grounded answer opens with an acknowledgement and then
        # answers, cited; a conversational reply can only acknowledge, and on a
        # turn like *"yes please tell me what happens, i am actually very
        # scared"* that means the question she asked is never answered.
        #
        # This is the turn where intent becomes action -- she is frightened and
        # asking what a clinic visit involves anyway -- so losing it costs more
        # than any routing error in the set.
        asking = _hits(_ASKING, text)
        if asking:
            return Decision(FACTUAL, "asked a question inside a feeling",
                            matched + asking, help_requested=asked_for_help)
        return Decision(SUPPORT, "support", matched, help_requested=asked_for_help)

    return Decision(FACTUAL, "no other family matched — treated as factual",
                    help_requested=asked_for_help)
