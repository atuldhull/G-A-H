"""Separate WSL2 mini-swe-agent adapter; no mini import in the host interpreter."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from urllib.parse import urlparse
from uuid import uuid4

from bench.grade import grade_exercise
from bench.failure_evidence import before_cleanup, capture, safe_error
from bench.prepare import prepare_workspace
from bench.run import _append, _decode, _save, _utc, run_plan


CONFIG_PATH = Path(__file__).parent / "configs" / "mini-2.4.6.json"
VERSION = "2.4.6"
TEMPLATE_BLOB = "8b72f71f8092ae805ec43221dbeaeefc2340cd3e"


@dataclass(frozen=True)
class Settings:
    distro: str
    python: str
    api_base: str = "http://127.0.0.1:18080/v1"
    credential_env: str = "CROCODILE_BENCH_VK"
    session_header_verified: bool = False
    session_header_evidence: str = ""

    def __post_init__(self):
        if not self.distro.strip() or self.distro.startswith("-") or any(ord(c) < 32 for c in self.distro):
            raise ValueError("Explicit WSL distribution required")
        if not PurePosixPath(self.python).is_absolute() or any(ord(c) < 32 for c in self.python):
            raise ValueError("Use an absolute WSL interpreter in the separate pinned environment")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.credential_env):
            raise ValueError("Use a credential environment variable NAME, never a key value")
        url = urlparse(self.api_base)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.username or url.password or url.path != "/v1" or url.query or url.fragment):
            raise ValueError("Only the reviewed loopback Bifrost /v1 endpoint is supported")
        if type(self.session_header_verified) is not bool:
            raise ValueError("Header verification must be an explicit boolean")
        if self.session_header_verified and not self.session_header_evidence.strip():
            raise ValueError("Verified header forwarding requires an evidence reference")


class SetupFailure(RuntimeError):
    pass


def _failure_type(error):
    if isinstance(error, SetupFailure):
        allowed = {"WSLUnavailable", "WSLPathMappingFailed", "WSLInterpreterUnavailable", "MiniProbeFailed",
                   "WSL2Required", "MiniNotInstalled", "MiniVersionMismatch", "MissingBenchCredential",
                   "SeparateMiniEnvironmentRequired", "WSLTimeoutCleanupUnconfirmed", "MiniSupervisorFailed",
                   "MiniPlanConfigMismatch"}
        reason = error.args[0] if error.args else None
        return reason if isinstance(reason, str) and reason in allowed else "MiniSetupFailure"
    return type(error).__name__


class WslBackend:
    """Narrow process transport. stdout/stderr are never persisted or printed."""

    def __init__(self, settings):
        self.settings = settings

    def _command(self, *argv):
        return ["wsl.exe", "--distribution", self.settings.distro, "--exec", *argv]

    def path(self, path):
        try:
            result = subprocess.run(self._command("/usr/bin/wslpath", "-a", "-u", str(Path(path).absolute())),
                                    capture_output=True, stdin=subprocess.DEVNULL, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise SetupFailure("WSLUnavailable") from None
        converted = result.stdout.strip()
        if result.returncode or not converted.startswith("/") or "\n" in converted:
            raise SetupFailure("WSLPathMappingFailed")
        return converted

    def probe(self, artifacts):
        script = self.path(Path(__file__).with_name("mini_bridge.py"))
        path = artifacts / "probe.json"
        try:
            outcome = subprocess.run(self._command(self.settings.python, "-I", script,
                                                   "--probe", self.path(path), "--credential-env",
                                                   self.settings.credential_env),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise SetupFailure("WSLInterpreterUnavailable") from None
        if outcome.returncode or not path.exists():
            raise SetupFailure("MiniProbeFailed")
        result = _decode(path.read_text(encoding="utf-8"))
        allowed = {"WSL2Required", "MiniNotInstalled", "MiniVersionMismatch", "MissingBenchCredential",
                   "SeparateMiniEnvironmentRequired"}
        if not result.get("ready") or result.get("version") != VERSION:
            raise SetupFailure(result.get("reason") if result.get("reason") in allowed else "MiniProbeFailed")
        return result

    def launch(self, spec, artifacts):
        # All command arguments and spec data are key-free.
        script = self.path(Path(__file__).with_name("mini_bridge.py"))
        spec_path = artifacts / "launch.json"
        _save(spec_path, spec)
        command = self._command(self.settings.python, "-I", script, "--spec", self.path(spec_path))
        _save(artifacts / "command.json", command)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        try:
            code = process.wait(timeout=650)  # Linux worker watchdog is 600 s.
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            cancel = artifacts / "cancel.json"
            try:
                subprocess.run(self._command(self.settings.python, "-I", script, "--cancel", spec["control"],
                                             "--attempt-id", spec["attempt_id"], "--cancel-result", self.path(cancel)),
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                process.kill()
                process.wait()
            # Windows wsl.exe termination alone cannot attest Linux cleanup.
            # Stop dispatch; even a group signal cannot contain escaped sessions.
            if isinstance(error, KeyboardInterrupt):
                raise
            raise SetupFailure("WSLTimeoutCleanupUnconfirmed") from None
        if code != 0:
            if code == 130:
                raise KeyboardInterrupt()
            raise SetupFailure("MiniSupervisorFailed")
        return _decode((artifacts / "process.json").read_text(encoding="utf-8"))


class MiniAdapter:
    def __init__(self, settings, backend=None):
        self.settings = settings
        self.backend = backend or WslBackend(settings)
        self.config = _decode(CONFIG_PATH.read_text(encoding="utf-8"))

    def identity(self):
        return {"settings": asdict(self.settings), "config": self.config,
                "bridge_sha256": hashlib.sha256(Path(__file__).with_name("mini_bridge.py").read_bytes()).hexdigest()}

    def attempt(self, row, run, artifacts, events_path, clock, used_sessions=None):
        if run["agent_variant"] != "mini-swe-agent":
            raise ValueError("Mini adapter cannot execute another variant")
        started = clock()
        fatal = None
        state = {"stage": "plan-config"}
        roots = {"source": Path(run["source_path"]), "artifacts": artifacts}
        row.update(mini_version=VERSION, config_version=self.config["upstream_commit"],
                   config_sha256=hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
                   attribution={"method": "unverified-time-window", "window_start": None, "window_end": None,
                                "header_verified": self.settings.session_header_verified},
                   step_cap_enforcement="not-executed", hard_deadline_enforced=False)
        if self.settings.session_header_verified:
            row["session_id"] = "mini-" + uuid4().hex
            if used_sessions is not None:
                if row["session_id"] in used_sessions:
                    raise ValueError("Mini session ID already used")
                used_sessions.add(row["session_id"])
            row["attribution"]["method"] = "reviewed-session-header"
            row["attribution"]["evidence_reference"] = self.settings.session_header_evidence
        try:
            if (self.config["mini_version"] != VERSION or self.config["default_template_git_blob"] != TEMPLATE_BLOB
                    or self.config["model"]["model_name"] != "openai/" + row["model"]
                    or self.config["agent"] != {"step_limit": run["step_cap"],
                                               "wall_time_limit_seconds": run["wall_clock_cap_seconds"], "cost_limit": 0}):
                raise SetupFailure("MiniPlanConfigMismatch")
            state["stage"] = "probe"
            self.backend.probe(artifacts)
            with tempfile.TemporaryDirectory(prefix="mini-bench-") as temporary, before_cleanup(
                row, artifacts, Path(temporary) / "exercise", state, roots
            ):
                workspace = Path(temporary) / "exercise"
                roots["workspace"] = workspace
                state["stage"] = "prepare-original"
                original = prepare_workspace(run["source_path"], artifacts / "original")
                state["stage"] = "prepare-workspace"
                prepare_workspace(original, workspace)
                row["workspace_path"] = str(workspace)
                row["evidence"]["original"] = str(original)
                state["stage"] = "launch-evidence"
                task_path = artifacts / "task.txt"
                task_path.write_bytes(run["task_text"].encode("utf-8"))
                config = artifacts / "config.json"
                _save(config, self.identity())
                row["evidence"]["mini_config"] = str(config)
                paths = {"workspace": workspace, "task_file": task_path, "receipt": artifacts / "mini-receipt.json",
                         "control": artifacts / "control.json", "process_result": artifacts / "process.json"}
                spec = {**{key: self.backend.path(value) for key, value in paths.items()},
                        "task_text_sha256": run["task_text_sha256"],
                        "attempt_id": row["attempt_id"], "credential_env": self.settings.credential_env,
                        "api_base": self.settings.api_base, "session_header": row["session_id"], "config": self.config}
                row["attribution"]["window_start"] = _utc()
                agent_started = clock()
                _append(events_path, {"event": "mini_process_started", **row})
                process_error = None
                state["stage"] = "process"
                try:
                    outcome = self.backend.launch(spec, artifacts)
                except BaseException as error:
                    process_error = error
                    outcome = {"returncode": None, "timed_out": isinstance(error, subprocess.TimeoutExpired)}
                    if isinstance(error, KeyboardInterrupt):
                        fatal = error
                finally:
                    row["attribution"]["window_end"] = _utc()
                row["process_outcome"] = outcome
                if (artifacts / "command.json").exists():
                    row["evidence"]["command"] = str(artifacts / "command.json")
                row["agent_duration_seconds"] = max(0, clock() - agent_started)
                state["stage"] = "receipt"
                receipt_path = artifacts / "mini-receipt.json"
                receipt = _decode(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
                row["evidence"]["receipt"] = str(receipt_path) if receipt_path.exists() else None
                row["agent_status"] = receipt.get("exit_status")
                row["steps"], row["token_usage"] = receipt.get("steps"), receipt.get("usage")
                row["agent_claimed_solved"] = receipt.get("exit_status") == "Submitted" if receipt else None
                row["step_cap_enforcement"] = "mini-api-30"
                row["deadline_policy"] = "mini-query-check-plus-linux-worker-watchdog"
                row["worker_deadline_enforced"] = outcome.get("worker_deadline_enforced", False)
                row["timed_out"] = outcome.get("timed_out", False) or receipt.get("exit_status") == "TimeExceeded"
                status = receipt.get("exit_status")
                if status == "Interrupted" or outcome.get("returncode") in {130, -2, -15}:
                    fatal = KeyboardInterrupt()
                if process_error is not None:
                    reason = _failure_type(process_error)
                    row["error"] = {"type": reason, "phase": "mini-process"}
                    if reason == "WSLTimeoutCleanupUnconfirmed":
                        row["timed_out"] = True
                        fatal = KeyboardInterrupt()
                elif row["timed_out"]:
                    row["error"] = {"type": "MiniTimeout", "phase": "mini-process"}
                elif (outcome.get("returncode") != 0 or status not in {"Submitted", "LimitsExceeded", "RepeatedFormatError"}
                      or receipt.get("mini_version") != VERSION or receipt.get("template_git_blob") != TEMPLATE_BLOB):
                    reasons = {"AuthenticationError": "MissingOrInvalidBenchCredential", "MissingBenchCredential": "MissingBenchCredential",
                               "TaskTextMismatch": "MiniTaskTextMismatch",
                               "RateLimitError": "QuotaOrRateLimit", "PermissionDeniedError": "BenchCredentialDenied",
                               "MiniTemplateMismatch": "MiniTemplateMismatch", "Interrupted": "MiniInterrupted",
                               "ModuleNotFoundError": "MiniDependencyMissing", "ImportError": "MiniDependencyMissing",
                               "UnsupportedParamsError": "MiniModelConfigUnsupported",
                               "APIConnectionError": "BifrostUnavailable", "NotFoundError": "MiniModelUnavailable"}
                    row["error"] = {"type": reasons.get(status, "MiniExecutionIncomplete"), "phase": "mini-process"}
                elif type(row["steps"]) is not int or not 0 <= row["steps"] <= 30:
                    row["error"] = {"type": "MiniStepCapViolation", "phase": "mini-process"}
                state["stage"] = "final-copy"
                final = prepare_workspace(workspace, artifacts / "final")
                row["evidence"]["final"] = str(final)
                if fatal is None:
                    state["stage"] = "grading"
                    grade = grade_exercise(original, final, artifacts / "grading", task_id=run["task_id"],
                                           test_paths=run["test_paths"])
                    row["grading"] = grade
                    row["evidence"]["grading_result"] = str(artifacts / "grading" / "result.json")
                    row["independently_graded_solved"] = grade["solved"]
                    if grade["timed_out"] or grade["error"]:
                        row["timed_out"] = row["timed_out"] or grade["timed_out"]
                        row["error"] = row["error"] or {"type": "MiniGradingIncomplete", "phase": "grading"}
        except BaseException as error:
            if "diagnostic_error" not in row:
                capture(row, artifacts, None, state, error, roots)
            detail = row.get("diagnostic_error") or safe_error(error, state["stage"], roots)
            row["error"] = row["error"] or {**detail,
                "type": _failure_type(error),
                "phase": "mini-setup-or-grading"}
            if not isinstance(error, Exception):
                fatal = error
        row["status"] = "interrupted" if fatal else "incomplete" if row["error"] else "completed"
        row["solved"] = row["status"] == "completed" and row["independently_graded_solved"] is True
        row["finished_at"], row["duration_seconds"] = _utc(), max(0, clock() - started)
        return fatal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("plan", "output", "oracles", "settings"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--retry-incomplete", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("Use --execute only for an authorized live run; tests inject fake processes")
    adapter = MiniAdapter(Settings(**_decode(args.settings.read_text(encoding="utf-8"))))
    rows = run_plan(args.plan, args.output, oracles=_decode(args.oracles.read_text(encoding="utf-8")),
                    mini_adapter=adapter, variants={"mini-swe-agent"}, retry_incomplete=args.retry_incomplete)
    print("Mini attempts recorded; no authoritative cost or benchmark report published.")
    latest = {row["run_id"]: row for row in rows if row["agent_variant"] == "mini-swe-agent"}
    return 0 if latest and all(row["status"] == "completed" for row in latest.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
