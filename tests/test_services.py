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
