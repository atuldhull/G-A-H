"""Part 1 adapters: plug Part 2's gateway and Part 3's security into the agent loop unchanged.

The loop talks to small agent-side interfaces (crocodile.agent_types). These classes translate
to the real implementations so neither side has to change its tested code:

- GatewayEgress  -> crocodile.gateway.egress.EgressClient (reservation, failover banner, budget)
- GatewayJournal -> crocodile.gateway.journal.EventJournal (+ the session's JSONL for debugging)
- SecurityBridge -> crocodile.security.approvals / cmd / git (console-only permits)

Bench sandbox runs (`--yes`, throwaway copies) cannot use Part 3's console approvals by design,
so in approve_mode == "auto" the bridge falls back to the plain runner and says so in the journal.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from . import _stubs
from .agent_types import (
    Action,
    BudgetStop,
    ChatResult,
    CmdResult,
    Decision,
    Mode,
    Session,
    Tier,
    ToolCallReq,
    Usage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Model chain per tier: primary first, then explicit fallbacks. Override with CROCODILE_CHAIN_<TIER>.
DEFAULT_CHAINS: dict[str, list[str]] = {
    "cheap": ["anthropic/claude-haiku-5-5", "openai/gpt-5-mini"],
    "strong": ["anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5"],
    "local": ["ollama/qwen2.5-coder:7b"],
}


def chain_for(tier: str) -> list[str]:
    env = os.environ.get(f"CROCODILE_CHAIN_{tier.upper()}", "")
    return [m.strip() for m in env.split(",") if m.strip()] or list(DEFAULT_CHAINS[tier])


def _state_db() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "crocodile" / "state.db"


# ---------------------------------------------------------------- Part 2: gateway

class GatewayEgress:
    def __init__(self) -> None:
        from crocodile.gateway.budget import BudgetManager
        from crocodile.gateway.egress import EgressClient
        from crocodile.gateway.journal import EventJournal
        from crocodile.gateway.prices import PriceTable

        db = _state_db()
        prices = PriceTable.from_yaml_file(os.environ.get("CROCODILE_PRICES", PROJECT_ROOT / "prices.yaml"))
        self.client = EgressClient(
            bifrost_base_url=os.environ.get("CROCODILE_BIFROST_URL", "http://127.0.0.1:8080"),
            budget_manager=BudgetManager(db, prices),
            journal=EventJournal(db),
            price_table=prices,
        )
        import inspect
        self._takes_temperature = "temperature" in inspect.signature(self.client.chat).parameters

    @staticmethod
    def _vk(alias: str) -> str:
        """Virtual key from Windows Credential Manager (keyring), env only as a dev fallback."""
        try:
            import keyring
            v = keyring.get_password("crocodile", f"vk-{alias}")
        except Exception:   # keyring backend missing: fall through to env
            v = None
        return v or os.environ.get(f"CROCODILE_VK_{alias.upper()}", "")

    def chat(self, messages: list[dict], tools: list[dict], *, session: Session, tier: Tier,
             max_tokens: int = 4096, temperature: float = 0.0) -> ChatResult:
        from crocodile.gateway.budget import Denied

        confidential = session.mode == "confidential"
        rung = "local" if confidential else tier
        chain = chain_for(rung)
        alias = "local" if confidential else "public"
        extra = {"temperature": temperature} if self._takes_temperature else {}
        try:
            r = self.client.chat(messages, tools or None, session=session.id, principal=session.user,
                                 chain=chain, fallbacks=[] if confidential else chain[1:],
                                 vk=self._vk(alias), vk_alias=alias, mode=session.mode, tier=rung,
                                 max_tokens=max_tokens, **extra)
        except Denied as e:
            raise BudgetStop(f"{e.reason}: needs ${e.needed:.4f}, ${e.remaining:.4f} left",
                             remaining_usd=e.remaining) from e
        if r.text is None and not r.tool_calls and not r.model_used:
            raise RuntimeError(f"gateway returned no answer (error class: {r.error_class})")
        u = r.usage
        return ChatResult(
            text=r.text or "",
            tool_calls=[ToolCallReq(c.id or f"call_{i}", c.name, dict(c.args)) for i, c in enumerate(r.tool_calls)],
            usage=Usage(u.input_tokens, u.output_tokens, u.cache_read_tokens),
            model_used=r.model_used,
            is_fallback=r.is_fallback,
            error_class=r.error_class,
            cost_usd=r.cost_usd,
        )


class GatewayJournal:
    """Durable events in Part 2's journal; the per-session JSONL stays for debugging and the bench."""

    def __init__(self) -> None:
        from crocodile.gateway.journal import EventJournal
        self.j = EventJournal(_state_db())
        self.jsonl = _stubs.StubJournal()

    def append(self, session: Session, event: str, payload: dict) -> None:
        self.jsonl.append(session, event, payload)
        self.j.append(session.id, event, payload)

    def resume(self, session_id: str) -> list[dict]:
        state = self.j.resume(session_id)
        return list(getattr(state, "events", []))


# ---------------------------------------------------------------- Part 3: security

class SecurityBridge:
    """approvals.ask + cmd.run + read-only git on Part 3's permits (one ApprovalSession per agent session)."""

    def __init__(self) -> None:
        from crocodile.security import approvals, cmd, types
        self.approvals, self.cmd, self.types = approvals, cmd, types
        self.sessions: dict[str, Any] = {}
        self.permits: dict[tuple[str, ...], tuple[Any, Any, Any]] = {}   # argv -> (p3 session, action, decision)
        self.auto_argv: set[tuple[str, ...]] = set()
        self.plain = _stubs.StubCmd()

    def _p3(self, s: Session):
        if s.id not in self.sessions:
            self.sessions[s.id] = self.approvals.ApprovalSession(repo_root=Path(s.repo), mode=s.mode)
        return self.sessions[s.id]

    def bind_session(self, s: Session, p3_session: Any) -> None:
        """Use a harness-made Part 3 session (e.g. ApprovalSession.for_bench) for this agent session."""
        if Path(p3_session.repo_root).resolve() != Path(s.repo).resolve():
            raise ValueError("security session repo_root does not match the agent repo")
        self.sessions[s.id] = p3_session

    def _official_bench(self, s: Session) -> bool:
        p3s = self.sessions.get(s.id)
        return bool(p3s is not None and getattr(p3s, "bench_auto", False))

    # approvals -------------------------------------------------------------
    def ask(self, action: Action, session: Session) -> Decision:
        if session.approve_mode == "auto" and not self._official_bench(session):
            # CLI --yes on a throwaway copy, without Part 3's bench session: plain runner, logged.
            if action.argv:
                self.auto_argv.add(tuple(action.argv))
            return Decision(True, "auto (bench sandbox; Part 3 console approvals bypassed)")
        a = self.types.Action(kind=action.kind, argv=list(action.argv) if action.argv else None,
                              diff=action.diff, source=action.source, cwd=".", paths=list(action.paths))
        p3s = self._p3(session)
        d = self.approvals.ask(a, session=p3s)
        ok = d.verdict == "allow"
        if ok and action.argv:
            self.permits[tuple(action.argv)] = (p3s, a, d)
        return Decision(ok, "; ".join(d.reasons) if d.reasons else d.verdict)

    # commands ------------------------------------------------------------------
    def run(self, argv: list[str], cwd: Path, *, timeout: int = 120) -> CmdResult:
        key = tuple(argv)
        if key in self.auto_argv and key not in self.permits:
            return self.plain.run(argv, cwd, timeout=timeout)
        p3s, a, d = self.permits.pop(key, (None, None, None))   # permits are single-use
        try:
            r = self.cmd.run(list(argv), cwd, timeout=float(timeout), session=p3s, action=a, decision=d)
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
            return CmdResult(list(argv), -1, out, "timed out", True, float(timeout))
        except self.approvals.ApprovalDenied as e:
            return CmdResult(list(argv), 126, "", f"denied by policy: {e}")
        return CmdResult(list(argv), r.returncode, r.stdout, r.stderr,
                         bool(getattr(r, "timed_out", False)), float(getattr(r, "duration_s", 0.0)))

    def git_read(self, op: str, session: Session) -> CmdResult:
        from crocodile.security.git import Git, GitDenied
        try:
            with Git(self._p3(session)) as g:
                r = g.run(op)
        except GitDenied as e:
            return CmdResult(["git", op], 126, "", f"denied by policy: {e}")
        return CmdResult(["git", op], r.returncode, r.stdout, r.stderr)


class SecurityConfidential:
    def mode_for(self, repo_path: Path) -> Mode:
        from crocodile.security.confidential import mode_for
        return mode_for(repo_path)
