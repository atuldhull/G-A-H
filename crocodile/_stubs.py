"""Temporary stand-ins for Part 2 and Part 3 so Part 1 and Part 4 can run end to end today.

None of these enforce budget, privacy or approval policy properly. They are replaced automatically
(see crocodile.services) as soon as the real module exists. Do not ship a demo on stubs.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .contracts import Action, ChatResult, CmdResult, Decision, Mode, Session, Tier, ToolCallReq, Usage


class StubEgress:
    """Calls one OpenAI-compatible endpoint directly. No budget, no fallbacks."""

    def __init__(self) -> None:
        # Stub only: the real egress (Part 2) reads keys from Credential Manager, never env.
        self.base = os.environ.get("CROCODILE_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        self.models = {
            "strong": os.environ.get("CROCODILE_MODEL_STRONG", "anthropic/claude-sonnet-5-5"),
            "cheap": os.environ.get("CROCODILE_MODEL_CHEAP", "anthropic/claude-haiku-5-5"),
            "local": os.environ.get("CROCODILE_MODEL_LOCAL", "ollama/qwen2.5-coder:7b"),
        }
        self.vk = os.environ.get("CROCODILE_VK", "")
        # Dev only: name of an env var holding a provider key, sent as a Bearer token (never logged).
        key_var = os.environ.get("CROCODILE_API_KEY_ENV", "")
        self.bearer = os.environ.get(key_var, "") if key_var else ""

    def chat(self, messages: list[dict], tools: list[dict], *, session: Session, tier: Tier,
             max_tokens: int = 4096, temperature: float = 0.0) -> ChatResult:
        import httpx

        model = self.models["local" if session.mode == "confidential" else tier]
        body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            body["tools"] = tools
        headers = {"x-bf-session-id": session.id}
        if self.vk:
            headers["x-bf-vk"] = self.vk
        if self.bearer:
            headers = {"Authorization": f"Bearer {self.bearer}"}   # direct provider: no Bifrost headers
        tries = 5
        for attempt in range(1, tries + 1):   # retry 429/5xx/timeouts (free-tier limits, Ollama OOM restart)
            try:
                r = httpx.post(f"{self.base}/chat/completions", json=body, headers=headers, timeout=600)
                if (r.status_code != 429 and r.status_code < 500) or attempt == tries:
                    break
            except httpx.TimeoutException:
                if attempt == tries:
                    raise
            time.sleep(min(60, 5 * 2 ** (attempt - 1)))
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            calls.append(ToolCallReq(id=tc.get("id") or f"call_{len(calls)}", name=fn.get("name", ""),
                                     arguments=args))
        u = data.get("usage") or {}
        cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
        return ChatResult(
            text=msg.get("content") or "",
            tool_calls=calls,
            usage=Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0), cached),
            model_used=data.get("model", model),
            finish_reason=choice.get("finish_reason"),
        )


class StubJournal:
    def append(self, session: Session, event: str, payload: dict) -> None:
        if session.state_dir is None:
            return
        rec = {"ts": time.time(), "session": session.id, "event": event, **payload}
        with open(session.state_dir / "journal.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def resume(self, session_id: str) -> list[dict]:
        return []


class StubApprovals:
    """Console y/n. Part 3 replaces this with CONIN$-only prompts, levels and provenance."""

    def ask(self, action: Action, session: Session) -> Decision:
        if session.approve_mode == "auto":
            return Decision(True, "auto (bench)")
        from rich.console import Console
        from rich.panel import Panel

        c = Console(stderr=True)
        body = action.diff or (" ".join(action.argv) if action.argv else "")
        if action.source:
            body = f"suggested by {action.source}\n\n{body}"
        c.print(Panel(body[:4000], title=f"[{action.level}] {action.kind}: {action.summary}"))
        ans = input("Approve? [y/N] ").strip().lower()
        return Decision(ans in ("y", "yes"), "user")


class StubCmd:
    def run(self, argv: list[str], cwd: Path, *, timeout: int = 120) -> CmdResult:
        t0 = time.monotonic()
        try:
            p = subprocess.run(argv, cwd=cwd, shell=False, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout,
                               stdin=subprocess.DEVNULL)
            return CmdResult(argv, p.returncode, p.stdout, p.stderr, False, time.monotonic() - t0)
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
            return CmdResult(argv, -1, out, "timed out", True, time.monotonic() - t0)
        except FileNotFoundError as e:
            return CmdResult(argv, 127, "", str(e), False, time.monotonic() - t0)


class StubConfidential:
    def mode_for(self, repo_path: Path) -> Mode:
        return "public"
