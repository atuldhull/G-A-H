"""Synthetic diagnostic regressions; no archive code, external services or models."""

import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from bench import failure_evidence, mini
from bench.mini_report import report_row
from bench.prepare import WorkspaceEntryError
from bench.tests.test_mini import execute, fake_mini as _fake_mini


@pytest.fixture
def harness(tmp_path, monkeypatch):
    return _fake_mini.__wrapped__(tmp_path, monkeypatch)


def install_bad_entry(harness, monkeypatch, make_entry):
    launch = harness.backend.launch

    def finish_then_add(spec, artifacts):
        result = launch(spec, artifacts)
        receipt = artifacts / "mini-receipt.json"
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["steps"] = 26
        receipt.write_text(json.dumps(data), encoding="utf-8")
        bad = Path(spec["workspace"]) / "nested/rejected.node"
        bad.parent.mkdir(exist_ok=True)
        make_entry(bad)
        return result

    monkeypatch.setattr(harness.backend, "launch", finish_then_add)


def assert_rejected(harness, reason, kind):
    rows = execute(harness)
    for row in rows:
        assert row["agent_status"] == "Submitted" and row["steps"] == 26
        assert row["process_outcome"]["returncode"] == 0, row["error"]
        assert row["agent_claimed_solved"] is True
        assert row["status"] == "incomplete" and not row["solved"]
        assert row["grading"] is None and row["independently_graded_solved"] is None
        assert row["evidence"]["final"] is None and row["evidence"]["grading_result"] is None
        assert not Path(row["workspace_path"]).exists()  # OS workspace cleaned.
        error = row["error"]
        assert error["type"] == "WorkspaceEntryError" and error["reason"] == reason
        assert error["stage"] == "final-copy" and error["relative_path"] == "nested/rejected.node"
        assert error["path_scope"] == "workspace" and error["message"]
        assert any(f["module"] == "prepare.py" for f in error["bench_frames"])
        evidence = json.loads(Path(row["evidence"]["failure_inventory"]).read_text(encoding="utf-8"))
        assert evidence["capture_timing"] == "before temporary workspace cleanup"
        assert not evidence["workspace"]["file_contents_captured"]
        assert not evidence["workspace"]["link_targets_captured"]
        assert {"path": "nested/rejected.node", "kind": kind} in evidence["workspace"]["entries"]
        assert not row["comparison_ready"] and row["cost_attribution"]["status"] == "incomplete"
        with pytest.raises(ValueError, match="Incomplete execution"):
            report_row(row, harness.plan["runs"][2], "must-not-read")
    assert not harness.grading


def test_final_copy_special_metadata_has_safe_durable_evidence_and_stays_incomplete(harness, monkeypatch):
    # Portable synthetic lstat seam; real FIFO/symlink OS tests below are separate.
    install_bad_entry(harness, monkeypatch, lambda p: p.write_bytes(b"DO NOT READ FILE CONTENT"))
    original = Path.lstat

    def metadata(path, *args, **kwargs):
        if path.name == "rejected.node" and any(p.startswith("mini-bench-") for p in path.parts):
            return SimpleNamespace(st_mode=stat.S_IFIFO | 0o600, st_size=0, st_file_attributes=0)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", metadata)
    assert_rejected(harness, "special-file", "special-file")


def test_real_fifo_rejection_does_not_open_or_block_on_special_file(harness, monkeypatch):
    if not hasattr(os, "mkfifo"):
        pytest.skip("Real FIFO creation is unavailable on this platform; synthetic metadata regression still runs")
    install_bad_entry(harness, monkeypatch, os.mkfifo)
    assert_rejected(harness, "special-file", "special-file")


def test_real_symlink_rejection_preserves_metadata_without_following_target(harness, monkeypatch, tmp_path):
    outside = tmp_path / "outside-sensitive.txt"
    outside.write_text("SYNTHETIC OUTSIDE CONTENT MUST NOT APPEAR", encoding="utf-8")
    probe = tmp_path / "probe-link"
    try:
        probe.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Real symlink creation unavailable without extra platform privileges")
    probe.unlink()
    install_bad_entry(harness, monkeypatch, lambda p: p.symlink_to(outside))
    assert_rejected(harness, "link-or-junction", "symlink")


def test_unknown_grading_exception_cannot_persist_prompt_or_credential_payload(harness, monkeypatch):
    payload = "SYNTHETIC PROMPT CONTENT authorization=Bearer sk-SYNTHETIC-PRIVATE-DIAGNOSTIC-CANARY"

    def fail(*args, **kwargs):
        raise ValueError(payload)

    monkeypatch.setattr(mini, "grade_exercise", fail)
    for row in execute(harness):
        assert row["status"] == "incomplete" and row["error"]["stage"] == "grading"
        assert row["error"]["relative_path"] is None
        raw = Path(row["evidence"]["failure_inventory"]).read_text(encoding="utf-8")
        assert "SYNTHETIC PROMPT" not in raw and "sk-SYNTHETIC" not in raw
        assert payload not in json.dumps(row)
        assert row["error"]["message"].startswith("Operation failed;")


def test_unknown_setup_error_text_is_not_used_as_a_reason_or_message(harness, monkeypatch):
    payload = "SYNTHETIC PROMPT sk-SYNTHETIC-PRIVATE-CANARY"

    def fail(*args):
        raise mini.SetupFailure(payload)

    monkeypatch.setattr(harness.backend, "probe", fail)
    for row in execute(harness):
        assert row["status"] == "incomplete" and row["error"]["type"] == "MiniSetupFailure"
        assert row["error"]["stage"] == "probe"
        evidence = Path(row["evidence"]["failure_inventory"]).read_text(encoding="utf-8")
        assert payload not in json.dumps(row) and "SYNTHETIC" not in evidence


def test_inventory_reads_only_metadata_and_redacts_unsafe_path_components(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / ".env").write_text("SYNTHETIC SECRET FILE DATA", encoding="utf-8")
    name = "sk-SYNTHETIC-PRIVATE-DIAGNOSTIC-CANARY"
    (root / name).write_text("SYNTHETIC PROMPT FILE DATA", encoding="utf-8")
    (root / "control\x1b[31m.txt").touch() if os.name != "nt" else None

    def forbidden(*args, **kwargs):
        pytest.fail("Diagnostic inventory must not open exercise files")

    monkeypatch.setattr(Path, "open", forbidden)
    result = failure_evidence.inventory(root)
    raw = json.dumps(result)
    assert result["complete"] and "SYNTHETIC" not in raw and name not in raw
    assert any(entry["path"].startswith("[name-") for entry in result["entries"])
    assert failure_evidence.relative_name(root / "../outside", root) is None


def test_inventory_is_bounded_and_missing_roots_are_not_complete(tmp_path, monkeypatch):
    for i in range(10):
        (tmp_path / f"item-{i}").touch()
    monkeypatch.setattr(failure_evidence, "MAX_ENTRIES", 4)
    result = failure_evidence.inventory(tmp_path)
    assert not result["complete"] and len(result["entries"]) <= 4
    assert not failure_evidence.inventory(tmp_path / "missing")["complete"]


def test_prepare_error_message_has_no_raw_absolute_path_or_file_content(tmp_path):
    bad = tmp_path / "bad"
    bad.write_bytes(b"synthetic")
    error = WorkspaceEntryError("special-file", bad)
    assert str(tmp_path) not in str(error)
    assert error.path == bad and isinstance(error, ValueError)
