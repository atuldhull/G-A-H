"""Approval-gated argv execution; full process hardening follows in Phase 2."""

import math
import os
import subprocess
from pathlib import Path

from . import approvals
from .types import Action, CmdResult, Decision


def run(
    argv: list[str],
    cwd: str | os.PathLike[str],
    *,
    timeout: float,
    session: approvals.ApprovalSession | None = None,
    action: Action | None = None,
    decision: Decision | None = None,
) -> CmdResult:
    """Run an argv list without a shell, capturing output and exit status.

    Obtain approval here or consume a caller's previously issued decision.
    TimeoutExpired and OSError propagate; nonzero exits return normally.
    Environment isolation, Windows job objects and Git hardening remain Phase 2.
    """
    if not isinstance(argv, list) or not argv:
        raise TypeError("argv must be a non-empty list of strings")
    if any(not isinstance(arg, str) or "\0" in arg for arg in argv):
        raise ValueError("argv entries must be strings without NUL characters")
    if not argv[0]:
        raise ValueError("argv[0] must not be empty")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError("timeout must be a positive finite number")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    args = argv.copy()
    session = (
        session if session is not None else approvals.ApprovalSession(repo_root=cwd)
    )
    action = (
        action
        if action is not None
        else Action("shell", argv=args, cwd=str(Path(cwd).resolve()))
    )
    if action.kind not in ("shell", "git", "test_consent") or action.argv != args:
        raise approvals.ApprovalDenied("command arguments do not match the action")
    if (session.repo_root / action.cwd).resolve() != Path(cwd).resolve():
        raise approvals.ApprovalDenied("command cwd does not match the action")
    if action.kind != "test_consent" and (
        "pytest" in args or Path(args[0]).stem.lower() == "pytest"
    ):
        raise approvals.ApprovalDenied(
            "pytest requires an explicit test_consent action"
        )
    decision = (
        decision if decision is not None else approvals.ask(action, session=session)
    )
    # Build options before the immediate pre-spawn validation.
    child_env = None
    if action.kind == "test_consent":
        child_env = os.environ.copy()
        child_env.pop("PYTEST_ADDOPTS", None)
        child_env.pop("PYTEST_PLUGINS", None)
        child_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    bound = approvals.validate_before_execution(action, decision, session=session)
    result = subprocess.run(
        list(bound.argv),
        cwd=bound.cwd,
        timeout=timeout,
        shell=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=child_env,
    )
    return CmdResult(list(bound.argv), result.returncode, result.stdout, result.stderr)
