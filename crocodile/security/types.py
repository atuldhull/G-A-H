"""Proposed contracts, local to Part 3 until a second owner agrees.

There is no shared contracts.py on person-3 yet. These definitions must be
reconciled with the other owners before promotion to the shared module.
"""

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["public", "confidential"]
ActionKind = Literal["write", "shell", "git", "test_consent"]
RiskLevel = Literal["green", "amber", "red"]


@dataclass(frozen=True)
class Action:
    """Minimum proposal described by the team-split interface table."""

    kind: ActionKind
    argv: list[str] | None = None
    diff: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class Decision:
    """Decision shape from Architecture 02; ask returns allow or deny."""

    verdict: Literal["allow", "ask", "deny"]
    level: RiskLevel | None = None
    reasons: list[str] = field(default_factory=list)
    steered_by: list[str] = field(default_factory=list)
    confirm_word: str | None = None
    token: str | None = None

    def __bool__(self) -> bool:
        return self.verdict == "allow"


@dataclass(frozen=True)
class CmdResult:
    """Completed command; spawn errors and timeouts propagate to the caller."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
