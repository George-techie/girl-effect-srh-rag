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

    def test_reported_coercion_is_caught_in_any_person(self):
        """D38 -- "he said if I really loved him I wouldn't make him use a
        condom" -- was the standing miss: coercion made only of a condition on
        her consent, and quoted second-hand rather than said to her face.

        The fix was not a pattern for that sentence. The rule already read the
        script in the second person; what it could not read was the script
        reported afterwards, which is how a girl actually tells you about it.
        So the person and direction were generalised, and these variants are
        the evidence it generalised rather than memorised -- none of them is
        the dataset's wording."""
        for message in [
            "He said if I really loved him I wouldn't make him use a condom.",
            "If you loved me you would not make me wear one, he keeps saying",
            "he tells me if i loved him i would trust him",
        ]:
            assert rules.decide(message).path == rules.SAFEGUARDING, message

    def test_affection_alone_is_not_coercion(self):
        """The other half of the same change. Generalising the person is only
        safe if it did not turn every sentence about loving someone into a
        disclosure -- precision on the benchmark stayed at 1.000, and these are
        the shapes closest to the new pattern."""
        assert rules.decide(
            "I love him so much and we are planning to go to college together"
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


class TestPatternIntegrity:
    """A guard against a bug that has now happened five times.

    Writing regex through a shell heredoc turns `\b` into a literal backspace
    byte (0x08). The module still imports, the patterns still compile, and they
    silently match nothing — which on the safeguarding families means
    disclosures route to `factual` with no error anywhere.
    """

    def test_no_control_characters_in_the_rule_source(self):
        from pathlib import Path

        import src.decision.rules as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        bad = {c for c in source if ord(c) < 32 and c not in "\n\t"}
        assert not bad, f"control characters in rules.py: {[hex(ord(c)) for c in bad]}"

    def test_every_safety_pattern_matches_something(self):
        """A pattern that can never fire is worse than no pattern: it reads as
        coverage in review and provides none."""
        import src.decision.rules as R

        for name, family in (("harm", R._HARM),
                             ("coercion", R._REPRODUCTIVE_COERCION),
                             ("third_party", R._THIRD_PARTY)):
            for pattern in family:
                assert "\x08" not in pattern.pattern, f"{name}: {pattern.pattern!r}"


class TestSelfHarmPhrasing:
    """The highest-consequence family in the file. "I don't want to be here"
    was caught and "I do not want to be here" was not — the same sentence, one
    apostrophe apart."""

    @pytest.mark.parametrize("message", [
        "I don't want to be here anymore.",
        "I do not want to be here anymore.",
        "I dont want to be here",
        "I do not want to live",
        "I don't want to live anymore",
    ])
    def test_both_contracted_and_expanded_forms_are_caught(self, message):
        assert rules.decide(message).path == rules.SAFEGUARDING


class TestHelpRequest:
    """Orthogonal to the path, never a replacement for it. A girl who asks for
    help in the same message as a disclosure must not be asked whether she
    wants help."""

    @pytest.mark.parametrize("message,path,asked", [
        ("Someone hurt me.", rules.SAFEGUARDING, False),
        ("Where can I get help if someone hurt me?", rules.SAFEGUARDING, True),
        ("My boyfriend forced me.", rules.SAFEGUARDING, False),
        ("Where can I get condoms?", rules.ACCESS, True),
        ("Can family planning make me infertile?", rules.FACTUAL, False),
    ])
    def test_signal_is_independent_of_route(self, message, path, asked):
        d = rules.decide(message)
        assert d.path == path
        assert d.help_requested is asked

    def test_a_girl_who_asked_is_not_asked_again(self):
        from src import pipeline

        asked = pipeline.answer("Where can I get help if someone hurt me?")
        assert asked.followup is None, "she already asked; do not offer a button"

        did_not_ask = pipeline.answer("My boyfriend forced me.")
        assert did_not_ask.followup is not None, "support first, offer the option"
