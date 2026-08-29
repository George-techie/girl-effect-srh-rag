"""Conversation state, and the three boundaries that make it safe.

The tests that matter most here are the ones asserting what context does *not*
do. Adding state to a system is how a safety floor acquires a state bug, and the
only defence is to pin the boundary in a test rather than in a comment.
"""

from __future__ import annotations

from src import conversation as conv
from src.decision import rules


def journey(*messages: str) -> conv.Conversation:
    """Replay messages the way the pipeline records them."""
    c = conv.Conversation()
    for m in messages:
        path = rules.decide(m).path
        c.record_her(m, path)
        c.record_aunti("(reply)", path)
    return c


class TestDependence:
    def test_fragments_need_their_antecedent(self):
        for message in ["and does it hurt?", "is it free?", "where can I go?",
                        "which one is better", "even at my age?"]:
            assert conv.is_dependent(message), message

    def test_a_message_that_names_its_subject_does_not(self):
        """The order of the checks in `is_dependent` is what this pins.

        "what about the injection" opens with a backreference *and* names a
        method. Resolving it against a question about the implant put both in
        one query and the implant won -- she asked about one method and would
        have been answered about another.
        """
        for message in ["what about the injection", "and the condom?",
                        "does the pill work", "where is the clinic"]:
            assert not conv.is_dependent(message), message

    def test_long_messages_carry_themselves(self):
        assert not conv.is_dependent(
            "My boyfriend has been saying things that make me uncomfortable "
            "and I do not know what to do about any of it"
        )


class TestTopic:
    def test_topic_outlives_the_turn_window(self):
        """The defect the reviewer's own journey exposed.

        She asked about the implant, talked about school, disclosed coercion
        twice, then asked "where can I go?". Six turns of window had trimmed the
        implant question away, so the fragment resolved against nothing.
        """
        c = journey(
            "Does the implant stop you from having children later?",
            "I want to be a doctor one day",
            "my boyfriend says if I really loved him I would not use anything",
            "he took it off last time without telling me",
        )
        assert len(c.turns) == conv.MAX_TURNS      # the window did trim
        assert c.topic is not None                 # the topic did not
        assert "implant" in c.topic

    def test_a_fragment_never_becomes_the_antecedent(self):
        c = journey("Does the implant hurt?", "and does it work?")
        assert c.topic == "Does the implant hurt?"

    def test_safeguarding_turns_are_not_topics(self):
        c = journey("my boyfriend took it off without telling me")
        assert c.topic is None


class TestBoundaries:
    def test_the_decision_never_reads_the_conversation(self):
        """Boundary 1. `rules.decide` takes a string and nothing else, so a
        disclosure cannot be missed because of what came before it."""
        import inspect
        params = list(inspect.signature(rules.decide).parameters)
        assert params == ["message"], params

    def test_resolution_is_skipped_on_paths_that_never_retrieve(self):
        """Boundary 2. A disclosure is answered from approved text and never
        searched, so there is no query to resolve -- and rewriting her
        disclosure against an earlier question about contraception would be
        both pointless and wrong."""
        c = journey("Does the implant hurt?")
        message = "he took it off last time without telling me"
        decision = rules.decide(message)
        assert decision.path == rules.SAFEGUARDING
        result = conv.resolve(message, c, retrieves=decision.retrieves)
        assert not result.resolved
        assert result.text == message

    def test_resolution_never_changes_what_she_said(self):
        c = journey("Does the implant stop you having children later?")
        result = conv.resolve("and does it hurt?", c)
        assert result.resolved
        assert result.original == "and does it hurt?"
        assert result.text.endswith("and does it hurt?")

    def test_it_is_bounded(self):
        c = journey(*[f"does the pill do thing number {i}" for i in range(20)])
        assert len(c.turns) == conv.MAX_TURNS

    def test_no_conversation_behaves_exactly_as_before(self):
        """Every single-turn evaluation in this repo depends on this."""
        result = conv.resolve("and does it hurt?", None)
        assert not result.resolved
        assert result.text == "and does it hurt?"


class TestDisclosureIsSticky:
    def test_disclosure_is_remembered_across_later_turns(self):
        c = journey("my boyfriend says if I really loved him I would not use anything")
        assert c.disclosed
        c.record_her("where can I go?", "access")
        assert c.disclosed, "a later ordinary turn must not clear it"

    def test_a_conversation_with_no_disclosure_says_so(self):
        assert not journey("Does the implant hurt?").disclosed


class TestHistoryBlock:
    def test_empty_before_anything_is_said(self):
        assert conv.Conversation().history_block() == ""

    def test_it_names_both_speakers(self):
        block = journey("Does the implant hurt?").history_block()
        assert "She: Does the implant hurt?" in block
        assert "You: (reply)" in block


class TestAspirations:
    """Her ambitions belong on the conversational contract. This was falling
    through to `factual` and being answered from contraception passages."""

    def test_ambitions_are_conversation(self):
        for message in [
            "I want to be a doctor one day, I am the first in my family to finish school",
            "my dream is to be a lawyer",
            "I passed my KCSE and got into college",
            "nataka kuwa daktari",
        ]:
            assert rules.decide(message).path == rules.CHAT, message

    def test_the_article_is_the_only_thing_separating_these(self):
        assert rules.decide("I want to be a doctor").path == rules.CHAT
        assert rules.decide("I want to be on the pill").path != rules.CHAT


class TestWhereToGoAfterDisclosure:
    """The demo's most important turn, and the one that was failing.

    She discloses coercion, then asks "where can I go?". The corpus has no
    answer to *where*, so it resolved against her earlier question about the
    implant, searched implant passages and refused -- at the exact moment she
    asked for help.
    """

    def test_a_fragment_after_a_disclosure_is_a_request_for_help(self):
        from src import pipeline
        from src.safety import responses
        c = journey(
            "Does the implant stop you having children later?",
            "my boyfriend says if I really loved him I would not use anything",
        )
        reply = pipeline.answer("where can I go?", conversation=c)
        assert reply.text == responses.WHERE_TO_GO_AFTER_DISCLOSURE
        assert reply.trace["llm_calls"] == 0

    def test_a_named_subject_is_still_a_real_access_question(self):
        """She may well still want the pill. Only a subjectless fragment is
        read as asking for help."""
        c = journey("my boyfriend says if I really loved him I would not use anything")
        assert not conv.is_dependent("where can I get the pill?")

    def test_without_a_disclosure_nothing_changes(self):
        c = journey("Does the implant stop you having children later?")
        assert not c.disclosed
