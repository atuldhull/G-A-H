"""Synthetic runner integration: injected agents/sessions, no live services."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bench import run as runner
from bench.plan import build_plan, write_manifest
from bench.prepare import populate_workspace


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = tmp_path / "dataset" / "exercise"
    source.mkdir(parents=True)
    (source / "solution.py").write_text("def answer(): return 0\n", encoding="utf-8")
    (source / "test_solution.py").write_text(
        "from solution import answer\ndef test_answer(): assert answer() == 42\n", encoding="utf-8"
    )
    (source / ".meta").mkdir()
    (source / ".meta" / "solution.txt").write_text("hidden synthetic solution", encoding="utf-8")
    (source / "nested" / ".meta").mkdir(parents=True)
    (source / "nested" / ".meta" / "answer.txt").write_text("hidden", encoding="utf-8")
    (source.parent / "prompt.txt").write_text("Fix the synthetic answer function.", encoding="utf-8")
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"schema_version": 1, "tasks": [{
        "dataset": "polyglot", "id": "synthetic", "source": "exercise", "task_file": "prompt.txt",
        "test_command": ["python", "-m", "pytest", "-q"],
    }]}), encoding="utf-8")
    plan = build_plan(index, polyglot=source.parent, dataset_set="polyglot")
    path = write_manifest(plan, tmp_path / "plan.json")
    state = SimpleNamespace(sessions=[], agents=[], grading=[], behavior="fix", ticks=0)

    class Session:
        def __init__(self, repo, *, parent, user_task):
            assert repo.parent == parent
            assert not list(repo.iterdir()), "session MUST precede every task copy"
            self.repo_root = repo
            self.identity = repo.stat().st_ino
            self.bench_auto = True
            self.events = [{"event": "bench_session_started"},
                           {"event": "approval", "token": "SYNTHETIC-PERMIT-NOT-FOR-PERSISTENCE"}]
            state.sessions.append(self)

        def close_bench(self):
            assert self.repo_root.stat().st_ino == self.identity
            assert self.bench_auto
            self.bench_auto = False
            self.events.append({"event": "bench_session_closed"})

    class Receipt:
        def __init__(self, sid):
            self.data = {"session": sid, "solved": False, "status": "UNVERIFIED", "steps": 0,
                         "usage": {"prompt_tokens": 20, "completion_tokens": 4, "cached_tokens": 3},
                         "models": ["synthetic/model"], "stubs": [], "cost_usd": 0.0123}

        def to_json(self):
            return dict(self.data)

    class Agent:
        def __init__(self, repo, task, **kwargs):
            assert kwargs["security_session"].repo_root == repo
            assert kwargs["security_session"].bench_auto
            assert kwargs["approve_mode"] == "auto"
            assert kwargs["oracle"] == ["test_solution.py"]
            assert kwargs["step_cap"] == 30
            assert "Test command: python -m pytest -q" in task
            assert not any(p.name == ".meta" for p in repo.rglob("*"))
            self.repo, self.kwargs = repo, kwargs
            self.s = SimpleNamespace(id=f"fake-{uuid4().hex}")
            self.r = Receipt(self.s.id)
            state.agents.append(self)

        def run(self):
            if state.behavior == "exception":
                raise RuntimeError("sensitive error text must not be journaled")
            if state.behavior == "interrupt":
                raise KeyboardInterrupt()
            if state.behavior == "swallowed-interrupt":
                self.r.data["status"] = "STOPPED: interrupted"
                return self.r
            if state.behavior == "timeout":
                raise TimeoutError()
            if state.behavior == "callback-timeout":
                state.ticks += 601
                self.kwargs["on_event"]("model_call", {})
            if state.behavior == "fix":
                (self.repo / "solution.py").write_text("def answer(): return 42\n", encoding="utf-8")
            if state.behavior == "tamper":
                (self.repo / "test_solution.py").write_text("def test_fake(): assert True\n", encoding="utf-8")
            self.r.data.update(solved=True, status="SOLVED", steps=1)
            if state.behavior == "over-step":
                self.r.data["steps"] = 31
            if state.behavior == "late-return":
                state.ticks += 601
            return self.r

    real_grade = runner.grade_exercise

    def grade(original, final, output, **kwargs):
        assert all(not sec.bench_auto for sec in state.sessions)
        assert original != source and original != final
        assert final.name == "final" and output.name == "grading"
        assert not any(final == sec.repo_root for sec in state.sessions)
        state.grading.append((original, final, output))
        output.mkdir()
        solved = "return 42" in (final / "solution.py").read_text(encoding="utf-8")
        result = {"solved": solved, "test_edit": False, "pytest_exit_code": 0 if solved else 1,
                  "timed_out": False, "error": None}
        (output / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr(runner, "grade_exercise", grade)
    state.real_grade = real_grade
    state.path, state.plan, state.source = path, plan, source
    state.output = tmp_path / "artifacts"
    state.options = {"oracles": {"polyglot/synthetic": ["test_solution.py"]},
                     "agent_factory": Agent, "session_factory": Session, "scratch_parent": tmp_path,
                     "clock": lambda: state.ticks}
    return state


def execute(harness, **kwargs):
    return runner.run_plan(harness.path, harness.output, **{**harness.options, **kwargs})


def test_normal_completion_order_flags_identity_and_durable_evidence(harness):
    rows = execute(harness)
    assert [row["run_id"] for row in rows] == [run["run_id"] for run in harness.plan["runs"]]
    assert [row["status"] for row in rows] == ["completed", "completed", "blocked", "blocked", "completed"]
    assert [agent.kwargs["flags"] for agent in harness.agents] == [None, None, set()]
    assert len(harness.agents) == len(harness.sessions) == len(harness.grading) == 3
    supported = [row for row in rows if row["status"] == "completed"]
    assert len({row["session_id"] for row in supported}) == 3
    assert len({row["attempt_id"] for row in rows}) == 5
    for row in supported:
        assert row["solved"] is row["agent_claimed_solved"] is row["independently_graded_solved"] is True
        assert row["full_plan_id"] == harness.plan["full_plan"]["id"]
        assert row["full_plan_position"] == 1 and row["shard_number"] is None
        assert row["cost_attribution"]["authoritative_cost_usd"] is None
        assert row["cost_attribution"]["receipt_cost_usd"] == 0.0123
        assert not row["comparison_ready"] and not row["hard_deadline_enforced"]
        assert all(Path(path).exists() for path in row["evidence"].values())
        assert not Path(row["workspace_path"]).exists()
        receipt = json.loads(Path(row["evidence"]["receipt"]).read_text())
        assert receipt["session"] == row["session_id"]
        audit = Path(row["evidence"]["security_events"]).read_text()
        assert "SYNTHETIC-PERMIT-NOT-FOR-PERSISTENCE" not in audit
        assert "[redacted]" in audit
    assert all(not sec.bench_auto for sec in harness.sessions)
    assert (harness.source / "solution.py").read_text() == "def answer(): return 0\n"
    assert all(row["error"]["type"] == "MissingMiniRunner" for row in rows if row["status"] == "blocked")


def test_real_grader_restores_original_oracle_and_disagrees_with_agent(harness, monkeypatch):
    harness.behavior = "tamper"
    monkeypatch.setattr(runner, "grade_exercise", harness.real_grade)
    rows = execute(harness)
    for row in rows:
        if row["status"] == "completed":
            assert row["agent_claimed_solved"] is True
            assert row["independently_graded_solved"] is row["solved"] is False
            assert row["grading"]["test_edit"] is True
            restored = Path(row["grading"]["workspace_path"]) / "test_solution.py"
            assert restored.read_bytes() == (harness.source / "test_solution.py").read_bytes()


@pytest.mark.parametrize("behavior", ["exception", "timeout", "callback-timeout", "late-return"])
def test_errors_and_timeouts_close_sessions_preserve_receipts_and_never_solve(harness, behavior):
    harness.behavior = behavior
    rows = execute(harness)
    for row in rows:
        if row["agent_variant"] == "mini-swe-agent":
            continue
        assert row["status"] == "incomplete" and not row["solved"]
        assert row["timed_out"] is (behavior != "exception")
        assert Path(row["evidence"]["receipt"]).exists()
        assert row["grading"] is not None
    assert all(not sec.bench_auto for sec in harness.sessions)
    assert "sensitive error text" not in (harness.output / "results.jsonl").read_text()


def test_resume_never_duplicates_completed_runs_or_replaces_evidence(harness):
    rows = execute(harness)
    journal = (harness.output / "results.jsonl").read_bytes()
    assert execute(harness) == rows
    assert execute(harness, retry_incomplete=True)[:5] == rows
    assert len(harness.agents) == 3
    assert (harness.output / "results.jsonl").read_bytes().startswith(journal)
    completed = [row for row in runner._rows(harness.output / "results.jsonl") if row["status"] == "completed"]
    assert len({row["run_id"] for row in completed}) == len(completed) == 3


def test_retry_is_explicit_and_uses_new_attempt_and_session(harness):
    harness.behavior = "exception"
    first = execute(harness)
    assert len(harness.agents) == 3
    harness.behavior = "fix"
    assert execute(harness) == first
    retried = execute(harness, retry_incomplete=True)[5:]
    assert {row["attempt_id"] for row in retried}.isdisjoint({row["attempt_id"] for row in first})
    assert {row["session_id"] for row in retried if row["session_id"]}.isdisjoint(
        {row["session_id"] for row in first if row["session_id"]})
    assert sum(row["status"] == "completed" for row in retried) == 3


def test_agent_consumed_interrupt_stops_further_dispatch_and_step_violations_are_incomplete(harness):
    harness.behavior = "swallowed-interrupt"
    with pytest.raises(KeyboardInterrupt):
        execute(harness)
    assert len(harness.agents) == 1 and not harness.sessions[0].bench_auto
    assert runner._rows(harness.output / "results.jsonl")[0]["status"] == "interrupted"
    harness.behavior = "over-step"
    rows = execute(harness, retry_incomplete=True)
    assert all(not row["solved"] for row in rows)
    assert all(row["status"] == "incomplete" for row in rows if row["steps"] == 31)


def test_duplicate_completed_run_ids_are_rejected(harness):
    rows = execute(harness)
    duplicate = {**rows[0], "attempt_id": uuid4().hex}
    runner._append(harness.output / "results.jsonl", duplicate)
    with pytest.raises(ValueError, match="Duplicate completed"):
        execute(harness)
    assert len(harness.agents) == 3


def test_oracle_mapping_is_frozen_across_resume(harness):
    execute(harness)
    assert json.loads((harness.output / "oracles.json").read_text()) == harness.options["oracles"]
    with pytest.raises(ValueError, match="immutable oracle"):
        execute(harness, oracles={"polyglot/synthetic": ["solution.py"]})
    assert len(harness.agents) == 3


def test_interrupt_closes_session_and_recovery_marks_orphan_incomplete(harness):
    harness.behavior = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        execute(harness)
    assert not harness.sessions[0].bench_auto
    first = runner._rows(harness.output / "results.jsonl")
    assert first[0]["status"] == "interrupted" and first[0]["solved"] is False
    # Simulate a killed process after lifecycle persistence but before result append.
    (harness.output / "results.jsonl").write_text("", encoding="utf-8")
    harness.behavior = "fix"
    rows = execute(harness)
    assert rows[0]["error"]["type"] == "OrphanedAttempt"
    assert rows[0]["session_id"] == first[0]["session_id"]
    assert len(harness.agents) == 3  # interrupted run 1 is not automatically retried


def test_concurrent_lock_truncated_journal_and_changed_plan_fail_closed(harness):
    harness.output.mkdir()
    lock = harness.output / ".runner.lock"
    lock.write_text("99999", encoding="utf-8")
    with pytest.raises(FileExistsError):
        execute(harness)
    assert lock.read_text() == "99999"
    lock.unlink()
    execute(harness)
    journal = harness.output / "results.jsonl"
    before = journal.read_bytes()
    journal.write_bytes(before + b'{"partial":')
    with pytest.raises(ValueError, match="Truncated"):
        execute(harness)
    journal.write_bytes(before)
    changed = json.loads(harness.path.read_text())
    changed["comment"] = "another immutable plan"
    harness.path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="different immutable plan"):
        execute(harness)
    assert len(harness.agents) == 3


def test_setup_failure_closes_session(harness, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic copy failure")

    monkeypatch.setattr(runner, "populate_workspace", fail)
    rows = execute(harness)
    assert not harness.agents
    assert all(not sec.bench_auto for sec in harness.sessions)
    assert all(row["status"] in {"incomplete", "blocked"} for row in rows)


def test_constructor_failure_still_closes_and_grades_prepared_tree(harness):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic constructor failure")

    rows = execute(harness, agent_factory=fail)
    assert len(harness.grading) == len(harness.sessions) == 3
    assert all(not sec.bench_auto for sec in harness.sessions)
    for row in rows:
        if row["agent_variant"] != "mini-swe-agent":
            assert row["status"] == "incomplete" and row["session_id"] is None
            assert row["evidence"]["receipt"] is None and not row["solved"]


def test_grading_error_keeps_receipt_and_cannot_be_solved(harness, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic grading failure")

    monkeypatch.setattr(runner, "grade_exercise", fail)
    rows = execute(harness)
    for row in rows:
        if row["agent_variant"] != "mini-swe-agent":
            assert row["status"] == "incomplete" and row["agent_claimed_solved"] is True
            assert row["independently_graded_solved"] is None and not row["solved"]
            assert Path(row["evidence"]["receipt"]).exists()


def test_grading_timeout_is_visible_at_attempt_level(harness, monkeypatch):
    def timeout(*args, **kwargs):
        return {"solved": False, "test_edit": False, "timed_out": True,
                "pytest_exit_code": None, "error": None}

    monkeypatch.setattr(runner, "grade_exercise", timeout)
    for row in execute(harness):
        if row["agent_variant"] != "mini-swe-agent":
            assert row["timed_out"] is True and row["status"] == "incomplete"
            assert row["agent_claimed_solved"] is True and not row["solved"]


def test_runner_rejects_nonstandard_repeats(harness):
    plan = harness.plan
    plan["runs_per_task"] = {"crocodile": 1, "mini-swe-agent": 1, "all-off-twin": 1}
    plan["runs"] = [row for row in plan["runs"] if row["run_number"] == 1]
    plan["run_count"] = 3
    harness.path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="2\\+2\\+1"):
        execute(harness)
    assert not harness.sessions


def test_custom_commands_protocol_changes_and_missing_oracles_are_rejected(harness):
    with pytest.raises(ValueError, match="oracle"):
        execute(harness, oracles={})
    plan = harness.plan
    plan["tasks"][0]["test_command"].append("--timeout=5")
    for row in plan["runs"]:
        row["test_command"] = plan["tasks"][0]["test_command"]
    harness.path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="Custom pytest"):
        execute(harness)
    assert not harness.agents


def test_cli_requires_execution_opt_in_without_importing_live_services(harness):
    with pytest.raises(SystemExit) as error:
        runner.main(["--plan", str(harness.path), "--output", str(harness.output),
                     "--oracles", "not-read.json"])
    assert error.value.code == 2
    assert not harness.agents


def test_population_keeps_root_identity_and_excludes_nested_metadata(harness, tmp_path):
    target = tmp_path / "pinned"
    target.mkdir()
    identity = target.stat().st_ino
    assert populate_workspace(harness.source, target) == target.resolve()
    assert target.stat().st_ino == identity
    assert not any(path.name == ".meta" for path in target.rglob("*"))
    before = (target / "solution.py").read_bytes()
    with pytest.raises(FileExistsError):
        populate_workspace(harness.source, target)
    assert (target / "solution.py").read_bytes() == before
