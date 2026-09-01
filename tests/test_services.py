"""The service handoff. The turn the whole Theory of Change ends at.

Girl Effect's Theory of Change runs behavioural drivers -> intent -> **service
access** -> behaviour change. Knowledge is one driver of eight, and a system
that answers every question beautifully and never gets her to a service has
done the easy half and stopped.

These tests exist because that handoff was missing while everything around it
looked finished. `_with_contacts` was wired into the safeguarding paths only, so
*"where can I get family planning?"* returned a correct, cited explanation of
what kind of provider exists and no number to call -- while Marie Stopes and
One2One sat in the verified table, unused.
"""

from __future__ import annotations

import pytest

from src import pipeline, services
from src.conversation import Conversation
from src.decision import rules


class TestTheTableItself:
    def test_every_row_is_verified(self):
        """Nothing unverified ships. The gate is the point of the table."""
        rows = services._load()
        assert rows, "no verified services -- the handoff cannot work"
        assert all(s.contact.strip() for s in rows)

    def test_the_routes_the_pipeline_asks_for_all_have_a_row(self):
        """A route the code can request but the table cannot answer is a
        silent dead end: she asks, and gets guidance with no number."""
        missing = [r for r in sorted(pipeline._KNOWN_ROUTES)
                   if not services.for_route(r)]
        assert not missing, f"routes with no verified service: {missing}"

    def test_text_capable_services_rank_first(self):
        """A girl on a shared phone, in a room with family, often cannot make a
        call. A row she can text is worth more to her than another hotline."""
        for route in ("contraception", "sexual_violence"):
            found = services.for_route(route)
            if len(found) > 1 and any(s.textable for s in found):
                assert found[0].textable, route

    def test_a_contact_is_never_generated(self):
        """Every character of a rendered contact comes from a column."""
        for service in services._load():
            assert service.contact in service.render()
            assert service.name in service.render()


class TestAccessReachesAService:
    """The gap this file was written for."""

    @pytest.mark.parametrize("message,route", [
        ("Where can I get family planning near me?", "contraception"),
        ("where can i go for an HIV test?", "hiv_sti"),
        ("i am pregnant, where do i go?", "pregnancy_support"),
    ])
    def test_the_route_is_read_off_her_words(self, message, route):
        assert pipeline._access_route(message) == route

    def test_an_access_turn_ends_with_a_real_contact(self):
        reply = pipeline.answer("Where can I get family planning near me?",
                                conversation=Conversation())
        assert reply.path == rules.ACCESS
        assert isinstance(reply.trace.get("services"), list)
        assert reply.trace["services"], "no service reached her"
        # The number itself, not a description of one.
        contacts = [s.contact for s in services.for_route("contraception")]
        assert any(c in reply.text for c in contacts)

    def test_a_factual_turn_does_not_get_a_service_list(self):
        """Only an access question gets contacts. Appending a helpline to
        "does the implant hurt" is noise, and noise is how a girl learns to
        skip the end of every message."""
        reply = pipeline.answer("Does the implant hurt?",
                                conversation=Conversation())
        assert reply.path == rules.FACTUAL
        assert not isinstance(reply.trace.get("services"), list)


class TestSafeguardingReachesAService:
    def test_urgent_puts_contacts_in_front_of_her(self):
        reply = pipeline.answer("He forced me and I did not want to")
        assert reply.trace["tier"] == "urgent"
        assert isinstance(reply.trace.get("services"), list)
        contacts = [s.contact for s in services.for_route("sexual_violence")]
        assert any(c in reply.text for c in contacts)

    def test_self_harm_gets_the_self_harm_row_not_a_generic_one(self):
        reply = pipeline.answer("i dont want to be here anymore")
        assert reply.trace["services"], "no crisis contact reached her"
        expected = {s.service_id for s in services.for_route("self_harm_risk")}
        assert set(reply.trace["services"]) <= expected

    def test_a_concern_offers_rather_than_pushes(self):
        reply = pipeline.answer("my boyfriend is pressuring me to have sex")
        assert reply.trace["tier"] == "concern"
        assert reply.followup is not None
        contacts = [s.contact for s in services.for_route("sexual_violence")]
        assert any(c in reply.followup for c in contacts)
        assert not any(c in reply.text for c in contacts), \
            "contacts belong behind the tap on a concern, not in the opening"


class TestWhereQuestionsAlwaysReachAService:
    """The Theory of Change ends at service access, so "where can I go" must
    never be a dead end. Two bugs conspired to make it one.

    First the routing: `where (can|do) i (get|go|find)` is a fixed form, and she
    writes "where can i ACTUALLY go to get it". That became `factual`, so the
    service table was never consulted.

    Then the handoff: even routed correctly, the corpus cannot answer *where* --
    no document knows what is near her -- so the turn returned "I don't have
    anything solid enough in my sources" while Marie Stopes and One2One sat
    verified in the table two lines away.
    """

    @pytest.mark.parametrize("message", [
        "okay so where can i actually go to get it?",
        "where can i go to get it",
        "where do i even go for this",
        "where can i just get them",
        "where should i go to get the pill",
        "where can we find condoms",
        "where to get family planning",
    ])
    def test_however_she_phrases_it_the_turn_is_access(self, message):
        assert rules.decide(message).path == rules.ACCESS, message

    @pytest.mark.parametrize("message", [
        "where does the implant go in your arm",
        "where did you get that idea",
    ])
    def test_a_where_that_is_not_about_going_somewhere_is_not_access(self, message):
        assert rules.decide(message).path != rules.ACCESS, message

    def test_a_where_question_reaches_a_contact_even_after_other_turns(self):
        """The real shape: she talks first, then asks where."""
        from src.conversation import Conversation

        c = Conversation()
        c.record_her("does the implant stop you having children later", "factual")
        c.record_aunti("(answer about fertility returning)", "factual")

        reply = pipeline.answer("okay so where can i actually go to get it?",
                                conversation=c)
        assert reply.path == rules.ACCESS
        assert reply.trace.get("services"), "no service reached her"
        contacts = [s.contact for s in services.for_route("contraception")]
        assert any(c_ in reply.text for c_ in contacts), \
            "an access turn ended without a number she can call"


class TestListRendering:
    """A numbered list must number. Models put a blank line between items, which
    is correct markdown and was being read as separate paragraphs -- each became
    its own <ol>, so a three-item list rendered as 1. 1. 1.
    """

    REPLY = (
        "There are a few options worth thinking about:\n\n"
        "1. **Condoms.** The only method that protects against both.\n\n"
        "2. **Pills, injections, implants or IUDs.** Safe for young people.\n\n"
        "3. **Spermicides.** Among the least effective on their own.\n\n"
        "Would it help to talk through how to bring it up with him?"
    )

    def test_items_separated_by_blank_lines_are_one_list(self):
        from src.ui import theme
        html = theme.bubble(self.REPLY)
        assert html.count("<ol>") == 1, "the list restarted its numbering"
        assert html.count("<li>") == 3

    def test_the_lead_in_and_closing_stay_paragraphs(self):
        from src.ui import theme
        html = theme.bubble(self.REPLY)
        assert html.count("<p>") == 2

    def test_a_reply_with_no_list_is_untouched(self):
        from src.ui import theme
        html = theme.bubble("One thought.\n\nAnd another one.")
        assert "<ol>" not in html and html.count("<p>") == 2


class TestIntentBecomesAccess:
    """Girl Effect's Theory of Change runs drivers -> **intent** -> service
    access. A girl asking what happens at a test has already half-decided to go,
    and answering with an explanation alone leaves her where she started.

    The turn that prompted this: "yes please tell me what happens, i am actually
    very scared if i even see that sign" -- asked one turn after establishing it
    was about HIV. It returned a warm, cited answer and no way to act on it.
    """

    def test_asking_what_happens_about_testing_reaches_a_service(self):
        c = Conversation()
        c.record_her("could i have gotten HIV from that", "factual")
        c.record_aunti("(testing is the only way to know)", "factual")

        reply = pipeline.answer(
            "yes please tell me what happens, i am actually very scared",
            conversation=c)
        assert reply.trace.get("services"), "she asked, and got no way to act"
        contacts = [s.contact for s in services.for_route("hiv_sti")]
        assert any(x in reply.text for x in contacts)

    def test_the_topic_may_come_from_the_conversation(self):
        """The asking is in this message; the subject was established earlier."""
        assert pipeline._ready_to_act(
            "yes please tell me what happens", "could i have gotten HIV")
        assert not pipeline._ready_to_act("yes please tell me what happens", None)

    @pytest.mark.parametrize("message", [
        "what happens when i go for an HIV test",
        "can i just walk into a clinic and get the pill",
        "what do they ask at the clinic before testing",
    ])
    def test_weighing_up_a_visit_counts(self, message):
        assert pipeline._ready_to_act(message)

    @pytest.mark.parametrize("message", [
        "Does the implant hurt?",
        "does family planning make you infertile",
        "i am so scared someone will see me",
    ])
    def test_curiosity_and_feeling_alone_do_not(self, message):
        """Appending a helpline to every factual answer is noise, and noise is
        how she learns to skip the end of every message."""
        assert not pipeline._ready_to_act(message)


class TestAnAccessQuestionNeverRefuses:
    """The Theory of Change's terminus must not be left to chance.

    "where can i actually go for one?" refused on one run and succeeded on the
    next, at the single turn the whole conversation exists to reach. Whatever
    goes wrong with a generated draft, the answer to "where can I go" lives in
    the verified table rather than in the text, so the table can answer alone.
    """

    @pytest.mark.parametrize("message", [
        "where can i actually go for one?",
        "where can i get it near me?",
        "where do i even go for family planning",
    ])
    def test_it_always_ends_with_a_contact(self, message):
        from src.safety import responses

        reply = pipeline.answer(message, conversation=Conversation())
        assert reply.text not in (
            responses.BLOCKED, responses.NO_EVIDENCE, responses.TECHNICAL), \
            "an access question refused"
        assert reply.trace.get("services"), message
        contacts = [s.contact for s in services._load()]
        assert any(c in reply.text for c in contacts), message
