"""Deterministic Phase 1 risk decisions, independent of console and model text."""

from fnmatch import fnmatchcase
from pathlib import Path

from .binding import BoundAction, bind
from .secrets import secret_scan
from .session import ApprovalSession
from .surfaces import changes_execution
from .types import Action, Decision

RED_NAMES = {
    "conftest.py",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pytest.ini",
    "pytest.toml",
    ".pytest.toml",
    ".pytest.ini",
    "tox.ini",
    "noxfile.py",
    "makefile",
    ".pre-commit-config.yaml",
    "sitecustomize.py",
    "usercustomize.py",
    "dockerfile",
    ".gitattributes",
    ".gitmodules",
}


def risk(action: Action, bound: BoundAction, session: ApprovalSession) -> Decision:
    args = action.argv or []
    sources = [secret_scan(source) for source in bound.steered_by]
    executable = Path(bound.argv[0]).stem.lower() if bound.argv else ""
    network = (
        action.kind == "network"
        or any("://" in value for value in args)
        or (action.kind == "git" and "push" in args)
        or ("pip" in args and "install" in args)
        or (executable.startswith("pip") and "install" in args)
        or executable
        in (
            "curl",
            "wget",
            "ssh",
            "scp",
            "sftp",
            "ftp",
            "rsync",
            "nc",
            "ncat",
            "telnet",
        )
    )
    if (session.mode == "confidential" or bound.steered_by) and network:
        return Decision(
            "deny",
            reasons=["network sink denied by confidentiality or provenance"],
            steered_by=sources,
        )
    if session.bench_auto and (
        session.mode != "public"
        or network
        or action.kind not in ("write", "shell", "test_consent")
    ):
        return Decision(
            "deny",
            reasons=[
                "bench auto permits local actions in its public disposable workspace only"
            ],
            steered_by=sources,
        )
    if session.yes_green and action.kind == "test_consent":
        return Decision(
            "deny", reasons=["--yes-green cannot combine with test execution"]
        )
    red_path = any(
        Path(path).name.lower() in RED_NAMES
        or any(
            fnmatchcase(Path(path).name.lower(), pat)
            for pat in ("test_*.py", "*_test.py", "*.pth", "requirements*.txt")
        )
        or any(
            part.lower() in ("tests", ".github", ".devcontainer")
            for part in Path(path).parts
        )
        for path in bound.paths
    )
    irreversible = action.kind == "git" and any(
        arg in ("push", "--hard", "-fdx", "-D") for arg in args
    )
    if (
        bound.steered_by
        or red_path
        or irreversible
        or action.kind == "test_consent"
        or (session.mode == "confidential" and action.kind != "write")
    ):
        return Decision("ask", "red", steered_by=sources)
    surface = not action.replacements or any(
        changes_execution(text) for text in action.replacements
    )
    level = (
        "green"
        if action.kind == "write" and not surface and len(bound.paths) <= 3
        else "amber"
    )
    return Decision("ask", level)


def decide(action: Action, *, session: ApprovalSession | None = None) -> Decision:
    """Schema/hard failure, confidentiality, provenance, then consent or ASK."""
    session = session if session is not None else ApprovalSession()
    try:
        bound = bind(action, session)
        decision = risk(action, bound, session)
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        return Decision("deny", reasons=[secret_scan(str(error))])
    if decision.verdict != "deny" and session.bench_auto:
        return Decision(
            "allow",
            decision.level,
            reasons=["trusted bench auto"],
            steered_by=decision.steered_by,
        )
    if (
        decision.verdict != "deny"
        and action.kind == "test_consent"
        and not bound.steered_by
        and session._consent == bound.digest
    ):
        return Decision("allow", reasons=["valid session test consent"])
    return decision
