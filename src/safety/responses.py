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
    "isn't okay, and it isn't your fault.\n\n"
    "I'm a digital guide, so I can't be the person who helps you with this. "
    "Someone real can."
)

#: **Pressure and conditional consent, without force.** The concern tier.
#:
#: "My boyfriend is pressuring me to have sex", "he keeps asking", "he gets
#: upset when I say no", "he says if I loved him I would". These are real
#: coercion signals and the system must recognise every one of them. They are
#: not emergencies.
#:
#: Answering them with the handoff text -- *"I can't be the person who helps
#: you with this, someone real can"* -- gets two things wrong at once. It reads
#: as being passed on when she came to talk, and it treats a conversation she
#: wanted to have as a referral event. At any real scale that also buries the
#: services in cases that were never emergencies.
#:
#: So this acknowledges, says plainly what consent is, leaves the decision with
#: her, and *offers* somewhere to go. It does not send her anywhere.
PRESSURE = (
    "Thank you for telling me. What you're describing is pressure, and it "
    "counts even though he hasn't forced you.\n\n"
    "Sex is something you choose freely, or it isn't really a choice. Agreeing "
    "because you're afraid he'll leave, or get angry, or keep on asking until "
    "you give in, is not the same as wanting to. Saying no is allowed as many "
    "times as you need to say it, and you don't have to decide anything today.\n\n"
    "Do you want to talk through what he's been saying, and what would help you "
    "feel safer?"
)

#: Offered alongside the concern tier, and only as an option she can ignore.
PRESSURE_FOLLOWUP = (
    "If you'd rather talk to someone outside the relationship, there are "
    "confidential places you can contact. Only if you want them."
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
#: The contacts are no longer written here. They are read from the verified
#: table and appended, which makes this file consistent with the rule the rest
#: of the system already follows: a contact is a table read, never text. Two
#: numbers were hardcoded in this string, and the same two now sit in
#: services.csv -- so the only thing that changed is which copy is authoritative,
#: and there is now one.
SELF_HARM = (
    "Thank you for telling me. That sounds really heavy, and I'm glad you said "
    "it rather than carrying it alone.\n\n"
    "Please tell someone near you now, or go to the nearest health facility. "
    "These people are there for exactly this, any time:"
)

#: Topics deliberately outside this service. Not a failure, and it should not
#: read like one.
OUT_OF_SCOPE = (
    "That's outside what I can help with. I stick to contraception, sexual "
    "health, staying safe, and finding services, because those are what I'm "
    "here for.\n\n"
    "For anything medical about your own body, like what's causing something, which "
    "method is right for you, or how much of anything to take, a nurse or "
    "clinician is the right person, and they won't turn you away.\n\n"
    "Is there something in what I do cover that I can help with?"
)

#: The corpus was searched and could not support an answer. Deliberately not the
#: same as out-of-scope: telling her "I don't cover that" when the topic *is*
#: covered and the search simply failed teaches her the service has nothing.
NO_EVIDENCE = (
    "I don't have anything solid enough in my sources to answer that properly, "
    "and I'd rather say so than guess.\n\n"
    "Try asking it a different way, or ask me something nearby. I can help with "
    "contraception methods, condoms and HIV, getting to a clinic, or what to "
    "expect when you go."
)

#: The system produced an answer and then rejected its own draft. Distinct from
#: NO_EVIDENCE, because the corpus *did* cover it and the fault is ours.
BLOCKED = (
    "Sorry, I had trouble putting that answer together properly, so I'd rather "
    "not send it half-right.\n\n"
    "Try asking again, or in a slightly different way?"
)

TECHNICAL = (
    "Something went wrong on my side just now. Please try again in a moment."
)

#: Nothing usable arrived. Says so without implying she did something wrong.
EMPTY_INPUT = "I didn't catch that. What would you like to ask?"

TOO_LONG = (
    "That's a lot to read in one go and I'd rather not answer half of it.\n\n"
    "Could you send me the main thing you want to know?"
)


#: She disclosed something, and then asked where to go — with no subject of her
#: own in the question. "Where can I go?" after telling you her boyfriend
#: pressures her is not a question about contraception, and answering it from
#: the corpus is how the demo's most important turn became a refusal: it
#: resolved against her earlier question about the implant, searched for implant
#: passages, found nothing about *where*, and declined.
#:
#: A human aunti would not look anything up here. She would answer the question
#: the girl is actually asking, which is who can help me.
WHERE_TO_GO_AFTER_DISCLOSURE = (
    "For what you've just told me, the people who can actually help are real "
    "people, not a service like me.\n\n"
    "**A health worker at any clinic.** They see this often, they won't judge "
    "you, and you don't need a parent with you.\n"
    "**A teacher or an adult you already trust.** Someone who knows you and "
    "can stay with it.\n"
    "**A helpline**, if you'd rather talk to someone who doesn't know you.\n\n"
    "You don't have to explain it as well as you just did to me. Saying "
    "\"someone is pressuring me\" is enough to start."
)
