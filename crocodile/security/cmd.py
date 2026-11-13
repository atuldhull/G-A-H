"""Approval-gated argv execution through the restricted process boundary."""

import math
import os
from pathlib import Path

from . import approvals, procs
from .binding import bind
from .outputs import prepare_command_result
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
    The process boundary isolates its environment and cleans up descendants.
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
    if Path(args[0]).stem.lower() == "git" or (
        action is not None and action.kind == "git"
    ):
        raise approvals.ApprovalDenied("Git requires security.git.Git fixed templates")
    if "-m" in args and any(
        arg == "crocodile" or arg.startswith("crocodile.") for arg in args
    ):
        raise approvals.ApprovalDenied("Crocodile cannot invoke itself")
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
    if not decision:
        source = (
            "; suggested by " + decision.steered_by[0] if decision.steered_by else ""
        )
        raise approvals.ApprovalDenied("command was not approved" + source)
    bound = bind(action, session)
    if Path(bound.argv[0]).stem.lower() == "git":
        raise approvals.ApprovalDenied("Git requires security.git.Git fixed templates")

    def revalidate():
        latest = approvals.validate_before_execution(action, decision, session=session)
        if latest.digest != bound.digest:
            raise approvals.ApprovalChanged("resolved command changed before spawn")
        check_integrity()

    with session.watch_integrity() as check_integrity:
        result = procs.run(
            list(bound.argv),
            Path(bound.cwd),
            root=session.repo_root,
            timeout=timeout,
            before_spawn=revalidate,
        )
    return prepare_command_result(
        result, session=session, ref="command", argv=bound.argv
    )
