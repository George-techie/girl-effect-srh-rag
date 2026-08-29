"""Approved text. Never generated.

A girl disclosing harm gets human-approved wording, not a model's improvisation
— not because a model would necessarily do worse, but because nobody can review,
approve or audit text that is rewritten on every turn.

Short on purpose. She is reading this while distressed, and the previous build's
staged design is kept: the opening arrives unprompted, the rest is offered.
"""

from __future__ import annotations

#: What a disclosure gets. One opening, because the taxonomy here is a floor
#: rather than a set of tracks — see docs/decisions.md D-01.
SAFEGUARDING = (
    "Thank you for telling me. That took something, and what you've described "
    "isn't okay — and it isn't your fault.\n\n"
    "I'm a digital guide, so I can't be the person who helps you with this. "
    "Someone real can."
)

#: Offered after the opening, not sent with it.
SAFEGUARDING_FOLLOWUP = (
    "People who can help with this properly: a trusted adult, a health worker "
    "at any clinic, a teacher you trust, or a helpline.\n\n"
    "You deserve support from someone qualified, not just words on a screen."
)

#: Self-harm risk is the one category where contacts are not held behind a tap.
#: The previous build measured that exact failure: `urgent` was set on the
#: template, written into the trace, and read by nothing, so a girl who did not
#: tap saw less than one who disclosed something less dangerous and did.
SELF_HARM = (
    "Thank you for telling me. That sounds really heavy, and I'm glad you said "
    "it rather than carrying it alone.\n\n"
    "Please tell someone near you now, or go to the nearest health facility.\n\n"
    "**Befrienders Kenya** — +254 722 178 177 · call or WhatsApp · you don't "
    "have to give your name\n"
    "**Kenya Red Cross counselling** — 1199 · free · any time"
)

#: Topics deliberately outside this service. Not a failure, and it should not
#: read like one.
OUT_OF_SCOPE = (
    "That's outside what I can help with — I stick to contraception, sexual "
    "health, staying safe, and finding services, because those are what my "
    "sources actually cover.\n\n"
    "For anything medical about your own body — what's causing something, which "
    "method is right for you, or how much of anything to take — a nurse or "
    "clinician is the right person, and they won't turn you away.\n\n"
    "Is there something in what I do cover that I can help with?"
)

#: The corpus was searched and could not support an answer. Deliberately not the
#: same as out-of-scope: telling her "I don't cover that" when the topic *is*
#: covered and the search simply failed teaches her the service has nothing.
NO_EVIDENCE = (
    "I don't have anything solid enough in my sources to answer that properly, "
    "and I'd rather say so than guess.\n\n"
    "Try asking it a different way, or ask me something nearby — I can help with "
    "contraception methods, condoms and HIV, getting to a clinic, or what to "
    "expect when you go."
)

#: The system produced an answer and then rejected its own draft. Distinct from
#: NO_EVIDENCE, because the corpus *did* cover it and the fault is ours.
BLOCKED = (
    "Sorry — I had trouble putting that answer together properly, so I'd rather "
    "not send it half-right.\n\n"
    "Try asking again, or in a slightly different way?"
)

TECHNICAL = (
    "Something went wrong on my side just now. Please try again in a moment."
)

#: Nothing usable arrived. Says so without implying she did something wrong.
EMPTY_INPUT = "I didn't catch that — what would you like to ask?"

TOO_LONG = (
    "That's a lot to read in one go and I'd rather not answer half of it.\n\n"
    "Could you send me the main thing you want to know?"
)
