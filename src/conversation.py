"""Conversation state. Bounded, deterministic, no model.

A girl does not arrive with a query. She arrives with a conversation, and it
moves: contraception, then what she wants to be, then something he said, then
where she can actually go. The previous version of this file did not exist,
and the measurement for why it now does is blunt --

    "and does it hurt?"   asked after a question about the implant,
                          retrieved **female sterilization** at 0.593
    "where can I go?"     asked after disclosing coercion,
                          retrieved **BTL** -- permanent sterilisation -- at 0.508
    "is it free?"         retrieved "Clients rights" at 0.484

A follow-up fragment carries its meaning in the turn before it. Answering it
alone is not a degraded answer, it is an answer to a different question, and in
two of those three cases the different question was about being sterilised.

What this is not: a memory system. There is no summarisation model, no entity
tracker, no vector store of past turns, no profile that accumulates. It is the
last few turns, one resolved topic, and one flag, all of them derived by rules
you can read in a minute. Anything more would be the thing this build exists to
stop doing.

**Three boundaries hold, and they are the design:**

1. *The decision is still made on her words alone.* Context expands what gets
   searched; it never decides whether a turn is a disclosure. A safety floor
   that depends on conversational state is a safety floor with a state bug in
   it.
2. *Resolution touches the retrieval query only.* What the generator answers is
   what she actually typed -- the same split that made query preparation safe.
3. *It is bounded and it forgets.* Six turns, in memory, for the length of one
   session. Nothing is written down about her.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: How many turns the history block can hold. Six is three exchanges -- enough
#: for a follow-up chain to resolve, short enough that the prompt does not start
#: competing with the passages for the model's attention.
MAX_TURNS = 6

#: Words that carry a subject on their own. A message containing one of these is
#: standing on its own feet and needs no antecedent. Drawn from the scope --
#: methods, services, and the situations the corpus covers.
_CONTENT = re.compile(
    r"\b(implant|injection|depo|iud|coil|pill|pills|condom|condoms|"
    r"contracepti\w+|family planning|fp|emergency|p2|morning after|"
    r"sterilis\w+|steriliz\w+|btl|vasectomy|"
    r"pregnan\w+|period|periods|bleeding|fertil\w+|infertil\w+|"
    r"hiv|sti|std|test|testing|prep|"
    r"clinic|hospital|chemist|pharmacy|nurse|doctor|health worker|"
    r"boyfriend|partner|husband|school|parents?|mum|mother|dad|father)\b",
    re.IGNORECASE,
)

#: Openings that point backwards explicitly. "What about the injection" has a
#: content word and still depends on the turn before it for what is being asked
#: *about* the injection.
_BACKREF = re.compile(
    r"^\s*(and|but|so|ok|okay|then|also|what about|how about|"
    r"what if|and what|and how|is it|does it|do they|will it|can it|"
    r"how about it|that one|the other one)\b",
    re.IGNORECASE,
)

#: A pronoun with nothing in the message for it to refer to.
_DANGLING = re.compile(r"\b(it|that|this|them|those|they|one)\b", re.IGNORECASE)

#: Above this, a message is long enough to carry its own context.
_SHORT_WORDS = 9


@dataclass
class Turn:
    role: str          # "her" | "aunti"
    text: str
    path: str | None = None


@dataclass
class Conversation:
    """Everything the system remembers, which is deliberately very little."""

    turns: list[Turn] = field(default_factory=list)

    # --- recording -----------------------------------------------------------
    def record_her(self, text: str, path: str | None = None) -> None:
        self.turns.append(Turn("her", text, path))
        self._remember_topic(text, path)
        self._trim()

    def record_aunti(self, text: str, path: str | None = None) -> None:
        self.turns.append(Turn("aunti", text, path))
        self._trim()

    def _trim(self) -> None:
        if len(self.turns) > MAX_TURNS:
            del self.turns[:-MAX_TURNS]

    # --- what it knows -------------------------------------------------------
    #: The last thing she said that could serve as an antecedent -- a turn that
    #: stood on its own and went to the corpus. Held separately from `turns`
    #: rather than searched out of it, because the turn window is trimmed and
    #: the subject is not: in the reviewer's own journey she asked about the
    #: implant, talked about school, disclosed coercion twice, and then asked
    #: "where can I go?" -- by which point the implant question had been trimmed
    #: away and the fragment resolved against nothing. Topic outlives the
    #: transcript, which is the whole reason it is a separate field.
    topic: str | None = None

    def _remember_topic(self, text: str, path: str | None) -> None:
        if path in ("factual", "access") and not is_dependent(text):
            self.topic = text

    @property
    def disclosed(self) -> bool:
        """She has disclosed harm at some point in this conversation.

        Sticky on purpose. A girl who told you about coercion three turns ago
        and now asks where to go is not an anonymous first-time asker, and the
        service handoff should not treat her as one. It never *downgrades*
        anything -- the floor is re-evaluated on her words every turn regardless.
        """
        return any(t.role == "her" and t.path == "safeguarding" for t in self.turns)

    @property
    def is_first_turn(self) -> bool:
        return not any(t.role == "aunti" for t in self.turns)

    def history_block(self) -> str:
        """The transcript as the prompts already expect it.

        Both prompt files have carried a `{history_block}` slot and a "you are in
        a conversation, do not re-introduce yourself" rule since the previous
        build. The pipeline passed an empty string into it, so a model told not
        to repeat itself was given no way to know what it had already said.
        """
        if not self.turns:
            return ""
        lines = [f"{'She' if t.role == 'her' else 'You'}: {t.text.strip()}"
                 for t in self.turns]
        return "Earlier in this conversation:\n" + "\n".join(lines) + "\n\n"


def is_dependent(message: str) -> bool:
    """Does this message need the turn before it to mean anything?

    Conservative by construction: a message that names its own subject is left
    alone, because the cost of resolving one that did not need it (a slightly
    longer query) is far below the cost of missing one that did (an answer about
    sterilisation).
    """
    text = message.strip()
    if not text:
        return False
    if len(text.split()) > _SHORT_WORDS:
        return False
    # Content first, and the order is load-bearing. "what about the injection"
    # opens with a backreference and still names its own subject; resolving it
    # against a question about the implant put both methods in one query and the
    # implant won -- she asked about the injection and would have been answered
    # about implants. A message that names a method is about that method.
    if _CONTENT.search(text):
        return False
    if _BACKREF.search(text):
        return True
    # Short, no subject of its own. Either it dangles a pronoun, or it is a bare
    # question like "where can I go?" -- which has no pronoun and no subject.
    return bool(_DANGLING.search(text)) or text.endswith("?")


@dataclass(frozen=True)
class Resolved:
    text: str
    original: str
    resolved: bool
    antecedent: str | None = None


def resolve(message: str, conversation: Conversation | None,
            *, retrieves: bool = True) -> Resolved:
    """Give a dependent fragment its antecedent, for retrieval only.

    The antecedent is prepended rather than substituted into the sentence.
    Substitution needs to know which noun the pronoun refers to and would be a
    parser; prepending needs to know nothing and puts both turns in front of the
    encoder, which is all a bi-encoder needs.

    `retrieves` is the same gate query preparation uses, for the same reason: a
    turn that never reaches the corpus has no query to resolve. Without it,
    *"he took it off last time without telling me"* -- a disclosure that is
    answered from approved text and never searched -- was being silently
    rewritten against a question about the injection.
    """
    if conversation is None or not retrieves:
        return Resolved(message, message, False)
    topic = conversation.topic
    if not topic or not is_dependent(message):
        return Resolved(message, message, False)
    return Resolved(f"{topic} {message}", message, True, topic)
