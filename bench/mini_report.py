"""Strict join from a completed attempt to separately acquired verified cost evidence."""

import hashlib
from pathlib import Path

from bench.bifrost_export import _json, _money, _prices, _sessions


def report_row(attempt, planned_run, bundle):
    """Return exactly the v1 reporter fields; refuse setup errors or unknown cost.

    Uses an individual complete Bifrost exporter bundle, never a receipt estimate
    or an unresolved time window. No report is published by this function.
    """
    if (attempt["status"] != "completed" or attempt["error"] or attempt["session_id"] is None
            or attempt["run_id"] != planned_run["run_id"] or attempt.get("timed_out")):
        raise ValueError("Incomplete execution or unresolved attribution cannot enter a report")
    if attempt.get("prior_attempt_ids") != []:
        raise ValueError("Retry cost aggregation is unverified; cannot omit earlier attempts")
    if any(attempt.get(key) != planned_run.get(key) for key in (
        "task_id", "dataset", "agent_variant", "run_number", "full_plan_id", "full_plan_position", "shard_number",
    )):
        raise ValueError("Attempt does not match the planned run identity")
    directory = Path(bundle)
    manifest = _json((directory / "manifest.json").read_bytes())
    files = {name: (directory / name).read_bytes()
             for name in ("evidence.jsonl", "prices.yaml", "costs.jsonl", "diagnostics.json")}
    if any(manifest.get(name) != hashlib.sha256(raw).hexdigest() for name, raw in files.items()):
        raise ValueError("Cost evidence hashes changed")
    diagnostics = _json(files["diagnostics.json"])
    if diagnostics.get("complete") is not True or diagnostics.get("raw_session_id") != attempt["session_id"]:
        raise ValueError("Cost evidence not bound to this actual session")
    sessions = [_json(line) for line in files["evidence.jsonl"].splitlines()]
    verified = _sessions(sessions, _prices(_json(files["prices.yaml"])))
    costs = [_json(line) for line in files["costs.jsonl"].splitlines()]
    if len(costs) != 1 or len(verified) != 1 or attempt["run_id"] not in verified:
        raise ValueError("Expected an individual matching run cost bundle")
    session, cost = verified[attempt["run_id"]]
    if (session["model"] != attempt["model"] or costs[0]["run_id"] != attempt["run_id"]
            or costs[0]["session_id"] != session["session_id"]
            or _money(costs[0]["cost_usd"]) != cost):
        raise ValueError("Model or cost mismatch")
    provenance = {"kind": "bifrost_logs_x_prices_yaml", "session_id": session["session_id"],
                  "logs_sha256": hashlib.sha256(files["evidence.jsonl"]).hexdigest(),
                  "prices_sha256": hashlib.sha256(files["prices.yaml"]).hexdigest()}
    if costs[0]["cost_provenance"] != provenance:
        raise ValueError("Cost provenance mismatch")
    grade = attempt["grading"]
    if grade["error"] or grade["timed_out"]:
        raise ValueError("Incomplete grading cannot enter a report")
    return {
        "schema_version": 1, "data_kind": session["data_kind"],
        **{key: planned_run[key] for key in (
            "run_id", "task_id", "dataset", "agent_variant", "run_number", "task_text_sha256",
            "test_command", "step_cap", "wall_clock_cap_seconds",
        )},
        "model": session["model"], "date": session["date"], "gateway_version": session["gateway_version"],
        "solved": grade["solved"], "test_edit": grade["test_edit"], "timed_out": False,
        "pytest_exit_code": grade["pytest_exit_code"], "error": None,
        "cost_usd": costs[0]["cost_usd"], "cost_provenance": provenance,
    }
