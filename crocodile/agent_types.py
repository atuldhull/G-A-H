"""Shared interfaces between the four parts (see docs/04-team-split.md §2).

Changing anything here needs the two affected owners to agree. Each part implements its side in its
own module with exactly these names; `crocodile.services` picks the real module when it exists and
falls back to `crocodile._stubs` until then.

    Part 2  crocodile.gateway.egress   chat(...)
            crocodile.gateway.journal  append(...), resume(...)
    Part 3  crocodile.security.approvals  ask(...)
            crocodile.security.cmd        run(...)
            crocodile.security.confidential  mode_for(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

Mode = Literal["public", "confidential"]
Tier = Literal["strong", "cheap", "local"]
Level = Literal["green", "amber", "red"]
ActionKind = Literal["write", "shell", "git", "test_consent", "network"]

# Journal event names (owner: Part 2). Payloads are plain JSON dicts.
EVENTS = (
    "session_start", "model_call", "tool_started", "tool_done", "approval",
    "takeover", "budget_warn", "budget_stop", "escalate", "green", "session_end",
)


# ---------- model calls (Part 2 implements, Part 1 calls) ----------

@dataclass
class Usage:
    prompt_tokens: int = 0          # includes cached tokens (Bifrost/OpenAI convention)
    completion_tokens: int = 0
    cached_tokens: int = 0          # subset of prompt_tokens served from cache

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens


@dataclass
class ToolCallReq:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCallReq]
    usage: Usage
    model_used: str
    is_fallback: bool = False
    error_class: str | None = None   # error class of the primary when a fallback answered
    cost_usd: float | None = None    # filled by Part 2 when known
    finish_reason: str | None = None


class BudgetStop(Exception):
    """Raised by egress.chat when the user's budget cannot cover the call (defined behaviour at limit)."""

    def __init__(self, message: str, remaining_usd: float | None = None):
        super().__init__(message)
        self.remaining_usd = remaining_usd


# ---------- approvals and commands (Part 3 implements, Part 1 calls) ----------

@dataclass
class Action:
    kind: ActionKind
    summary: str                         # one line, shown as the panel title
    argv: list[str] | None = None        # for shell/git/test_consent
    diff: str | None = None              # for write
    source: str | None = None            # "README.md:40" when repo text suggested it (provenance-lite)
    level: Level = "amber"
    reasons: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)   # repo-relative files a write touches
    query: str | None = None                          # network: the outbound search text


@dataclass
class Decision:
    approved: bool
    reason: str = ""


@dataclass
class CmdResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_s: float = 0.0


# ---------- session (Part 1 owns; read by everyone) ----------

@dataclass
class Session:
    id: str
    repo: Path
    mode: Mode
    user: str = "default"
    approve_mode: Literal["ask", "auto"] = "ask"   # "auto" only via the bench CLI flag, never from the model
    flags: set[str] = field(default_factory=set)
    state_dir: Path | None = None                  # per-session scratch: spill files, journal


class EgressAPI(Protocol):
    def chat(self, messages: list[dict], tools: list[dict], *, session: Session, tier: Tier,
             max_tokens: int = 4096, temperature: float = 0.0) -> ChatResult: ...

    def web_search(self, query: str, *, session: Session) -> dict: ...


class JournalAPI(Protocol):
    def append(self, session: Session, event: str, payload: dict) -> None: ...
    def resume(self, session_id: str) -> list[dict]: ...


class ApprovalsAPI(Protocol):
    def ask(self, action: Action, session: Session) -> Decision: ...


class CmdAPI(Protocol):
    def run(self, argv: list[str], cwd: Path, *, timeout: int = 120) -> CmdResult: ...


class ConfidentialAPI(Protocol):
    def mode_for(self, repo_path: Path) -> Mode: ...
