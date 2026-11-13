"""Deterministic Phase 1 risk decisions, independent of console and model text."""

from fnmatch import fnmatchcase
from pathlib import Path

from .binding import BoundAction, bind
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
    network = (
        any("://" in value for value in args)
        or (action.kind == "git" and "push" in args)
        or ("pip" in args and "install" in args)
    )
    if (session.mode == "confidential" or action.source) and network:
        return Decision(
            "deny", reasons=["network sink denied by confidentiality or provenance"]
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
        action.source
        or red_path
        or irreversible
        or action.kind == "test_consent"
        or (session.mode == "confidential" and action.kind != "write")
    ):
        return Decision(
            "ask", "red", steered_by=[action.source] if action.source else []
        )
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
        return Decision("deny", reasons=[str(error)])
    if (
        decision.verdict != "deny"
        and action.kind == "test_consent"
        and not action.source
        and session._consent == bound.digest
    ):
        return Decision("allow", reasons=["valid session test consent"])
    return decision
