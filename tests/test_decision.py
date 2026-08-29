"""Decision-layer regressions.

Pinned because they are the cases the rules got wrong on the first run, and the
two contrasts the dataset was built around. A rule change that reintroduces any
of these should fail here rather than in an evaluation nobody reran.
"""

from __future__ import annotations

import json

import pytest

from src.decision import rules

DATASET = "evaluation/decisions_v1.jsonl"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return [json.loads(line) for line in open(DATASET, encoding="utf-8") if line.strip()]


class TestSafetyPath:

    @pytest.mark.parametrize("message", [
        "My uncle keeps touching me and says not to tell anyone.",
        "My friend told me her stepfather comes into her room at night.",
        "Chali yangu hunipiga then anaapologize later.",
        "My boyfriend says he'll leave me if I don't stop taking the pill.",
        "Where can I get help if someone hurt me?",
    ])
    def test_disclosures_reach_the_safety_path(self, message):
        assert rules.decide(message).path == rules.SAFEGUARDING

    def test_nothing_is_wrongly_routed_to_safety(self, rows):
        """Precision was 1.000 and should stay there. Over-routing a girl who
        asked an ordinary question into a safety response is a real cost."""
        wrong = [r["id"] for r in rows
                 if rules.decide(r["message"]).path == rules.SAFEGUARDING
                 and r["decision"] != rules.SAFEGUARDING]
        assert not wrong, wrong

    def test_implicit_coercion_is_still_missed(self, rows):
        """D38 -- "he said if I really loved him I wouldn't make him use a
        condom" -- is coercion made only of a condition on her consent, quoted
        second-hand. The rules do not catch it, and no pattern was added for it,
        because fitting a rule to one message in a set the same author wrote
        would measure nothing.

        This test asserts the *known limitation*, so that if a later change
        catches it the failure here is the prompt to check how."""
        assert rules.decide(
            "He said if I really loved him I wouldn't make him use a condom."
        ).path != rules.SAFEGUARDING


class TestContrasts:
    """The pairs the dataset exists for. Each separates two messages that share
    a surface form and need different paths."""

    @pytest.mark.parametrize("message,expected", [
        ("My boyfriend doesn't like condoms.", rules.SUPPORT),
        ("My boyfriend says he'll leave me if I don't stop taking the pill.",
         rules.SAFEGUARDING),
        ("Where can I get condoms in Nairobi?", rules.ACCESS),
        ("Where can I get help if someone hurt me?", rules.SAFEGUARDING),
        ("What will they ask me at the clinic?", rules.ACCESS),
        ("Is it normal to feel nervous before going to the clinic?", rules.SUPPORT),
        ("My periods have been irregular for three months.", rules.OUT_OF_SCOPE),
        ("I'm on the pill and I keep bleeding between periods, is that from the pill?",
         rules.FACTUAL),
    ])
    def test_pair(self, message, expected):
        assert rules.decide(message).path == expected


class TestScopeBoundary:

    @pytest.mark.parametrize("message", [
        "Which pill should I take?",
        "How many mg of the morning after pill should I take?",
        "I've had a rash since the implant. What's wrong with me?",
    ])
    def test_prescribing_and_diagnosis_stay_out_of_scope(self, message):
        """These all name a method, and the menstrual-symptom rescue used to
        pull them back in -- which is what took out-of-scope recall to 0.500."""
        assert rules.decide(message).path == rules.OUT_OF_SCOPE


class TestRestatementContract:
    """Experiment 2 measured that restatement helps factual and access turns and
    actively harms support and disclosure ones."""

    def test_only_factual_and_access_are_restated(self):
        assert rules.RESTATED == {rules.FACTUAL, rules.ACCESS}

    def test_support_and_safeguarding_keep_her_words(self):
        for message in ("I'm pregnant and I'm scared to tell anyone.",
                        "My boyfriend forced me and I didn't want to."):
            assert rules.decide(message).restate is False

    def test_out_of_scope_never_retrieves(self):
        assert rules.decide("What's the capital of Kenya?").retrieves is False


class TestInputValidation:
    """The front door. Rejects what cannot be answered, and changes nothing
    else -- she writes in Sheng, in lower case, with emoji, and all of that is
    valid input from the person this is built for."""

    from src.decision import input_validation as _iv

    @pytest.mark.parametrize("bad", ["", "   ", "\n\n", None, 12345])
    def test_unusable_input_is_rejected(self, bad):
        assert self._iv.validate(bad).ok is False

    def test_over_length_is_rejected_rather_than_truncated(self):
        """Truncating and answering would answer a question she did not finish
        asking."""
        result = self._iv.validate("a" * 5000)
        assert result.ok is False and "longer" in result.reason

    @pytest.mark.parametrize("good", [
        "hello aunti",
        "Ni kweli ati family planning inaharibu mji wa mtoto?",
        "naogopa 😰 kuuliza",
        "WHERE CAN I GET CONDOMS",
        "can i get fp without my parents?? 🙏",
    ])
    def test_her_language_passes_untouched(self, good):
        result = self._iv.validate(good)
        assert result.ok is True
        assert result.text == good
        assert result.original == good

    def test_only_whitespace_is_normalised(self):
        result = self._iv.validate("  hello   aunti\n\n  ")
        assert result.text == "hello aunti"
        assert result.original == "  hello   aunti\n\n  "

    def test_the_pipeline_rejects_before_any_model_call(self):
        from src import pipeline
        reply = pipeline.answer("   ")
        assert reply.path == "invalid_input"
        assert reply.trace["llm_calls"] == 0
