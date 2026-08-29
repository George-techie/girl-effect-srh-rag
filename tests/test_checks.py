"""The deterministic validator, in both directions.

A fatal check has two ways to fail and only one of them is loud. Letting a
fabricated phone number through is the failure everyone tests for. Firing on a
page number is the failure nobody tests for, and it produces a refusal — which
is the outcome this build exists to stop repeating.

The phone rule was rewritten after being run over the corpus: the old short-code
half matched 9 chunks, all of them page references. Both halves are asserted
here so that stays fixed.
"""

from __future__ import annotations

import pytest

from src.safety import checks


class TestPhoneNumbers:
    @pytest.mark.parametrize("draft", [
        "Call Befrienders on +254 722 178 177 if you need to talk",
        "You can reach them on 0722178177 any time",
        "Dial 1199 for free counselling",
        "Call the helpline on 116, it is free",
        "The number is 116 - toll free",
    ])
    def test_fabricated_contacts_are_fatal(self, draft):
        issues, fatal = checks.check(draft, n_passages=0, grounded=False)
        assert fatal
        assert any("came from no source" in i for i in issues)

    @pytest.mark.parametrize("draft", [
        "See LNG-IUD for Women With HIV, p. 199 for the detail",
        "There is more on this at see Question 2, p. 116 in the guide",
        "Health and Human Rights 18(2): 195-208 covers the same ground",
        "The department recorded just 116 cases that year",
    ])
    def test_page_references_are_not_phone_numbers(self, draft):
        """The regression. Every one of these appears in the corpus, and each
        used to be a fatal block."""
        assert not checks.PHONE.search(draft), draft

    def test_no_corpus_chunk_matches(self):
        """The claim the README makes, asserted rather than believed."""
        from src.rag import indexing
        docs = indexing.get_collection().get(include=["documents"])["documents"]
        offenders = [d[:80] for d in docs if checks.PHONE.search(d)]
        assert not offenders, offenders


class TestMachineryTalk:
    def test_machinery_talk_is_recorded_not_blocked(self):
        issues, fatal = checks.check(
            "The passages I have don't cover what it costs, but a clinic can "
            "tell you when you ask, and asking costs nothing at all [S1].",
            n_passages=2,
        )
        assert not fatal, "an awkward answer must not become a refusal"
        assert any("machinery" in i for i in issues)

    def test_a_clean_grounded_answer_has_no_issues(self):
        issues, fatal = checks.check(
            "No, family planning does not cause infertility [S1]. Your ability "
            "to get pregnant comes back after you stop, and a nurse at any "
            "clinic can talk you through which method suits you [S2].",
            n_passages=2,
        )
        assert not fatal
        assert not issues


class TestLivedExperience:
    def test_empathy_passes_and_claimed_experience_does_not(self):
        ok = ("I hear what you're going through, and it makes sense that it "
              "feels heavy right now, so let's take it one step at a time [S1].")
        assert not checks.check(ok, n_passages=1)[1]

        claimed = ("I've been there myself and I know exactly how that feels, "
                   "so here is what the guidance says about it [S1].")
        assert checks.check(claimed, n_passages=1)[1]
