"""Part 1 adapters: plug Part 2's gateway and Part 3's security into the agent loop unchanged.

The loop talks to small agent-side interfaces (crocodile.agent_types). These classes translate
to the real implementations so neither side has to change its tested code:

- GatewayEgress  -> crocodile.gateway.egress.EgressClient (reservation, failover banner, budget)
- GatewayJournal -> crocodile.gateway.journal.EventJournal (+ the session's JSONL for debugging)
- SecurityBridge -> crocodile.security.approvals / cmd / git (console-only permits)

Automatic execution requires an explicitly bound ApprovalSession.for_bench from a trusted
harness. Every command uses Part 3 permits and its hardened runner.
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


def limits_path() -> Path:
    """Admin-owned per-user daily limits (architecture 06). CROCODILE_LIMITS overrides for demos/tests."""
    env = os.environ.get("CROCODILE_LIMITS")
    if env:
        return Path(env)
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "crocodile" / "limits.yaml"


def load_limits() -> dict[str, float]:
    """{principal: daily_usd}. Missing file -> {} (Part 2 then applies its default limit)."""
    import yaml

    p = limits_path()
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    users = data.get("users", data) if isinstance(data, dict) else {}
    return {str(k): float(v) for k, v in users.items()}


def _state_db() -> Path:
    from .runtime_security import state_path

    return state_path()


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
            budget_manager=BudgetManager(db, prices, limits=load_limits()),
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
        except Exception:  # keyring backend missing: fall through to env
            v = None
        return v or os.environ.get(f"CROCODILE_VK_{alias.upper()}", "")

    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        session: Session,
        tier: Tier,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> ChatResult:
        from crocodile.gateway.budget import Denied

        from . import services

        context = services.security(session)
        manager = self.client.budget_manager
        if manager is None or Path(manager.db_path).resolve() != context.p3.integrity.path.resolve():
            raise RuntimeError("gateway and security must use the same protected state database")
        manager.state_integrity = context.p3.integrity
        confidential = session.mode == "confidential"
        rung = "local" if confidential else tier
        chain = chain_for(rung)
        alias = "local" if confidential else "public"
        extra = {"temperature": temperature} if self._takes_temperature else {}
        try:
            r = self.client.chat(
                messages,
                tools or None,
                session=session.id,
                principal=session.user,
                chain=chain,
                fallbacks=[] if confidential else chain[1:],
                vk=self._vk(alias),
                vk_alias=alias,
                mode=session.mode,
                tier=rung,
                max_tokens=max_tokens,
                **extra,
            )
        except Denied as e:
            raise BudgetStop(
                f"{e.reason}: needs ${e.needed:.4f}, ${e.remaining:.4f} left", remaining_usd=e.remaining
            ) from e
        finally:
            context.check(session)
        if r.text is None and not r.tool_calls and not r.model_used:
            raise RuntimeError(f"gateway returned no answer (error class: {r.error_class})")
        u = r.usage
        return ChatResult(
            text=r.text or "",
            tool_calls=[
                ToolCallReq(c.id or f"call_{i}", c.name, dict(c.args)) for i, c in enumerate(r.tool_calls)
            ],
            usage=Usage(u.input_tokens, u.output_tokens, u.cache_read_tokens),
            model_used=r.model_used,
            is_fallback=r.is_fallback,
            error_class=r.error_class,
            cost_usd=r.cost_usd,
        )

    def web_search(self, query: str, *, session: Session) -> dict:
        """Tavily via Part 2's gated search_tavily (hard-denied in confidential mode)."""
        from . import services

        services.security(session)
        if session.mode != "public":
            raise PermissionError("web search is unavailable in confidential mode")
        key = _stubs.tavily_key()
        if not key:
            raise RuntimeError("no Tavily key (set TAVILY_API_KEY or keyring crocodile/tavily)")
        r = self.client.search_tavily(query, key, mode=session.mode)
        return {"results": r.results, "credits": r.credits_used}


class GatewayJournal:
    """Durable events in Part 2's journal; the per-session JSONL stays for debugging and the bench."""

    def __init__(self) -> None:
        from crocodile.gateway.journal import EventJournal

        self.j = EventJournal(_state_db())
        self.jsonl = _stubs.StubJournal()

    def append(self, session: Session, event: str, payload: dict) -> None:
        from .runtime_security import clean

        payload = clean(payload)
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
        self.permits: dict[
            tuple[str, tuple[str, ...]], tuple[Any, Any, Any]
        ] = {}  # (session id, argv) -> (p3 session, action, decision)
        self.consented: dict[tuple[str, tuple[str, ...]], tuple[Any, Any]] = {}

    def _p3(self, s: Session):
        if s.id not in self.sessions:
            raise RuntimeError("security session was not initialized")
        p3 = self.sessions[s.id]
        p3.verify_integrity()
        p3.refresh_confidentiality()
        s.mode = p3.mode
        return p3

    def bind_session(self, s: Session, p3_session: Any) -> None:
        """Use a harness-made Part 3 session (e.g. ApprovalSession.for_bench) for this agent session."""
        if Path(p3_session.repo_root).resolve() != Path(s.repo).resolve():
            raise ValueError("security session repo_root does not match the agent repo")
        if s.approve_mode == "auto" and not p3_session.bench_auto:
            raise ValueError("auto requires a harness-created disposable bench session")
        self.sessions[s.id] = p3_session

    def _official_bench(self, s: Session) -> bool:
        p3s = self.sessions.get(s.id)
        return bool(p3s is not None and getattr(p3s, "bench_auto", False))

    # approvals -------------------------------------------------------------
    def ask(self, action: Action, session: Session) -> Decision:
        if session.approve_mode == "auto" and not self._official_bench(session):
            return Decision(False, "auto requires an official disposable bench session")
        a = self.types.Action(
            kind=action.kind,
            argv=list(action.argv) if action.argv else None,
            diff=action.diff,
            source=action.source,
            cwd=".",
            paths=list(action.paths),
            query=action.query,
            replacements=list(action.replacements),
        )
        p3s = self._p3(session)
        d = self.approvals.ask(a, session=p3s)
        ok = d.verdict == "allow"
        if ok and action.argv:
            self.permits[(session.id, tuple(action.argv))] = (p3s, a, d)
            if action.kind == "test_consent":
                self.consented[(session.id, tuple(action.argv))] = (p3s, a)
        return Decision(
            ok,
            "; ".join(d.reasons) if d.reasons else d.verdict,
            (session.id, p3s, a, d, dict(action.changes)) if ok else None,
        )

    def apply_write(self, action: Action, decision: Decision, session: Session, *, call_id: str):
        """Capture preimages, then consume the exact grant immediately before mutation."""
        import stat

        from .security.paths import atomic_write, resolve_in_repo
        from .security.undo import ShadowUndo, UndoConflict

        if not decision.approved or decision.permit is None:
            raise self.approvals.ApprovalDenied("write has no approval")
        sid, p3, proposed, grant, changes = decision.permit
        if sid != session.id or p3 is not self._p3(session) or proposed.kind != "write":
            raise self.approvals.ApprovalDenied("write permit belongs to another action/session")
        if dict(action.changes) != changes or set(changes) != set(proposed.paths):
            raise self.approvals.ApprovalChanged("proposed replacement bytes/targets changed")
        history = ShadowUndo(session.repo, session=p3)
        checkpoint = history.prepare(changes, reason=action.summary, call_id=call_id)
        mutated = False
        try:
            history.validate(checkpoint)
            self.approvals.validate_before_execution(proposed, grant, session=p3)
            for raw, data in changes.items():
                target = resolve_in_repo(raw, p3.repo_root, for_write=True, mode=p3.mode)
                permissions = (
                    stat.S_IMODE(target.stat().st_mode)
                    if target.exists()
                    else (0o666 if os.name == "nt" else 0o600)
                )
                if data is None:
                    target.unlink()
                else:
                    atomic_write(raw, data, root=p3.repo_root, mode=p3.mode)
                    os.chmod(target, permissions)
                mutated = True
            history.complete(checkpoint)
            p3.record_edit(proposed.replacements)
            return checkpoint
        except BaseException:
            if mutated:
                p3._permits.clear()
                p3._consent = None
                p3._edited_code = True
            try:
                history.cancel(checkpoint)
            except (UndoConflict, RuntimeError):
                # Retain pending checkpoint; never guess at partial-edit ownership.
                pass
            raise

    def consume(self, action: Action, decision: Decision, session: Session):
        if not decision.approved or decision.permit is None:
            raise self.approvals.ApprovalDenied("no approved action")
        sid, p3, proposed, grant, _ = decision.permit
        if (
            sid != session.id
            or p3 is not self._p3(session)
            or proposed.kind != action.kind
            or proposed.query != action.query
            or proposed.argv != action.argv
            or proposed.diff != action.diff
        ):
            raise self.approvals.ApprovalChanged("approved action changed")
        return self.approvals.validate_before_execution(proposed, grant, session=p3)

    # commands ------------------------------------------------------------------
    def run(
        self, argv: list[str], cwd: Path, *, timeout: int = 120, session: Session | None = None
    ) -> CmdResult:
        if session is None:
            matches = [
                key
                for key, value in self.permits.items()
                if key[1] == tuple(argv) and value[0].repo_root == Path(cwd).resolve()
            ]
            if len(matches) != 1:
                return CmdResult(list(argv), 126, "", "no unique approved session for command")
            key = matches[0]
        else:
            self._p3(session)
            key = (session.id, tuple(argv))
        if key not in self.permits and key in self.consented:
            # Part 3 permits are single-use. Re-ask for the same test command: Part 3 reuses the
            # session's test consent silently when nothing changed (else it prompts again).
            p3s, a = self.consented[key]
            d = self.approvals.ask(a, session=p3s)
            if d.verdict != "allow":
                return CmdResult(list(argv), 126, "", "test consent no longer valid: " + "; ".join(d.reasons))
            self.permits[key] = (p3s, a, d)
        if key not in self.permits:
            return CmdResult(list(argv), 126, "", "no unconsumed command approval")
        p3s, a, d = self.permits.pop(key)
        try:
            r = self.cmd.run(list(argv), cwd, timeout=float(timeout), session=p3s, action=a, decision=d)
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
            return CmdResult(list(argv), -1, out, "timed out", True, float(timeout))
        except self.approvals.ApprovalDenied as e:
            return CmdResult(list(argv), 126, "", f"denied by policy: {e}")
        return CmdResult(
            list(argv),
            r.returncode,
            r.stdout,
            r.stderr,
            bool(getattr(r, "timed_out", False)),
            float(getattr(r, "duration_s", 0.0)),
        )

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
