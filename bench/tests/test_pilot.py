"""Synthetic pilot policy/evidence tests; no services, exercises or credentials."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from bench import pilot
from bench.run import _append, _rows


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    proof = {"canonical_config_id": pilot.V4_ID, "runtime_drift": [], "worktree_clean": True,
             "canonical_publication_git_commit": "synthetic", "task_ids": pilot.TASKS,
             "task_count": 3, "run_count": 15, "run_ids": [f"synthetic-{i}" for i in range(15)],
             "selection": {"shard": "1/4", "limit": 3}, "scope": "development-smoke",
             "execution_authorized": False, "canonical_comparability_ready": False,
             "effective_mini_identity": {"synthetic": True}}
    monkeypatch.setattr(pilot, "attest_plan", lambda *a, **k: deepcopy(proof))
    calls = []

    def dispatch(plan, output, **kwargs):
        calls.append(kwargs)
        output.mkdir(exist_ok=True)
        if not (output / "results.jsonl").exists():
            for i in range(15):
                status = "blocked" if i == 0 else "completed"
                _append(output / "results.jsonl", {"attempt_id": str(i), "run_id": f"synthetic-{i}",
                        "status": status, "solved": i > 0, "grading": None if i == 0 else {"solved": True},
                        "agent_claimed_solved": i > 0, "session_id": f"synthetic-session-{i}"})
        return _rows(output / "results.jsonl")

    monkeypatch.setattr(pilot, "run_plan", dispatch)
    options = {"oracles": {}, "config": tmp_path / "config.json", "data_root": tmp_path / "inputs",
               "mini_adapter": SimpleNamespace(identity=lambda: {"synthetic": True})}
    return SimpleNamespace(proof=proof, calls=calls, options=options, output=tmp_path / "pilot",
                           plan=tmp_path / "plan.json")


@pytest.mark.parametrize("field,value", [
    ("task_count", 54), ("run_count", 270), ("task_ids", ["quixbugs/kheapsort"]),
    ("worktree_clean", False), ("runtime_drift", ["synthetic drift"]),
    ("canonical_config_id", "forged"), ("execution_authorized", True),
    ("effective_mini_identity", None), ("run_ids", ["duplicate"] * 15),
    ("selection", {"shard": "1/4", "limit": None}),
])
def test_invalid_scope_never_creates_output_or_dispatches(fixture, field, value):
    fixture.proof[field] = value
    with pytest.raises(ValueError, match="Pilot requires"):
        pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    assert not fixture.calls and not fixture.output.exists()


def test_incomplete_only_ledger_preserves_raw_grades_blockers_and_resume(fixture):
    rows = pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    raw = (fixture.output / "raw-execution/results.jsonl").read_bytes()
    assert len(rows) == 15 and rows[0]["observed_execution_status"] == "blocked"
    assert rows[0]["grading"] is None and rows[1]["grading"]["solved"] is True
    assert rows[1]["observed_graded_solved"] is True
    assert all(r["status"] == "incomplete" and r["solved"] is None and not r["complete"]
               and not r["eligible_for_pooled_report"] and not r["authoritative_cost_complete"] for r in rows)
    assert pilot.run_pilot(fixture.plan, fixture.output, **fixture.options) == rows
    assert (fixture.output / "raw-execution/results.jsonl").read_bytes() == raw
    assert len({r["attempt_id"] for r in rows}) == 15
    assert (fixture.output / "pilot-attestation.json").exists()


def test_interruption_collects_partial_evidence_and_releases_only_own_lock(fixture, monkeypatch):
    def interrupted(plan, output, **kwargs):
        output.mkdir()
        _append(output / "results.jsonl", {"attempt_id": "partial", "status": "interrupted", "solved": False})
        raise KeyboardInterrupt()
    monkeypatch.setattr(pilot, "run_plan", interrupted)
    with pytest.raises(KeyboardInterrupt):
        pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    rows = _rows(fixture.output / "pilot-results.jsonl")
    assert len(rows) == 1 and rows[0]["status"] == "incomplete" and rows[0]["solved"] is None
    assert rows[0]["observed_execution_status"] == "interrupted"
    assert not (fixture.output / ".pilot.lock").exists()


def test_resume_cannot_change_attestation(fixture):
    pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    fixture.proof["effective_mini_identity"] = {"different": True}
    with pytest.raises(ValueError, match="identical attestation"):
        pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    assert len(fixture.calls) == 1


def test_oracle_error_at_real_attestation_boundary_never_dispatches(fixture, monkeypatch):
    def refused(*args, **kwargs):
        raise ValueError("Oracle subset differs from frozen originals")
    monkeypatch.setattr(pilot, "attest_plan", refused)
    with pytest.raises(ValueError, match="Oracle subset"):
        pilot.run_pilot(fixture.plan, fixture.output, **fixture.options)
    assert not fixture.output.exists() and not fixture.calls


def test_cli_does_not_execute_without_both_operator_flags(tmp_path):
    args = ["--plan", "p", "--oracles", "o", "--output", str(tmp_path / "out"),
            "--canonical-data-root", "d", "--mini-settings", "m"]
    for flag in ([], ["--execute"], ["--accept-incomplete"]):
        with pytest.raises(SystemExit) as error:
            pilot.main(args + flag)
        assert error.value.code == 2
    assert not (tmp_path / "out").exists()
