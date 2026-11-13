"""Tests for event journal and idempotent resume."""

from crocodile.gateway.journal import EventJournal


def test_journal_append_and_replay(tmp_path):
    db_path = tmp_path / "journal_test.db"
    j = EventJournal(db_path)

    seq1 = j.append("session-1", "session_started", {"repo": "test"})
    seq2 = j.append("session-1", "model_request", {"model": "haiku"})
    seq3 = j.append("session-1", "model_response", {"cost": 0.002})

    assert seq1 == 1
    assert seq2 == 2
    assert seq3 == 3

    events = j.get_events("session-1")
    assert len(events) == 3
    assert events[0]["type"] == "session_started"
    assert events[2]["payload"]["cost"] == 0.002


def test_idempotent_resume_outcomes(tmp_path):
    db_path = tmp_path / "journal_resume.db"
    j = EventJournal(db_path)

    # Tool started but process crashed before tool_result!
    j.append("session-crash", "tool_started", {"call_id": "call_99", "snapshot": "git_sha_abc"})

    state = j.resume("session-crash")
    # Resume must append an OUTCOME UNKNOWN result
    updated_events = j.get_events("session-crash")
    last_event = updated_events[-1]
    assert last_event["type"] == "tool_result"
    assert last_event["payload"]["call_id"] == "call_99"
    assert last_event["payload"]["status"] == "unknown"
    assert "OUTCOME UNKNOWN" in last_event["payload"]["error"]
