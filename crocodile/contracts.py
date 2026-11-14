"""Shared contracts and integration stubs for Crocodile.

Defined in docs/04-team-split.md §2.
All parts agree on these interfaces and merge stubs first.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

# ---------------------------------------------------------------------------
# Core Type Aliases
# ---------------------------------------------------------------------------

Mode = Literal["public", "confidential"]
ActionKind = Literal["write", "shell", "git", "test_consent"]
RiskLevel = Literal["green", "amber", "red"]
Verdict = Literal["allow", "ask", "deny"]
LadderRung = Literal["strong", "cheap", "local", "pause"]
ErrorClass = Literal["auth", "rate-limit", "quota", "transient", "timeout", "caller-fault", "unknown"]


# ---------------------------------------------------------------------------
# Part 3: Security & Approval Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """Action proposed by the agent loop that requires policy/approval review."""

    kind: ActionKind
    argv: list[str] | None = None
    diff: str | None = None
    source: str | None = None
    cwd: str = "."
    paths: list[str] = field(default_factory=list)
    replacements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Decision:
    """Policy engine verdict on an action."""

    verdict: Verdict
    level: RiskLevel | None = None
    reasons: list[str] = field(default_factory=list)
    steered_by: list[str] = field(default_factory=list)
    confirm_word: str | None = None
    token: str | None = None

    def __bool__(self) -> bool:
        return self.verdict == "allow"


@dataclass(frozen=True)
class CmdResult:
    """Result of executing an approved command."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class ApprovalsInterface(Protocol):
    def ask(self, action: Action) -> Decision:
        ...


class ConfidentialInterface(Protocol):
    def mode_for(self, repo_path: str | Path) -> Mode:
        ...


class CmdInterface(Protocol):
    def run(self, argv: list[str], cwd: str | Path = ".", *, timeout: int = 120) -> CmdResult:
        ...


# ---------------------------------------------------------------------------
# Part 2: Gateway, Budget & Journal Contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Usage:
    """Token usage breakdown returned from an inference call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ToolCall:
    """Structured tool call proposed by the model."""

    id: str
    name: str
    args: dict[str, Any]
    steered_by: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChatResult:
    """Unified result returned from egress.chat."""

    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model_used: str = ""
    is_fallback: bool = False
    error_class: ErrorClass | None = None
    cost_usd: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reservation:
    """Pre-call budget reservation."""

    id: str
    principal: str
    usd: float
    model_ceiling: str
    tier: str
    est_in: int
    bound_in: int
    max_out: int
    owner_pid: int
    heartbeat: float


@dataclass
class State:
    """Minimal resumable session state."""

    session_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    current_rung: LadderRung = "cheap"
    total_spent_usd: float = 0.0
    is_paused: bool = False
    pause_reason: str | None = None


class EgressInterface(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        session: str,
        tier: str = "default",
        temperature: float | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        ...

    def reserve(self, session: str, est_tokens: int) -> Reservation:
        ...

    def reconcile(self, res: Reservation, usage: Usage) -> float:
        ...


class JournalInterface(Protocol):
    def append(self, session: str, event: dict[str, Any]) -> int:
        ...

    def resume(self, session: str) -> State:
        ...


# ---------------------------------------------------------------------------
# Default Integration Stubs (Section §2 Table)
# ---------------------------------------------------------------------------

class StubEgress:
    """Part 2 stub: Direct minimal stub with no budget checks."""

    def __init__(self, default_model: str = "anthropic/claude-haiku-5-5") -> None:
        self.default_model = default_model

    def reserve(self, session: str, est_tokens: int) -> Reservation:
        return Reservation(
            id=f"stub-res-{int(time.time() * 1000)}",
            principal="stub-principal",
            usd=0.001,
            model_ceiling=self.default_model,
            tier="default",
            est_in=est_tokens,
            bound_in=est_tokens,
            max_out=1024,
            owner_pid=os.getpid(),
            heartbeat=time.time(),
        )

    def reconcile(self, res: Reservation, usage: Usage) -> float:
        return 0.0005

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        session: str,
        tier: str = "default",
        temperature: float | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            text="Stub response: ok",
            tool_calls=[],
            usage=Usage(input_tokens=100, output_tokens=10, total_tokens=110),
            model_used=self.default_model,
            is_fallback=False,
            error_class=None,
            cost_usd=0.0005,
        )


class StubJournal:
    """Part 2 stub: Appends to a simple JSONL file."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or Path(".crocodile_stub_journal.jsonl")

    def append(self, session: str, event: dict[str, Any]) -> int:
        entry = {"session": session, "ts": time.time(), "event": event}
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return 1

    def resume(self, session: str) -> State:
        events: list[dict[str, Any]] = []
        if self.log_path.exists():
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get("session") == session:
                            events.append(data.get("event", {}))
        return State(session_id=session, events=events)


class StubApprovals:
    """Part 3 stub: Prompts console y/N."""

    def ask(self, action: Action) -> Decision:
        print(f"\n[STUB APPROVAL] {action.kind}: {action.argv or action.diff or action.paths}")
        try:
            ans = input("Approve? [y/N]: ").strip().lower()
            if ans == "y":
                return Decision(verdict="allow", level="amber")
            return Decision(verdict="deny", level="red", reasons=["user denied"])
        except (EOFError, OSError):
            return Decision(verdict="deny", level="red", reasons=["no console input"])


class StubConfidential:
    """Part 3 stub: Always returns 'public'."""

    def mode_for(self, repo_path: str | Path) -> Mode:
        return "public"


class StubCmd:
    """Part 3 stub: Subprocess run with shell=False."""

    def run(self, argv: list[str], cwd: str | Path = ".", *, timeout: int = 120) -> CmdResult:
        res = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, shell=False)
        return CmdResult(argv=argv, returncode=res.returncode, stdout=res.stdout, stderr=res.stderr)


# Module-level instances of the stubs for direct import
egress = StubEgress()
journal = StubJournal()
approvals = StubApprovals()
confidential = StubConfidential()
cmd = StubCmd()
