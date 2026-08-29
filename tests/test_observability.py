"""Events, invariants, and the two properties that make them safe to ship.

A monitoring layer earns its place by catching things. It loses its place the
moment it can break a turn or leak a disclosure, so both are pinned here.
"""

from __future__ import annotations

import json

import pytest

from src import observability as obs


@pytest.fixture
def events_file(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(obs, "EVENTS", path)
    monkeypatch.setattr(obs, "ENABLED", True)
    return path


def read_one(path):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    return json.loads(lines[0])


class TestPrivacy:
    """The default must be safe, because a safeguarding product's event log is
    otherwise a database of adolescent girls' disclosures."""

    def test_her_words_are_not_written_by_default(self, events_file, monkeypatch):
        monkeypatch.setattr(obs, "TRACE_MESSAGES", False)
        secret = "my boyfriend took the condom off without telling me"
        obs.record(trace={"llm_calls": 0, "latency_ms": 3}, reply_path="safeguarding",
                   n_sources=0, text="Thank you for telling me.", message=secret)
        raw = events_file.read_text(encoding="utf-8")
        assert secret not in raw
        assert "Thank you for telling me" not in raw

    def test_the_event_is_still_useful_without_them(self, events_file, monkeypatch):
        monkeypatch.setattr(obs, "TRACE_MESSAGES", False)
        obs.record(trace={"llm_calls": 0, "latency_ms": 3}, reply_path="safeguarding",
                   n_sources=0, text="x", message="secret")
        event = read_one(events_file)
        assert event["path"] == "safeguarding"
        assert event["stage"] == "safeguarding"
        assert event["latency_ms"] == 3

    def test_opting_in_records_them(self, events_file, monkeypatch):
        monkeypatch.setattr(obs, "TRACE_MESSAGES", True)
        obs.record(trace={"llm_calls": 1}, reply_path="factual", n_sources=1,
                   text="reply", message="does the implant hurt")
        assert read_one(events_file)["message"] == "does the implant hurt"


class TestNeverBreaksATurn:
    def test_an_unwritable_path_is_swallowed(self, monkeypatch, tmp_path):
        monkeypatch.setattr(obs, "EVENTS", tmp_path / "nope" / "\0" / "bad.jsonl")
        monkeypatch.setattr(obs, "ENABLED", True)
        # Must not raise. A girl's answer does not depend on a log file.
        obs.record(trace={}, reply_path="chat", n_sources=0, text="hi", message="hi")

    def test_invariants_are_returned_not_raised(self):
        violations = obs.check_invariants(
            {"contract": "conversational"}, "chat", n_sources=3, text="hello")
        assert violations
        assert isinstance(violations, list)


class TestInvariants:
    """Each of these exists because something in this codebase went wrong in
    exactly that shape."""

    def test_a_path_that_must_not_search_is_caught_searching(self):
        names = [v.name for v in obs.check_invariants(
            {"retrieved": [{"similarity": 0.6}]}, "safeguarding", 0, "text")]
        assert "searched_on_a_path_that_must_not" in names

    def test_a_grounded_answer_with_no_sources_is_caught(self):
        names = [v.name for v in obs.check_invariants(
            {"contract": "grounded", "retrieved": [{}]}, "factual", 0, "an answer")]
        assert "grounded_answer_without_sources" in names

    def test_a_conversational_answer_with_sources_is_caught(self):
        names = [v.name for v in obs.check_invariants(
            {"contract": "conversational"}, "chat", 2, "hello")]
        assert "conversational_answer_with_sources" in names

    def test_a_dead_signal_is_caught(self):
        """The previous build set `urgent` on a template and nothing read it,
        so a girl at risk of self-harm saw less than one who disclosed something
        less dangerous."""
        names = [v.name for v in obs.check_invariants(
            {"help_requested": True}, "factual", 1, "text")]
        assert "help_request_outside_safeguarding" in names

    def test_an_unresolved_fragment_is_caught(self):
        """The trimmed-topic defect, which was invisible until printed by hand."""
        names = [v.name for v in obs.check_invariants(
            {"dependent": True, "contract": "grounded", "retrieved": [{}]},
            "factual", 1, "text")]
        assert "unresolved_fragment" in names

    def test_a_second_model_call_is_caught(self):
        names = [v.name for v in obs.check_invariants(
            {"llm_calls": 2}, "factual", 1, "text")]
        assert "more_than_one_model_call" in names

    def test_a_healthy_turn_violates_nothing(self):
        assert not obs.check_invariants(
            {"contract": "grounded", "llm_calls": 1, "retrieved": [{"similarity": 0.7}],
             "dependent": False},
            "factual", n_sources=2, text="No, it does not cause infertility.")


class TestStages:
    def test_every_path_maps_to_a_stage(self):
        from src.decision import rules
        for path in (rules.CHAT, rules.FACTUAL, rules.ACCESS, rules.SUPPORT,
                     rules.SAFEGUARDING, rules.OUT_OF_SCOPE):
            assert path in obs.STAGE, path

    def test_access_is_the_theory_of_change_terminus(self):
        assert obs.STAGE["access"] == "service_access"


class TestReading:
    def test_a_truncated_line_does_not_break_the_reader(self, events_file):
        events_file.write_text(
            '{"path": "chat"}\n{"path": "fact\n{"path": "access"}\n',
            encoding="utf-8")
        assert [e["path"] for e in obs.read(events_file)] == ["chat", "access"]

    def test_a_missing_file_reads_as_empty(self, tmp_path):
        assert obs.read(tmp_path / "absent.jsonl") == []
