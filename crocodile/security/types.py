"""Shared result contracts with a local network-capable Action extension.

No shared contract is changed. The adapter accepts the exact shared Action;
normal owner calls and Part 3 network proposals use the same validated binding.
"""

from dataclasses import dataclass
from typing import Literal

from crocodile.contracts import Action as SharedAction
from crocodile.contracts import CmdResult, Decision, Mode

ActionKind = Literal["write", "shell", "git", "test_consent", "network"]
RiskLevel = Literal["green", "amber", "red"]


@dataclass(frozen=True)
class Action(SharedAction):
    """Part 3 keeps proposed network fields local until shared-owner approval."""

    kind: ActionKind
    query: str | None = None
    url: str | None = None


__all__ = ["Action", "ActionKind", "CmdResult", "Decision", "Mode", "RiskLevel"]
