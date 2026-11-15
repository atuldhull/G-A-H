"""Fake WSL/mini processes only. No mini install, credentials or paid requests."""

from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace

import pytest

from bench import mini, mini_bridge
from bench.bifrost_export import _prices, _sessions, write_export
from bench.mini_report import report_row
from bench.run import _rows, _save, run_plan
from bench.tests.test_run import harness as _shared_harness


@pytest.fixture
def fake_mini(tmp_path, monkeypatch):
    harness = _shared_harness.__wrapped__(tmp_path, monkeypatch)
    from bench import run as runner
    monkeypatch.setattr(mini, "grade_exercise", runner.grade_exercise)
    settings = mini.Settings("Synthetic-Ubuntu", "/opt/mini-2.4.6/bin/python")

    class Backend:
        calls = 0
        mode = "success"
        specs = []

        def path(self, path):
            return str(path)  # Local synthetic path, never an actual WSL conversion.

        def probe(self, artifacts):
            if self.mode in {"WSLUnavailable", "MissingBenchCredential", "MiniVersionMismatch"}:
                raise mini.SetupFailure(self.mode)
            return {"ready": True, "version": "2.4.6"}

        def launch(self, spec, artifacts):
            self.calls += 1
            self.specs.append(spec)
            _save(artifacts / "command.json", ["wsl.exe", "--distribution", "Synthetic-Ubuntu", "--exec", "fake-python"])
            workspace = Path(spec["workspace"])
            assert not any(path.name == ".meta" for path in workspace.rglob("*"))
            task_bytes = Path(spec["task_file"]).read_bytes()
            assert task_bytes.decode("utf-8") == harness.plan["runs"][2]["task_text"]
            assert hashlib.sha256(task_bytes).hexdigest() == spec["task_text_sha256"]
            assert spec["config"]["agent"]["step_limit"] == 30
            assert spec["config"]["agent"]["wall_time_limit_seconds"] == 600
            if self.mode == "success":
                (workspace / "solution.py").write_text("def answer(): return 42\n", encoding="utf-8")
            if self.mode == "disagreement":
                (workspace / "test_solution.py").write_text("def test_fake(): assert True\n", encoding="utf-8")
            status = {"quota": "RateLimitError", "auth": "AuthenticationError", "failure": "RuntimeError",
                      "agent_failure": "LimitsExceeded", "timeout": "TimeExceeded"}.get(self.mode, "Submitted")
            _save(artifacts / "mini-receipt.json", {"mini_version": "2.4.6", "template_git_blob": mini.TEMPLATE_BLOB,
                                                    "steps": 30 if self.mode == "agent_failure" else 1,
                                                    "exit_status": status, "usage": None})
            if self.mode == "interrupt":
                raise KeyboardInterrupt()
            return {"returncode": 1 if self.mode in {"failure", "quota", "auth"} else 0,
                    "timed_out": self.mode == "timeout", "worker_deadline_enforced": True,
                    "escaped_descendants_contained": False}

    backend = Backend()
    adapter = mini.MiniAdapter(settings, backend)
    harness.mini = adapter
    harness.backend = backend
    return harness


def execute(harness, **kwargs):
    return run_plan(harness.path, harness.output, **harness.options,
                    mini_adapter=harness.mini, variants={"mini-swe-agent"}, **kwargs)


def test_success_uses_exact_planned_mini_slots_config_and_fresh_grading(fake_mini):
    rows = execute(fake_mini)
    assert [row["run_id"] for row in rows] == [row["run_id"] for row in fake_mini.plan["runs"][2:4]]
    assert [row["run_number"] for row in rows] == [1, 2]
    assert len(fake_mini.agents) == len(fake_mini.sessions) == 0
    assert fake_mini.backend.calls == 2
    for row in rows:
        assert row["status"] == "completed" and row["solved"] is True
        assert row["agent_claimed_solved"] is True
        assert row["full_plan_id"] == fake_mini.plan["full_plan"]["id"]
        assert not Path(row["workspace_path"]).exists()
        assert Path(row["evidence"]["command"]).exists()
        assert row["attribution"]["window_start"] <= row["attribution"]["window_end"]
        assert row["session_id"] is None and row["attribution"]["method"] == "unverified-time-window"
        assert row["cost_attribution"]["authoritative_cost_usd"] is None and not row["comparison_ready"]
        assert not row["hard_deadline_enforced"] and row["worker_deadline_enforced"]
    config = fake_mini.mini.config
    assert config["model"]["model_name"] == "openai/gemini/gemini-3.5-flash-lite"
    assert config["model"]["cost_tracking"] == "ignore_errors"
    assert config["model"]["set_cache_control"] == "default_end"
    assert config["model"]["model_kwargs"] == {"drop_params": True, "extra_body": {"fallbacks": []}}


def test_approved_gemini_profiles_align_with_frozen_policy_without_live_claims():
    from bench.plan import EVALUATION_POLICY

    directory = mini.CONFIG_PATH.parent
    settings = mini.Settings(**json.loads((directory / "mini-settings.ubuntu.json").read_text()))
    native = json.loads((directory / "crocodile-gemini-bench.json").read_text())
    adapter = mini.MiniAdapter(settings)
    policy = EVALUATION_POLICY
    assert adapter.config["model"]["model_name"] == "openai/" + policy["model"]
    assert settings.api_base == policy["gateway_url"] + "/v1"
    assert mini.Settings("Synthetic-Ubuntu", "/fake/python").api_base == settings.api_base
    assert native["bifrost_url"] == policy["gateway_url"] == "http://127.0.0.1:18080"
    assert native["models"] == {tier: {"chain": [policy["model"]]} for tier in ("cheap", "strong")}
    assert (policy["virtual_key_id"], policy["virtual_key_name"]) == ("vk-bench", "bench")
    assert policy["measured_model_fallbacks"] == [] and policy["measured_escalation"] is False
    assert policy["thinking"] == policy["effort"] == "provider-default"
    assert adapter.config["thinking_policy"]["thinking"] == "provider-default"
    assert adapter.config["model"]["model_kwargs"] == {"drop_params": True, "extra_body": {"fallbacks": []}}
    assert settings.credential_env == "CROCODILE_BENCH_VK"
    assert settings.session_header_verified is False and settings.session_header_evidence == ""
    assert set(native) == {"bifrost_url", "models"}  # No unsupported VK selector or credential.


def test_interleaving_preserves_all_five_runs_without_adapter_substitution(fake_mini):
    rows = run_plan(fake_mini.path, fake_mini.output, **fake_mini.options, mini_adapter=fake_mini.mini)
    assert [row["run_id"] for row in rows] == [run["run_id"] for run in fake_mini.plan["runs"]]
    assert len(fake_mini.agents) == 3 and fake_mini.backend.calls == 2


@pytest.mark.parametrize("mode,reason", [("WSLUnavailable", "WSLUnavailable"),
                                        ("MissingBenchCredential", "MissingBenchCredential"),
                                        ("MiniVersionMismatch", "MiniVersionMismatch"),
                                        ("quota", "QuotaOrRateLimit"), ("auth", "MissingOrInvalidBenchCredential"),
                                        ("failure", "MiniExecutionIncomplete")])
def test_infrastructure_failures_are_incomplete_not_task_failures(fake_mini, mode, reason):
    fake_mini.backend.mode = mode
    for row in execute(fake_mini):
        assert row["status"] == "incomplete" and row["error"]["type"] == reason
        assert not row["solved"] and not row["comparison_ready"]
        with pytest.raises(ValueError, match="Incomplete execution"):
            report_row(row, fake_mini.plan["runs"][2], "not-read")


def test_agent_limit_is_recorded_separately_from_infrastructure_failure(fake_mini):
    fake_mini.backend.mode = "agent_failure"
    for row in execute(fake_mini):
        assert row["status"] == "completed" and row["error"] is None
        assert row["agent_status"] == "LimitsExceeded" and not row["solved"]
        assert row["steps"] == 30


def test_timeout_is_incomplete_and_not_a_solved_result(fake_mini):
    fake_mini.backend.mode = "timeout"
    for row in execute(fake_mini):
        assert row["timed_out"] and row["error"]["type"] == "MiniTimeout"
        assert row["status"] == "incomplete" and not row["solved"]
        assert row["grading"] is not None


def test_grading_timeout_is_not_a_completed_run(fake_mini, monkeypatch):
    monkeypatch.setattr(mini, "grade_exercise", lambda *args, **kwargs: {
        "solved": False, "test_edit": False, "timed_out": True, "error": None, "pytest_exit_code": None,
    })
    for row in execute(fake_mini):
        assert row["status"] == "incomplete" and row["timed_out"] and not row["solved"]


def test_real_grading_disagrees_and_restores_tampered_tests(fake_mini, monkeypatch):
    fake_mini.backend.mode = "disagreement"
    monkeypatch.setattr(mini, "grade_exercise", fake_mini.real_grade)
    for row in execute(fake_mini):
        assert row["status"] == "completed" and row["agent_claimed_solved"] is True
        assert not row["solved"] and row["grading"]["test_edit"]
        assert (Path(row["grading"]["workspace_path"]) / "test_solution.py").read_bytes() == (
            fake_mini.source / "test_solution.py").read_bytes()


def test_resume_and_interrupt_preserve_attempts_and_do_not_duplicate_completed_ids(fake_mini):
    fake_mini.backend.mode = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        execute(fake_mini)
    assert _rows(fake_mini.output / "results.jsonl")[0]["status"] == "interrupted"
    fake_mini.backend.mode = "success"
    rows = execute(fake_mini, retry_incomplete=True)
    calls = fake_mini.backend.calls
    assert execute(fake_mini) == rows
    assert fake_mini.backend.calls == calls == 3
    completed = [row["run_id"] for row in rows if row["status"] == "completed"]
    assert len(completed) == len(set(completed)) == 2


def test_reviewed_header_attribution_and_frozen_settings(fake_mini):
    settings = mini.Settings("Synthetic-Ubuntu", "/opt/mini-2.4.6/bin/python",
                             session_header_verified=True, session_header_evidence="synthetic transport review")
    fake_mini.mini = mini.MiniAdapter(settings, fake_mini.backend)
    rows = execute(fake_mini)
    assert len({row["session_id"] for row in rows}) == 2
    assert [spec["session_header"] for spec in fake_mini.backend.specs] == [row["session_id"] for row in rows]
    fake_mini.mini = mini.MiniAdapter(mini.Settings("Other-Ubuntu", "/opt/mini/bin/python"), fake_mini.backend)
    with pytest.raises(ValueError, match="immutable mini"):
        execute(fake_mini)


def test_report_row_requires_complete_cost_evidence_and_matches_existing_schema(fake_mini, tmp_path):
    from bench.report import _plan, _validated

    fake_mini.mini = mini.MiniAdapter(mini.Settings("Synthetic-Ubuntu", "/opt/mini/bin/python",
                                                 session_header_verified=True,
                                                 session_header_evidence="synthetic"), fake_mini.backend)
    attempt = execute(fake_mini)[0]
    planned = fake_mini.plan["runs"][2]
    model = attempt["model"]
    session = {"schema_version": 1, "data_kind": "synthetic", "source": "bifrost", "complete": True,
               "run_id": planned["run_id"], "session_id": "qualified-synthetic-session", "model": model,
               "date": "2026-11-14", "gateway_version": "2.5.1", "requests": [
                   {"request_id": "synthetic-request", "model": model,
                    "usage": {"uncached_input": 1, "cache_read_input": 0, "cache_write_input": 0, "output": 1}}]}
    prices = {"schema_version": 1, "data_kind": "synthetic", "currency": "USD", "models": {
        model: {"uncached_input": 1, "cache_read_input": 1, "cache_write_input": 1, "output": 1}}}
    bundle = write_export({"complete": True, "session": session, "prices": prices,
                           "computed_cost_usd": Fraction(2, 1_000_000), "receipt_comparison": {"status": "unavailable"},
                           "raw_session_id": attempt["session_id"]}, tmp_path / "synthetic-billing")
    row = report_row(attempt, planned, bundle)
    expected, _ = _plan(fake_mini.plan)
    sessions = _sessions([session], _prices(prices))
    _validated([row], {planned["run_id"]: expected[planned["run_id"]]}, model, sessions,
               row["cost_provenance"]["logs_sha256"], row["cost_provenance"]["prices_sha256"], "synthetic")
    assert row["cost_usd"] > 0 and row["solved"] is True
    unverified = deepcopy(attempt)
    unverified["session_id"] = None
    with pytest.raises(ValueError):
        report_row(unverified, planned, bundle)
    retry = deepcopy(attempt)
    retry["prior_attempt_ids"] = ["earlier-billable-attempt"]
    with pytest.raises(ValueError, match="Retry cost aggregation"):
        report_row(retry, planned, bundle)


@pytest.mark.parametrize("task_text", ["Synthetic task", "Synthetic\r\nCRLF\rCR\nLF: \u03bb\n"])
def test_worker_never_serializes_credentials_or_conversation(tmp_path, monkeypatch, task_text):
    key = "SYNTHETIC-NOT-A-REAL-CREDENTIAL"
    config_dir = tmp_path / "installed-config"
    config_dir.mkdir()
    raw = b"synthetic upstream config for fake mini modules\n"
    (config_dir / "mini.yaml").write_bytes(raw)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    options = {}

    class Model:
        def __init__(self, **kwargs):
            options.update(kwargs)

    class Environment:
        def __init__(self, **kwargs):
            assert key not in os.environ.values()

    class Agent:
        def __init__(self, model, environment, **kwargs):
            self.messages, self.n_calls = [], 0

        def run(self, task):
            assert task == task_text
            self.n_calls = 1
            self.messages = [{"role": "user", "content": key}, {"role": "exit", "extra": {"exit_status": "Submitted"}}]
            self.save(None)

    modules = {"yaml": {"safe_load": lambda _: {"agent": {}, "environment": {}, "model": {
        "observation_template": "synthetic-default-observation", "format_error_template": "synthetic-default-format"}}},
               "minisweagent.config": {"builtin_config_dir": config_dir},
               "minisweagent.agents.default": {"DefaultAgent": Agent},
               "minisweagent.environments.local": {"LocalEnvironment": Environment},
               "minisweagent.models.litellm_model": {"LitellmModel": Model}}
    import sys
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(mini_bridge, "probe", lambda _: {"ready": True})
    monkeypatch.setattr(mini_bridge, "version", lambda _: "2.4.6")
    monkeypatch.setattr(mini_bridge, "TEMPLATE_BLOB", blob)
    monkeypatch.setattr(mini_bridge.logging, "disable", lambda _: None)
    monkeypatch.setattr(os, "environ", {"FAKE_BENCH_VK": key, "HOME": str(tmp_path), "OTHER_API_KEY": key})
    task, receipt = tmp_path / "task.txt", tmp_path / "receipt.json"
    task.write_bytes(task_text.encode("utf-8"))
    config = deepcopy(mini.MiniAdapter(mini.Settings("fake", "/python")).config)
    assert mini_bridge.worker({"credential_env": "FAKE_BENCH_VK", "config": config, "workspace": str(tmp_path),
                               "task_text_sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
                               "task_file": str(task), "receipt": str(receipt), "api_base": "http://127.0.0.1:18080/v1",
                               "session_header": "synthetic-session"}) == 0
    assert options["model_kwargs"]["extra_headers"]["x-bf-vk"] == key
    assert options["model_kwargs"]["extra_headers"]["x-bf-session-id"] == "synthetic-session"
    assert options["observation_template"] == "synthetic-default-observation"
    assert key not in receipt.read_text()
    assert "messages" not in json.loads(receipt.read_text())


def test_task_digest_mismatch_stops_before_probe_or_model_imports(tmp_path, monkeypatch):
    task, receipt = tmp_path / "task.txt", tmp_path / "receipt.json"
    task.write_bytes(b"Synthetic\r\ntext")

    def forbidden(*args):
        pytest.fail("Invalid task must be rejected before readiness or any model setup")

    monkeypatch.setattr(mini_bridge, "probe", forbidden)
    assert mini_bridge.worker({"task_file": str(task), "task_text_sha256": "0" * 64,
                               "receipt": str(receipt)}) == 2
    assert json.loads(receipt.read_text())["exit_status"] == "TaskTextMismatch"


def test_bridge_preflight_version_and_missing_wsl_are_specific(monkeypatch):
    monkeypatch.setattr(mini_bridge.platform, "release", lambda: "linux-without-subsystem")
    assert mini_bridge.probe("NOT_READ")["reason"] == "WSL2Required"
    monkeypatch.setattr(mini_bridge.platform, "release", lambda: "synthetic-microsoft-standard-WSL2")
    monkeypatch.setattr(mini_bridge, "version", lambda _: "0.0")
    assert mini_bridge.probe("NOT_READ")["reason"] == "MiniVersionMismatch"


def test_cli_is_opt_in_and_settings_contain_no_credentials(fake_mini):
    with pytest.raises(SystemExit) as error:
        mini.main(["--plan", "not-read", "--output", "not-written", "--oracles", "not-read", "--settings", "not-read"])
    assert error.value.code == 2
    with pytest.raises(ValueError):
        mini.Settings("fake", "/python", session_header_verified=True)


def test_model_configuration_drift_is_incomplete_before_launch(fake_mini):
    fake_mini.mini.config["model"]["model_name"] = "openai/unapproved/model"
    rows = execute(fake_mini)
    assert fake_mini.backend.calls == 0
    assert all(row["status"] == "incomplete" and row["error"]["type"] == "MiniPlanConfigMismatch" for row in rows)


def test_legacy_model_plan_is_rejected_before_any_adapter_or_agent_call(fake_mini):
    legacy = deepcopy(fake_mini.plan)
    legacy["evaluation_policy"].update(model="anthropic/claude-haiku-5-5", thinking="adaptive", effort="medium")
    fake_mini.path.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen model/thinking/cache"):
        execute(fake_mini)
    assert fake_mini.backend.calls == 0
    assert not fake_mini.agents and not fake_mini.sessions
    assert not fake_mini.output.exists()


def test_wsl_path_translation_is_argv_only_and_no_shell_is_used(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="/mnt/c/synthetic path/fixture\n")

    monkeypatch.setattr(mini.subprocess, "run", fake_run)
    backend = mini.WslBackend(mini.Settings("Synthetic-Ubuntu", "/venv/bin/python"))
    assert backend.path(tmp_path / "fixture") == "/mnt/c/synthetic path/fixture"
    assert calls[0][0][0:6] == ["wsl.exe", "--distribution", "Synthetic-Ubuntu", "--exec", "/usr/bin/wslpath", "-a"]
    assert "shell" not in calls[0][1]


def test_linux_supervisor_enforces_worker_timeout_but_does_not_claim_descendant_containment(tmp_path, monkeypatch):
    class Process:
        pid = 12345
        killed = False

        def wait(self, timeout=None):
            if not self.killed:
                assert timeout == 600
                raise subprocess.TimeoutExpired("synthetic-worker", timeout)
            return -9

        def kill(self):
            self.killed = True

        def poll(self):
            return -9 if self.killed else None

    process = Process()
    monkeypatch.setattr(mini_bridge.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(mini_bridge, "_start_time", lambda _: "synthetic-start")
    monkeypatch.setattr(mini_bridge, "stop", lambda *args: True)
    spec = {"control": str(tmp_path / "control.json"), "process_result": str(tmp_path / "process.json"),
            "attempt_id": "synthetic-attempt"}
    assert mini_bridge.supervise(spec, "not-executed.json") == 0
    outcome = json.loads((tmp_path / "process.json").read_text())
    assert outcome["timed_out"] and outcome["worker_deadline_enforced"]
    assert outcome["escaped_descendants_contained"] is False


def test_unknown_cleanup_stops_further_attempts(fake_mini):
    def failed_launch(*args):
        raise mini.SetupFailure("WSLTimeoutCleanupUnconfirmed")

    fake_mini.backend.launch = failed_launch
    with pytest.raises(KeyboardInterrupt):
        execute(fake_mini)
    rows = _rows(fake_mini.output / "results.jsonl")
    assert len(rows) == 1 and rows[0]["status"] == "interrupted"
    assert rows[0]["timed_out"] and rows[0]["error"]["type"] == "WSLTimeoutCleanupUnconfirmed"
