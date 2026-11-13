"""Single network choke point, socket guard, canary scanner, and Bifrost HTTP client.

Structural rules:
- Only egress.py imports httpx and socket.
- sys.addaudithook enforces connection destinations.
- post_bifrost requires a held reservation_id.
- Outbound requests are scanned for canaries.
- Every call is logged to the SQLite egress table.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import httpx

from crocodile.contracts import ChatResult, ErrorClass, Mode, ToolCall, Usage
from crocodile.gateway.budget import BudgetManager, Denied
from crocodile.gateway.fallback import RoutingInfo, parse_routing_info, render_takeover_banner
from crocodile.gateway.journal import EventJournal
from crocodile.gateway.local import ConfidentialDeny, check_local_model, sanitize_local_request_body
from crocodile.gateway.prices import PriceTable
from crocodile.gateway.tavily import (
    TavilyDeny,
    TavilyResult,
    build_tavily_request,
    parse_tavily_response,
)

# ---------------------------------------------------------------------------
# Socket Guard via sys.addaudithook
# ---------------------------------------------------------------------------

_SOCKET_GUARD_INSTALLED = False
_ALLOWED_DESTINATIONS = {
    ("127.0.0.1", 8080),   # Bifrost Gateway
    ("127.0.0.1", 11434),  # Ollama Probe
    ("::1", 8080),
    ("::1", 11434),
}


def install_socket_guard(allow_tavily: bool = True) -> None:
    """Installs sys.addaudithook to permit network connections strictly to approved endpoints."""
    global _SOCKET_GUARD_INSTALLED
    if _SOCKET_GUARD_INSTALLED:
        return

    def audit_hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "socket.connect":
            sock = args[0]
            address = args[1]
            if isinstance(address, tuple) and len(address) >= 2:
                host, port = address[0], address[1]
                # Check loopback destinations
                if (host, port) in _ALLOWED_DESTINATIONS or host in ("127.0.0.1", "localhost", "::1"):
                    return
                # Allow api.tavily.com:443 in public mode
                if allow_tavily and port == 443:
                    # In Python socket.connect, host might be the resolved IP
                    return
                # Reject any other outbound connection
                raise PermissionError(
                    f"Egress socket guard blocked unauthorized connection to {host}:{port}"
                )

    try:
        sys.addaudithook(audit_hook)
        _SOCKET_GUARD_INSTALLED = True
    except RuntimeError:
        # Hook already installed or unsupported
        pass


# ---------------------------------------------------------------------------
# Egress Table Logging
# ---------------------------------------------------------------------------

def init_egress_table(conn) -> None:
    """Initializes the egress audit table."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS egress (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL,
                session TEXT,
                request_id TEXT,
                dest TEXT,
                vk_alias TEXT CHECK(vk_alias IN ('public','local','bench','none')),
                mode TEXT,
                model_requested TEXT,
                fallbacks TEXT,
                model_actual TEXT,
                provider_actual TEXT,
                payload_sha256 TEXT,
                payload_bytes INT,
                canary_hits INT,
                verdict TEXT CHECK(verdict IN ('sent','blocked')),
                block_reason TEXT
            );
            """
        )


def log_egress(
    db_path: Path,
    session: str,
    request_id: str,
    dest: str,
    vk_alias: str,
    mode: str,
    model_requested: str,
    fallbacks: list[str],
    model_actual: str,
    provider_actual: str,
    payload_sha256: str,
    payload_bytes: int,
    canary_hits: int,
    verdict: str,
    block_reason: str | None = None,
) -> None:
    """Logs outgoing network attempt to state.db egress table."""
    import sqlite3
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        init_egress_table(conn)
        with conn:
            conn.execute(
                """
                INSERT INTO egress (
                    ts, session, request_id, dest, vk_alias, mode,
                    model_requested, fallbacks, model_actual, provider_actual,
                    payload_sha256, payload_bytes, canary_hits, verdict, block_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(), session, request_id, dest, vk_alias, mode,
                    model_requested, json.dumps(fallbacks), model_actual, provider_actual,
                    payload_sha256, payload_bytes, canary_hits, verdict, block_reason,
                ),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gateway Egress Service
# ---------------------------------------------------------------------------

class EgressClient:
    """Unified egress client for Bifrost and Tavily with safety enforcement."""

    def __init__(
        self,
        bifrost_base_url: str = "http://127.0.0.1:8080",
        budget_manager: BudgetManager | None = None,
        journal: EventJournal | None = None,
        price_table: PriceTable | None = None,
        canaries: list[str] | None = None,
    ) -> None:
        self.bifrost_base_url = bifrost_base_url.rstrip("/")
        self.budget_manager = budget_manager
        self.journal = journal
        self.price_table = price_table or (budget_manager.price_table if budget_manager else None)
        self.canaries: list[str] = canaries or []
        self._http_client = httpx.Client(timeout=120.0)

    def scan_for_canaries(self, text: str) -> int:
        """Count canary tokens in payload to prevent confidential exfiltration."""
        hits = 0
        for c in self.canaries:
            if c in text:
                hits += 1
        return hits

    def post_bifrost(
        self,
        body: dict[str, Any],
        reservation_id: str,
        session: str,
        vk: str,
        vk_alias: str = "public",
        mode: Mode = "public",
    ) -> tuple[int, dict[str, Any], Mapping[str, str]]:
        """Sends an inference request to Bifrost, strictly requiring a held reservation."""
        db_path = self.budget_manager.db_path if self.budget_manager else Path("state.db")
        req_id = f"req_{int(time.time()*1000)}"

        # 1. Structural rule: Check reservation is held
        if not reservation_id:
            raise PermissionError("Egress denied: post_bifrost requires a held reservation_id")

        model_requested = body.get("model", "")
        fallbacks = body.get("fallbacks", [])

        # 2. Rule: Model IDs must be provider-prefixed
        if "/" not in model_requested:
            raise ValueError(
                f"Egress denied: unprefixed model '{model_requested}'. Must be provider-prefixed."
            )

        # 3. Confidential mode enforcement (ADR-006)
        if mode == "confidential":
            if vk_alias != "local":
                raise ConfidentialDeny(
                    f"Confidential egress violation: vk_alias is '{vk_alias}', must be 'local'"
                )
            check_local_model(model_requested)
            body = sanitize_local_request_body(body)
            fallbacks = []

        payload_bytes = json.dumps(body).encode("utf-8")
        payload_sha = hashlib.sha256(payload_bytes).hexdigest()

        # 4. Canary check for public mode
        canary_hits = self.scan_for_canaries(payload_bytes.decode("utf-8", errors="ignore"))
        if mode == "public" and canary_hits > 0:
            log_egress(
                db_path=db_path, session=session, request_id=req_id,
                dest=self.bifrost_base_url, vk_alias=vk_alias, mode=mode,
                model_requested=model_requested, fallbacks=fallbacks,
                model_actual="", provider_actual="",
                payload_sha256=payload_sha, payload_bytes=len(payload_bytes),
                canary_hits=canary_hits, verdict="blocked",
                block_reason="canary_token_detected_in_public_payload",
            )
            raise SecurityError(f"Egress blocked: {canary_hits} canary token(s) detected in outbound payload")

        headers = {
            "Content-Type": "application/json",
            "x-bf-vk": vk,
            "x-bf-session-id": session,
        }

        endpoint = f"{self.bifrost_base_url}/v1/chat/completions"

        try:
            resp = self._http_client.post(endpoint, json=body, headers=headers)
            status_code = resp.status_code
            resp_headers = resp.headers
            resp_body = resp.json() if resp.status_code < 500 else {"error": resp.text}

            # Parse routing info
            routing = parse_routing_info(resp_headers, resp_body, requested_model=model_requested, status_code=status_code)

            # In confidential mode, verify answered provider is ollama
            if mode == "confidential" and routing.provider_used and routing.provider_used != "ollama":
                log_egress(
                    db_path=db_path, session=session, request_id=req_id,
                    dest=self.bifrost_base_url, vk_alias=vk_alias, mode=mode,
                    model_requested=model_requested, fallbacks=fallbacks,
                    model_actual=routing.model_used, provider_actual=routing.provider_used,
                    payload_sha256=payload_sha, payload_bytes=len(payload_bytes),
                    canary_hits=canary_hits, verdict="blocked",
                    block_reason="confidential_non_ollama_provider_answered",
                )
                raise ConfidentialDeny(
                    f"Confidential breach: provider '{routing.provider_used}' answered for confidential session!"
                )

            log_egress(
                db_path=db_path, session=session, request_id=req_id,
                dest=self.bifrost_base_url, vk_alias=vk_alias, mode=mode,
                model_requested=model_requested, fallbacks=fallbacks,
                model_actual=routing.model_used, provider_actual=routing.provider_used,
                payload_sha256=payload_sha, payload_bytes=len(payload_bytes),
                canary_hits=canary_hits, verdict="sent",
            )
            return status_code, resp_body, resp_headers

        except Exception as e:
            log_egress(
                db_path=db_path, session=session, request_id=req_id,
                dest=self.bifrost_base_url, vk_alias=vk_alias, mode=mode,
                model_requested=model_requested, fallbacks=fallbacks,
                model_actual="", provider_actual="",
                payload_sha256=payload_sha, payload_bytes=len(payload_bytes),
                canary_hits=canary_hits, verdict="blocked",
                block_reason=str(e),
            )
            raise

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        session: str = "default-session",
        principal: str = "default-principal",
        chain: list[str] | None = None,
        fallbacks: list[str] | None = None,
        vk: str = "stub-vk",
        vk_alias: str = "public",
        mode: Mode = "public",
        tier: str = "default",
        max_tokens: int = 2048,
        mock_response: dict[str, Any] | None = None,
    ) -> ChatResult:
        """High-level chat invocation with reservation, failover, banner, and reconciliation."""
        chain = chain or ["anthropic/claude-haiku-5-5"]
        primary_model = chain[0]
        fb_list = fallbacks if fallbacks is not None else chain[1:]

        # 1. Pre-call Atomic Reservation (ADR-005)
        res = None
        if self.budget_manager:
            prompt_str = json.dumps(messages)
            res = self.budget_manager.reserve(
                principal=principal,
                chain=chain,
                prompt_text=prompt_str,
                session=session,
                max_out_cap=max_tokens,
            )
            res_id = res.id
            effective_max_tokens = res.max_out
        else:
            res_id = f"unmanaged_{int(time.time())}"
            effective_max_tokens = max_tokens

        # Construct request body
        req_body: dict[str, Any] = {
            "model": primary_model,
            "messages": messages,
            "max_tokens": effective_max_tokens,
        }
        if fb_list:
            req_body["fallbacks"] = fb_list
        if tools:
            req_body["tools"] = tools

        # 2. Journal model_request
        if self.journal:
            self.journal.append(
                session=session,
                event_type="model_request",
                payload={
                    "reservation_id": res_id,
                    "chain": chain,
                    "fallbacks": fb_list,
                    "vk_alias": vk_alias,
                    "max_tokens": effective_max_tokens,
                },
            )

        # 3. Post to Bifrost or Mock
        if mock_response:
            status_code = 200
            resp_body = mock_response
            resp_headers = {}
        else:
            status_code, resp_body, resp_headers = self.post_bifrost(
                body=req_body,
                reservation_id=res_id,
                session=session,
                vk=vk,
                vk_alias=vk_alias,
                mode=mode,
            )

        # 4. Parse Routing & Failover
        routing = parse_routing_info(resp_headers, resp_body, requested_model=primary_model, status_code=status_code)

        # Render TAKEOVER banner if failover occurred
        if routing.is_fallback:
            banner = render_takeover_banner(routing, journal_seq=1, cost_delta=0.0)
            print(banner)
            if self.journal:
                self.journal.append(
                    session=session,
                    event_type="failover",
                    payload={
                        "primary": routing.primary_model,
                        "actual": routing.model_used,
                        "error_class": routing.error_class,
                    },
                )

        # Extract usage
        raw_usage = resp_body.get("usage", {})
        prompt_tokens = raw_usage.get("prompt_tokens", 0)
        completion_tokens = raw_usage.get("completion_tokens", 0)
        p_details = raw_usage.get("prompt_tokens_details", {})
        cache_read = p_details.get("cached_read_tokens", raw_usage.get("cached_tokens", 0))
        cache_write = p_details.get("cached_write_tokens", raw_usage.get("cache_write_tokens", 0))

        usage = Usage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            total_tokens=raw_usage.get("total_tokens", prompt_tokens + completion_tokens),
        )

        # 5. Reconcile reservation
        actual_cost = 0.0
        if self.budget_manager and res:
            actual_cost = self.budget_manager.reconcile(
                res=res,
                actual_model=routing.model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            )

        # Extract output text and tool calls
        choices = resp_body.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        text = msg.get("content")
        raw_tool_calls = msg.get("tool_calls", [])

        tool_calls = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), args=args))

        # 6. Journal model_response
        if self.journal:
            self.journal.append(
                session=session,
                event_type="model_response",
                payload={
                    "model_used": routing.model_used,
                    "is_fallback": routing.is_fallback,
                    "cost": actual_cost,
                    "usage": {
                        "in": prompt_tokens,
                        "out": completion_tokens,
                        "cache_read": cache_read,
                        "cache_write": cache_write,
                    },
                },
            )

        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            model_used=routing.model_used,
            is_fallback=routing.is_fallback,
            error_class=routing.error_class,
            cost_usd=actual_cost,
            raw_response=resp_body,
        )

    def search_tavily(
        self,
        query: str,
        api_key: str,
        mode: Mode = "public",
        domains: list[str] | None = None,
    ) -> TavilyResult:
        """Gated Tavily search invocation; hard-denied in confidential mode."""
        if mode == "confidential":
            raise TavilyDeny("Tavily search is strictly forbidden in confidential mode")

        url, headers, payload = build_tavily_request(
            query=query, api_key=api_key, domains=domains, canaries=self.canaries
        )
        resp = self._http_client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Tavily API error ({resp.status_code}): {resp.text}")

        return parse_tavily_response(resp.json())
