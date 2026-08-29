"""The gate matters more than the mappings.

A mapping that fires on the wrong turn is the failure Experiment 2 measured:
restating a support turn moved retrieval from material written for her to policy
literature about her, and restating an out-of-scope question made it retrieve
*more* confidently. So these tests spend most of their attention on when the
layer stays out of the way.
"""

from __future__ import annotations

import re

from src.decision import rules
from src.rag import query_prep


def prepared_for(message: str) -> query_prep.PreparedQuery:
    """What the pipeline would actually build, gate included."""
    return query_prep.prepare(message, restate=rules.decide(message).restate)


class TestGate:
    def test_support_turns_are_untouched(self):
        for message in [
            "I am pregnant and scared to tell anyone",
            "I feel so alone since my friends found out",
        ]:
            assert prepared_for(message).text == message

    def test_safeguarding_turns_are_untouched(self):
        message = "My boyfriend says he'll leave me if I don't stop taking the pill"
        assert prepared_for(message).text == message

    def test_out_of_scope_turns_are_untouched(self):
        # The boundary case that retrieved *more* confidently under the oracle.
        message = "My periods have been irregular for three months"
        assert prepared_for(message).text == message

    def test_chat_turns_are_untouched(self):
        assert prepared_for("hello aunti").text == "hello aunti"

    def test_factual_turn_with_no_matching_mapping_is_untouched(self):
        message = "Does the implant work"
        result = prepared_for(message)
        assert result.text == message
        assert not result.restated


class TestExpansion:
    def test_her_words_survive_in_full(self):
        message = "Can I get family planning without my parents knowing"
        result = prepared_for(message)
        assert result.restated
        assert result.text.startswith(message)
        assert "informed consent" in result.text

    def test_original_is_kept_verbatim(self):
        message = "Can I get it if I am not married"
        assert prepared_for(message).original == message

    def test_mappings_are_reported_for_the_trace(self):
        result = prepared_for("Can I get family planning without my parents knowing")
        assert result.applied
        assert all(a.startswith(("evidenced:", "extrapolated:"))
                   for a in result.applied)


class TestPatternIntegrity:
    """Regex written through a shell heredoc silently becomes backspace bytes.

    This has happened five times in this project: ``\\b`` collapses to 0x08, the
    pattern still compiles, and it matches nothing. A mapping that never fires
    costs nothing visible, which is exactly why it needs a test.
    """

    def test_no_control_characters_in_patterns(self):
        for pattern, addition, kind in query_prep._EXPANSIONS:
            assert not any(ord(c) < 32 for c in pattern), repr(pattern)
            assert kind in {"evidenced", "extrapolated"}
            assert addition.strip()

    def test_every_pattern_compiles_and_fires_on_something(self):
        for pattern, _, _ in query_prep._EXPANSIONS:
            re.compile(pattern)
