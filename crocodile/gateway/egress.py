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
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import httpx

from crocodile.contracts import ChatResult, Mode, ToolCall, Usage
from crocodile.gateway.budget import BudgetManager
from crocodile.gateway.fallback import parse_routing_info, render_takeover_banner
from crocodile.gateway.journal import EventJournal
from crocodile.gateway.local import ConfidentialDeny, check_local_model, sanitize_local_request_body
from crocodile.gateway.network_policy import DestinationDenied, NetworkPolicy, local_host
from crocodile.gateway.prices import PriceTable
from crocodile.gateway.tavily import (
    TavilyDeny,
    TavilyResult,
    build_tavily_request,
    parse_tavily_response,
)


class SecurityError(PermissionError):
    """Raised when an egress security policy or canary check is violated."""

    pass


DEFAULT_CHAINS: dict[str, list[str]] = {
    "cheap": ["anthropic/claude-haiku-5-5", "openai/gpt-5-mini"],
    "strong": ["anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5"],
    "local": ["ollama/qwen2.5-coder:7b"],
}

# ---------------------------------------------------------------------------
# Socket Guard via sys.addaudithook
# ---------------------------------------------------------------------------

_SOCKET_GUARD_INSTALLED = False
_PUBLIC_SERVICES_ENABLED = True
_SOCKET_PAIRS = ContextVar("crocodile_socket_pairs", default=None)
_ALLOWED_DESTINATIONS = {
    ("127.0.0.1", 8080),  # Bifrost Gateway
    ("127.0.0.1", 11434),  # Ollama Probe
    ("::1", 8080),
    ("::1", 11434),
}


def install_socket_guard(allow_tavily: bool = True) -> None:
    """Install once. Public services require an explicit public request scope.

    Legacy allow_tavily never authorizes arbitrary HTTPS connections.
    """
    global _SOCKET_GUARD_INSTALLED, _PUBLIC_SERVICES_ENABLED
    if not allow_tavily:
        _PUBLIC_SERVICES_ENABLED = False
    if _SOCKET_GUARD_INSTALLED:
        return

    sys.addaudithook(_socket_audit)
    _SOCKET_GUARD_INSTALLED = True


def _socket_audit(event, args):
    if event not in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        return
    address = args[1]
    pairs = _SOCKET_PAIRS.get()
    pairs = _ALLOWED_DESTINATIONS if pairs is None else pairs
    if not isinstance(address, tuple) or len(address) < 2 or (address[0], address[1]) not in pairs:
        raise DestinationDenied("socket guard refused an unapproved host-and-port pair")


@contextmanager
def network_scope(policy, origin, *, mode, service):
    # Validation precedes DNS and every transport attempt, including retries.
    scheme, host, port = policy.validate(origin, mode=mode, service=service)
    if service == "public" and not _PUBLIC_SERVICES_ENABLED:
        raise DestinationDenied("public services disabled by socket guard")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    pairs = {(item[4][0], item[4][1]) for item in addresses}
    if not pairs or (mode == "confidential" and any(not local_host(h) for h, _ in pairs)):
        raise DestinationDenied("destination did not resolve to approved local addresses")
    token = _SOCKET_PAIRS.set(frozenset(pairs))
    try:
        yield
    finally:
        _SOCKET_PAIRS.reset(token)


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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(egress)")}
        for name, declaration in (("evidence_version", "INT DEFAULT 1"), ("gateway_request_id", "TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE egress ADD COLUMN {name} {declaration}")


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
    gateway_request_id: str | None = None,
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
                    payload_sha256, payload_bytes, canary_hits, verdict, block_reason,
                    evidence_version, gateway_request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2, ?)
                """,
                (
                    time.time(),
                    session,
                    request_id,
                    dest,
                    vk_alias,
                    mode,
                    model_requested,
                    json.dumps(fallbacks),
                    model_actual,
                    provider_actual,
                    payload_sha256,
                    payload_bytes,
                    canary_hits,
                    verdict,
                    block_reason,
                    gateway_request_id,
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
        network_policy: NetworkPolicy | None = None,
    ) -> None:
        self.bifrost_base_url = bifrost_base_url.rstrip("/")
        self.budget_manager = budget_manager
        self.journal = journal
        self.price_table = price_table or (budget_manager.price_table if budget_manager else None)
        self.canaries: list[str] = canaries or []
        self.network_policy = network_policy or NetworkPolicy()
        install_socket_guard()
        # No proxy environment, redirects or hidden retries may change the peer.
        self._http_client = httpx.Client(timeout=120.0, trust_env=False, follow_redirects=False)

    def scan_for_canaries(self, text: str) -> int:
        """Count canary tokens in payload to prevent confidential exfiltration."""
        hits = 0
        for c in self.canaries:
            if c in text:
                hits += 1
        return hits

    def probe(self, origin, path, *, method="GET", body=None, headers=None, service="gateway"):
        """Fixed local diagnostic adapter; no task text or credential output."""
        with network_scope(self.network_policy, origin, mode="confidential", service=service):
            response = self._http_client.request(
                method, origin.rstrip("/") + path, json=body, headers=headers or {}, timeout=3.0
            )
        if len(response.content) > 4 * 1024 * 1024:
            raise ValueError("diagnostic response too large")
        try:
            data = response.json()
        except ValueError:
            data = {}
        return response.status_code, data

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
        req_id = "req_" + uuid.uuid4().hex

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
            self.network_policy.validate(self.bifrost_base_url, mode=mode, service="gateway")
            if vk_alias != "local":
                raise ConfidentialDeny(
                    f"Confidential egress violation: vk_alias is '{vk_alias}', must be 'local'"
                )
            check_local_model(model_requested)
            body = sanitize_local_request_body(body)
            fallbacks = []

        payload_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
        payload_sha = hashlib.sha256(payload_bytes).hexdigest()

        # 4. Canary check for public mode
        canary_hits = self.scan_for_canaries(payload_bytes.decode("utf-8", errors="ignore"))
        if mode == "public" and canary_hits > 0:
            log_egress(
                db_path=db_path,
                session=session,
                request_id=req_id,
                dest=self.bifrost_base_url,
                vk_alias=vk_alias,
                mode=mode,
                model_requested=model_requested,
                fallbacks=fallbacks,
                model_actual="",
                provider_actual="",
                payload_sha256=payload_sha,
                payload_bytes=len(payload_bytes),
                canary_hits=canary_hits,
                verdict="blocked",
                block_reason="canary_token_detected_in_public_payload",
            )
            raise SecurityError(f"Egress blocked: {canary_hits} canary token(s) detected in outbound payload")

        headers = {
            "Content-Type": "application/json",
            "x-bf-vk": vk,
            "x-bf-session-id": session,
            "x-bf-request-id": req_id,
            "x-crocodile-request-id": req_id,
            "x-crocodile-payload-sha256": payload_sha,
            "x-request-id": req_id,
            "x-bf-lh-crocodile-request-id": req_id,
            "x-bf-lh-crocodile-session": session,
            "x-bf-lh-crocodile-payload-sha256": payload_sha,
            "x-bf-lh-crocodile-payload-bytes": str(len(payload_bytes)),
            "x-bf-lh-crocodile-vk-alias": vk_alias,
            "x-bf-lh-crocodile-model-requested": model_requested,
            "x-bf-lh-crocodile-fallbacks": json.dumps(fallbacks, separators=(",", ":")),
        }

        endpoint = f"{self.bifrost_base_url}/v1/chat/completions"
        if self.budget_manager is None:
            raise PermissionError("inference requires the protected budget manager")
        self.budget_manager.verify_hold(reservation_id)
        logged = False
        try:
            with network_scope(self.network_policy, self.bifrost_base_url, mode=mode, service="gateway"):
                resp = self._http_client.post(endpoint, content=payload_bytes, headers=headers)
            status_code = resp.status_code
            resp_headers = resp.headers
            resp_body = resp.json() if resp.status_code < 500 else {"error": resp.text}

            # In confidential mode, verify answered provider is ollama
            # Routing parsers may infer a provider from the requested model for
            # UI compatibility. That inference is never actual-provider evidence.
            metadata = {k.lower(): v for k, v in resp_headers.items()}
            route = resp_body.get("extra_fields", {}).get("routing_info", {})
            provider = (
                metadata.get("x-bifrost-provider")
                or metadata.get("x-bifrost-routing-info-provider")
                or route.get("provider", "")
            )
            actual_model = (
                metadata.get("x-bifrost-resolved-model")
                or metadata.get("x-bifrost-routing-info-model")
                or route.get("model")
                or resp_body.get("model", "")
            )
            if actual_model and "/" not in actual_model and provider:
                actual_model = provider + "/" + actual_model

            log_egress(
                db_path=db_path,
                session=session,
                request_id=req_id,
                dest=self.bifrost_base_url,
                vk_alias=vk_alias,
                mode=mode,
                model_requested=model_requested,
                fallbacks=fallbacks,
                model_actual=actual_model,
                provider_actual=provider,
                payload_sha256=payload_sha,
                payload_bytes=len(payload_bytes),
                canary_hits=canary_hits,
                verdict="sent",
                gateway_request_id=metadata.get("x-bifrost-request-id") or metadata.get("x-request-id"),
            )
            logged = True
            if mode == "confidential" and status_code < 400 and provider != "ollama":
                raise ConfidentialDeny("confidential response has missing or non-Ollama provider evidence")
            return status_code, resp_body, {**resp_headers, "x-crocodile-request-id": req_id}

        except Exception as e:
            if logged:
                raise
            log_egress(
                db_path=db_path,
                session=session,
                request_id=req_id,
                dest=self.bifrost_base_url,
                vk_alias=vk_alias,
                mode=mode,
                model_requested=model_requested,
                fallbacks=fallbacks,
                model_actual="",
                provider_actual="",
                payload_sha256=payload_sha,
                payload_bytes=len(payload_bytes),
                canary_hits=canary_hits,
                verdict="blocked" if isinstance(e, DestinationDenied) else "sent",
                block_reason=type(e).__name__,
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
        temperature: float | None = None,
        mock_response: dict[str, Any] | None = None,
    ) -> ChatResult:
        """High-level chat invocation with reservation, failover, banner, and reconciliation."""
        if self.budget_manager is None:
            raise PermissionError("inference requires the protected budget manager")
        if chain is None:
            if mode == "confidential":
                chain = list(DEFAULT_CHAINS.get("local", ["ollama/qwen2.5-coder:7b"]))
            elif tier in DEFAULT_CHAINS:
                chain = list(DEFAULT_CHAINS[tier])
            else:
                chain = ["anthropic/claude-haiku-5-5"]
        primary_model = chain[0]
        fb_list = fallbacks if fallbacks is not None else chain[1:]
        if mode == "confidential":
            self.network_policy.validate(self.bifrost_base_url, mode=mode, service="gateway")
            for model in chain:
                check_local_model(model)
            if any(not model.startswith("ollama/") for model in fb_list):
                raise ConfidentialDeny("confidential fallback chain must be local")
            fb_list = []

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
        if temperature is not None:
            req_body["temperature"] = temperature
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
                    "temperature": temperature,
                },
            )

        # 3. Post to Bifrost or Mock
        if mock_response:
            status_code = 200
            resp_body = mock_response
            resp_headers = {}
        else:
            try:
                status_code, resp_body, resp_headers = self.post_bifrost(
                    body=req_body,
                    reservation_id=res_id,
                    session=session,
                    vk=vk,
                    vk_alias=vk_alias,
                    mode=mode,
                )
            except (ConfidentialDeny, SecurityError, PermissionError):
                raise
            except httpx.RequestError as exc:
                # Upstream transport error: synthesize failure response
                status_code = 504 if isinstance(exc, httpx.TimeoutException) else 502
                resp_body = {"error": str(exc)}
                resp_headers = {}

        # 4. Parse Routing & Failover
        routing = parse_routing_info(
            resp_headers, resp_body, requested_model=primary_model, status_code=status_code
        )

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
        p_details = raw_usage.get("prompt_tokens_details") or {}
        cache_read = (
            p_details.get("cached_read_tokens")
            or p_details.get("cached_tokens")
            or raw_usage.get("cached_read_tokens")
            or raw_usage.get("cached_tokens")
            or 0
        )
        cache_write = (
            p_details.get("cached_write_tokens")
            or raw_usage.get("cache_write_tokens")
            or raw_usage.get("cached_write_tokens")
            or 0
        )

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
                request_id=resp_headers.get("x-crocodile-request-id"),
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
        with network_scope(self.network_policy, "https://api.tavily.com:443", mode=mode, service="public"):
            resp = self._http_client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Tavily API error ({resp.status_code}): {resp.text}")

        return parse_tavily_response(resp.json())
