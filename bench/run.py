"""In-process benchmark attempts with independent grading and durable evidence.

Importing this module never loads live agent services. CLI execution is opt-in.
"""

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from bench.grade import grade_exercise
from bench.plan import SHARD_RANGES, TEST_PREFIX, _object, _relative
from bench.prepare import populate_workspace, prepare_workspace
from bench.report import _plan


class DeadlineExceeded(TimeoutError):
    """Cooperative event/return deadline, NOT a hard cancellation boundary."""


def _invalid_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def _decode(text):
    return json.loads(text, object_pairs_hook=_object, parse_constant=_invalid_constant)


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _save(path, value):
    payload = json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _append(path, value):
    payload = json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _rows(path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise ValueError(f"Truncated journal; manual recovery required: {path.name}")
    return [_decode(line) for line in text.splitlines()]


def _event_evidence(value):
    """Do not persist authority-bearing permit tokens from Part 3's audit list."""
    if isinstance(value, dict):
        sensitive = {"token", "key", "api_key", "authorization", "password", "credential", "vk"}
        return {key: "[redacted]" if str(key).casefold() in sensitive else _event_evidence(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_event_evidence(item) for item in value]
    return str(value) if isinstance(value, Path) else value


def _validate(plan, oracles):
    expected, _ = _plan(plan)
    if plan["runs_per_task"] != {"crocodile": 2, "mini-swe-agent": 2, "all-off-twin": 1}:
        raise ValueError("Runner requires the agreed 2+2+1 protocol")
    if [run["run_id"] for run in plan["runs"]] != list(expected):
        raise ValueError("Runs must retain the agreed sorted task/variant/repeat order")
    tasks = {task["task_id"]: task for task in plan["tasks"]}
    if not isinstance(oracles, Mapping) or set(oracles) != set(tasks):
        raise ValueError("Explicit oracle target lists must cover exactly the planned tasks")
    full_id = plan.get("full_plan", {}).get("id")
    if (not isinstance(full_id, str) or len(full_id) != 64
            or any(c not in "0123456789abcdef" for c in full_id)):
        raise ValueError("Use a current plan with a full_plan identity")
    for task_id, task in tasks.items():
        position, shard = task.get("full_plan_position"), task.get("shard_number")
        ids = plan["full_plan"].get("task_ids", [])
        if (type(position) is not int or not 1 <= position <= len(ids)
                or ids[position - 1] != task_id):
            raise ValueError("Invalid full-plan position")
        if shard is not None:
            if type(shard) is not int or not 1 <= shard <= 4:
                raise ValueError("Invalid shard number")
            start, end = SHARD_RANGES[shard - 1]
            if not start <= position <= end or (plan.get("shard") or {}).get("number") != shard:
                raise ValueError("Invalid shard assignment")
        if task["test_command"] != TEST_PREFIX:
            raise ValueError("Custom pytest arguments require a grading/agent adapter; refusing mismatch")
        if hashlib.sha256(task["task_text"].encode("utf-8")).hexdigest() != task["task_text_sha256"]:
            raise ValueError("Planned task text hash mismatch")
        targets = oracles[task_id]
        if not isinstance(targets, (list, tuple)) or not targets:
            raise ValueError("Each task needs an explicit nonempty oracle target list")
        for target in targets:
            if (not isinstance(target, str) or target.startswith("-")
                    or any(ord(c) < 32 for c in target)):
                raise ValueError("Invalid oracle target")
            _relative(target.split("::")[0], "oracle target")
    for run in plan["runs"]:
        task = tasks[run["task_id"]]
        for field in ("task_text", "source_path", "test_paths", "full_plan_position", "shard_number"):
            if run.get(field) != task.get(field):
                raise ValueError(f"Run/task mismatch: {field}")
        if run.get("full_plan_id") != full_id or task.get("full_plan_id") != full_id:
            raise ValueError("Run/task full-plan identity mismatch")


def _base(run, plan_id, model, attempt_id, artifacts):
    return {
        "schema_version": 1, "kind": "benchmark-attempt", "plan_id": plan_id,
        **{key: run[key] for key in (
            "run_id", "task_id", "dataset", "agent_variant", "run_number",
            "full_plan_id", "full_plan_position", "shard_number",
        )},
        "attempt_id": attempt_id, "runner_session_id": uuid4().hex,
        "session_id": None, "model": model, "models_observed": [],
        "status": "started", "started_at": _utc(), "finished_at": None,
        "duration_seconds": None, "agent_duration_seconds": None, "steps": None, "token_usage": None,
        "agent_claimed_solved": None, "agent_status": None,
        "independently_graded_solved": None, "solved": False, "grading": None,
        "error": None, "timed_out": False, "step_cap": 30,
        "step_cap_enforcement": "not-executed", "wall_clock_cap_seconds": 600,
        "hard_deadline_enforced": False, "deadline_policy": "cooperative-events-and-return",
        "cost_attribution": {"status": "incomplete", "authoritative_cost_usd": None,
                             "receipt_cost_usd": None, "receipt_comparison": "pending-log-attribution"},
        "comparison_ready": False, "artifact_directory": str(artifacts), "workspace_path": None,
        "evidence": {"receipt": None, "security_events": None, "original": None,
                     "final": None, "grading_result": None},
    }


def _receipt(agent, returned, row, artifacts):
    receipt = returned if returned is not None else getattr(agent, "r", None)
    if receipt is None:
        raise ValueError("Agent receipt unavailable")
    data = receipt.to_json()
    if data.get("session") != row["session_id"]:
        raise ValueError("Receipt session does not match agent session")
    path = artifacts / "receipt.json"
    _save(path, data)
    row["evidence"]["receipt"] = str(path)
    row["agent_claimed_solved"] = data.get("solved")
    row["agent_status"] = data.get("status")
    row["steps"], row["token_usage"] = data.get("steps"), data.get("usage")
    row["models_observed"] = data.get("models", [])
    row["cost_attribution"]["receipt_cost_usd"] = data.get("cost_usd")
    if type(row["steps"]) is not int or not 0 <= row["steps"] <= 30:
        raise ValueError("Missing/invalid step count or step-cap violation")
    if type(row["agent_claimed_solved"]) is not bool:
        raise ValueError("Missing/invalid agent solved claim")
    usage = row["token_usage"]
    if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                         for k in ("prompt_tokens", "completion_tokens", "cached_tokens"))
            or usage["cached_tokens"] > usage["prompt_tokens"]):
        raise ValueError("Missing/invalid token evidence")
    if data.get("stubs"):
        raise ValueError("Stub-backed execution is incomplete")


def _attempt(row, run, targets, artifacts, scratch, agent_factory, session_factory,
             security_options, events_path, clock, used_sessions):
    started = clock()
    agent = returned = sec = None
    agent_started = None
    prepared = False
    fatal = None

    def failed(error, phase):
        # Exception text can contain headers/task data. Keep type and phase only.
        row["error"] = row["error"] or {"type": type(error).__name__, "phase": phase}
        if isinstance(error, TimeoutError):
            row["timed_out"] = True

    if run["agent_variant"] == "mini-swe-agent":
        row.update(status="blocked", error={"type": "MissingMiniRunner", "phase": "dispatch"})
        row["step_cap_enforcement"] = "not-executed"
    else:
        with tempfile.TemporaryDirectory(prefix="crocodile-bench-", dir=scratch) as workspace:
            row["workspace_path"] = workspace
            _append(events_path, {"event": "workspace_created", **row})
            try:
                sec = session_factory(Path(workspace), parent=scratch, user_task=run["task_text"],
                                      **security_options)
                try:
                    if Path(sec.repo_root).resolve() != Path(workspace).resolve() or not sec.bench_auto:
                        raise ValueError("Factory did not return the active pinned bench session")
                    original = prepare_workspace(run["source_path"], artifacts / "original")
                    row["evidence"]["original"] = str(original)
                    for target in targets:
                        if not (original / target.split("::")[0]).exists():
                            raise ValueError("Declared oracle target missing from original")
                    populate_workspace(original, sec.repo_root)
                    prepared = True
                    agent_started = clock()
                    deadline = agent_started + 600
                    expired = False

                    def on_event(kind, data):
                        nonlocal expired
                        if not expired and clock() >= deadline:
                            expired = True
                            raise DeadlineExceeded("cooperative deadline")

                    if agent_factory is None:
                        from crocodile.loop import Agent
                        factory = Agent
                    else:
                        factory = agent_factory
                    agent = factory(Path(sec.repo_root), run["task_text"], oracle=list(targets),
                                    approve_mode="auto", security_session=sec,
                                    flags=None if run["agent_variant"] == "crocodile" else set(),
                                    step_cap=30, on_event=on_event)
                    row["step_cap_enforcement"] = "agent-api"
                    row["session_id"] = agent.s.id
                    if not isinstance(row["session_id"], str) or not row["session_id"]:
                        raise ValueError("Agent session ID unavailable")
                    if row["session_id"] in used_sessions:
                        raise ValueError("Agent reused an existing session ID")
                    used_sessions.add(row["session_id"])
                    _append(events_path, {"event": "agent_session_bound", **row})
                    if clock() >= deadline:
                        raise DeadlineExceeded("agent construction exceeded deadline")
                    returned = agent.run()
                    # The merged Agent consumes KeyboardInterrupt and returns a
                    # stopped receipt. Honor that stop rather than launching run 2.
                    if returned.to_json().get("status") == "STOPPED: interrupted":
                        raise KeyboardInterrupt()
                    if expired or clock() >= deadline:
                        raise DeadlineExceeded("agent returned after deadline")
                finally:
                    sec.close_bench()
                    if agent_started is not None:
                        row["agent_duration_seconds"] = max(0, clock() - agent_started)
            except BaseException as error:
                failed(error, "agent-or-session")
                if not isinstance(error, Exception):
                    fatal = error
            finally:
                if agent is not None:
                    try:
                        _receipt(agent, returned, row, artifacts)
                    except Exception as error:
                        failed(error, "receipt")
                if sec is not None:
                    try:
                        path = artifacts / "security-events.json"
                        _save(path, _event_evidence(sec.events))
                        row["evidence"]["security_events"] = str(path)
                    except Exception as error:
                        failed(error, "security-events")
                if prepared:
                    try:
                        final = prepare_workspace(workspace, artifacts / "final")
                        row["evidence"]["final"] = str(final)
                        if fatal is not None:
                            raise InterruptedError("Grading deferred after interruption")
                        grading = grade_exercise(artifacts / "original", final, artifacts / "grading",
                                                 task_id=run["task_id"], test_paths=run["test_paths"])
                        row["grading"] = grading
                        row["independently_graded_solved"] = grading["solved"]
                        row["evidence"]["grading_result"] = str(artifacts / "grading" / "result.json")
                        if grading["timed_out"]:
                            failed(TimeoutError(), "grading")
                        elif grading["error"]:
                            failed(RuntimeError(), "grading")
                    except Exception as error:
                        failed(error, "grading")
            row["status"] = "interrupted" if fatal else "incomplete" if row["error"] else "completed"
    row["finished_at"] = _utc()
    row["duration_seconds"] = max(0, clock() - started)
    row["solved"] = (row["status"] == "completed" and not row["timed_out"]
                     and row["independently_graded_solved"] is True)
    return fatal


def run_plan(plan_path, output, *, oracles, agent_factory=None, session_factory=None,
             scratch_parent=None, security_options=None, retry_incomplete=False, clock=time.monotonic):
    """Execute supported planned attempts sequentially; mini gets blocked rows.

    A completed attempt (including a graded failure) is never repeated. Failed,
    interrupted and blocked attempts require explicit retry_incomplete=True.
    Factories must both be injected for synthetic validation, or both omitted
    to use the merged live APIs. No Bifrost database or credentials are read here.
    """
    raw = Path(plan_path).read_bytes()
    plan = _decode(raw.decode("utf-8"))
    _validate(plan, oracles)
    if (agent_factory is None) != (session_factory is None):
        raise ValueError("Inject both factories together, or neither")
    options = dict(security_options or {})
    if options.keys() - {"integrity", "confidentiality"}:
        raise ValueError("Only integrity/confidentiality security options may be supplied")
    scratch = Path(scratch_parent or tempfile.gettempdir()).resolve(strict=True)
    destination = Path(output).absolute().resolve(strict=False)
    for root in plan["dataset_roots"].values():
        source = Path(root).resolve()
        if destination == source or source in destination.parents or destination in source.parents:
            raise ValueError("Run artifacts must not overlap datasets")
    destination.mkdir(exist_ok=True)
    lock = destination / ".runner.lock"
    # Fail closed: never auto-delete a lock left by a killed process.
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        snapshot = destination / "plan.json"
        if snapshot.exists() and snapshot.read_bytes() != raw:
            raise ValueError("Output belongs to a different immutable plan snapshot")
        if not snapshot.exists():
            with snapshot.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        oracle_snapshot = destination / "oracles.json"
        oracle_data = {task_id: list(targets) for task_id, targets in oracles.items()}
        if oracle_snapshot.exists() and _decode(oracle_snapshot.read_text(encoding="utf-8")) != oracle_data:
            raise ValueError("Output belongs to a different immutable oracle mapping")
        if not oracle_snapshot.exists():
            _save(oracle_snapshot, oracle_data)
        plan_id = hashlib.sha256(raw).hexdigest()
        results_path, events_path = destination / "results.jsonl", destination / "events.jsonl"
        rows, events = _rows(results_path), _rows(events_path)
        runs = {run["run_id"]: run for run in plan["runs"]}
        attempts, completed = set(), set()
        latest = {}
        for row in rows:
            if (row["plan_id"] != plan_id or row["run_id"] not in runs
                    or row["attempt_id"] in attempts
                    or row["status"] not in {"completed", "blocked", "incomplete", "interrupted"}):
                raise ValueError("Conflicting result journal identity")
            attempts.add(row["attempt_id"])
            latest[row["run_id"]] = row
            if row["status"] == "completed":
                if row["run_id"] in completed:
                    raise ValueError("Duplicate completed run ID")
                completed.add(row["run_id"])
        pending = {}
        for event in events:
            if event["plan_id"] != plan_id or event["run_id"] not in runs:
                raise ValueError("Conflicting lifecycle journal identity")
            pending[event["attempt_id"]] = event
        for attempt_id, event in pending.items():
            if attempt_id not in attempts:
                orphan = {k: v for k, v in event.items() if k != "event"}
                orphan.update(status="interrupted", finished_at=_utc(), solved=False,
                              error={"type": "OrphanedAttempt", "phase": "resume"})
                _append(results_path, orphan)
                rows.append(orphan)
                latest[orphan["run_id"]] = orphan
        session_owners = {}
        for row in rows:
            session_id = row["session_id"]
            if session_id is not None:
                if session_id in session_owners and session_owners[session_id] != row["attempt_id"]:
                    raise ValueError("Session ID is shared by multiple attempts")
                session_owners[session_id] = row["attempt_id"]
        used_sessions = set(session_owners)
        artifacts_root = destination / "attempts"
        artifacts_root.mkdir(exist_ok=True)
        for run in plan["runs"]:
            if run["run_id"] in completed or (run["run_id"] in latest and not retry_incomplete):
                continue
            attempt_id = uuid4().hex
            artifacts = artifacts_root / attempt_id
            artifacts.mkdir()
            row = _base(run, plan_id, plan["evaluation_policy"]["model"], attempt_id, artifacts)
            row["oracle_targets"] = list(oracles[run["task_id"]])
            _append(events_path, {"event": "attempt_started", **row})
            factory = session_factory
            if factory is None and run["agent_variant"] != "mini-swe-agent":
                # Lazy import, inside the attempt so import failure gets evidence.
                def factory(*args, **kwargs):
                    from crocodile.security import ApprovalSession
                    return ApprovalSession.for_bench(*args, **kwargs)
            try:
                fatal = _attempt(row, run, oracles[run["task_id"]], artifacts, scratch,
                                 agent_factory, factory, options, events_path, clock, used_sessions)
            except BaseException as error:
                # Includes temp creation/cleanup failures outside the session block.
                row.update(status="interrupted" if not isinstance(error, Exception) else "incomplete",
                           finished_at=_utc(), solved=False,
                           error={"type": type(error).__name__, "phase": "attempt-boundary"})
                fatal = error if not isinstance(error, Exception) else None
            _append(results_path, row)
            rows.append(row)
            if fatal is not None:
                raise fatal
        return rows
    finally:
        lock.unlink()


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True, help="JSON task-ID to pytest-target-list mapping")
    parser.add_argument("--execute", action="store_true", help="Explicitly opt into live agent execution")
    parser.add_argument("--retry-incomplete", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("Execution requires --execute; use bench.plan --dry-run for planning only")
    try:
        rows = run_plan(args.plan, args.output, oracles=_decode(args.oracles.read_text(encoding="utf-8")),
                        retry_incomplete=args.retry_incomplete)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Runner failed ({type(error).__name__}); inspect durable evidence.\n")
    print(f"Recorded {len(rows)} attempts; mini integration and authoritative cost attribution remain incomplete.")
    return 0 if all(row["status"] == "completed" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
