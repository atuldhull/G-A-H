"""Failover detection, routing header parsing, and MODEL TAKEOVER banner.

Implements R1 Reliability requirement:
- Detects failovers via Bifrost response headers (x-bifrost-routing-info-*) or body.
- Classifies primary failure into error classes: auth, rate-limit, quota, transient, timeout, caller-fault.
- Renders the yellow MODEL TAKEOVER banner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crocodile.contracts import ErrorClass


@dataclass
class RoutingInfo:
    """Information about which model answered and whether a fallback was triggered."""

    model_used: str
    provider_used: str
    is_fallback: bool
    primary_model: str | None = None
    primary_provider: str | None = None
    fallback_index: int | None = None
    error_class: ErrorClass | None = None
    error_message: str | None = None
    cost_delta: float = 0.0


def classify_error(status_code: int | None, error_body_or_msg: str | None) -> ErrorClass:
    """Classifies an upstream failure into Bifrost's error classes."""
    msg = (error_body_or_msg or "").lower()

    if status_code == 401 or "auth" in msg or "key" in msg or "unauthorized" in msg:
        return "auth"
    if status_code == 429 or "rate" in msg or "too many requests" in msg:
        return "rate-limit"
    if status_code == 402 or "quota" in msg or "budget" in msg or "balance" in msg or "insufficient" in msg:
        return "quota"
    if status_code == 504 or "timeout" in msg or "timed out" in msg:
        return "timeout"
    if status_code in (500, 502, 503) or "transient" in msg or "overloaded" in msg:
        return "transient"
    if status_code == 400 or "bad request" in msg or "caller" in msg:
        return "caller-fault"

    return "unknown"


def parse_routing_info(
    headers: Mapping[str, str],
    body: dict[str, Any] | None = None,
    requested_model: str = "",
    status_code: int = 200,
) -> RoutingInfo:
    """Parses Bifrost response headers and payload to determine routing and failovers."""
    headers_lower = {k.lower(): v for k, v in headers.items()}
    body = body or {}
    extra_fields = body.get("extra_fields", {})
    body_routing = extra_fields.get("routing_info", {})

    # Extract is_fallback flag
    header_is_fallback = headers_lower.get("x-bifrost-routing-info-is-fallback")
    is_fallback = False
    if header_is_fallback is not None:
        is_fallback = header_is_fallback.lower() in ("true", "1")
    elif "is_fallback" in body_routing:
        is_fallback = bool(body_routing.get("is_fallback"))

    # Extract answered model
    model_used = (
        headers_lower.get("x-bifrost-resolved-model")
        or headers_lower.get("x-bifrost-routing-info-model")
        or body_routing.get("model")
        or body.get("model")
        or requested_model
    )

    provider_used = (
        headers_lower.get("x-bifrost-provider")
        or headers_lower.get("x-bifrost-routing-info-provider")
        or body_routing.get("provider")
        or ""
    )

    primary_model = (
        headers_lower.get("x-bifrost-routing-info-primary-model")
        or body_routing.get("primary_model")
        or requested_model
    )

    primary_provider = (
        headers_lower.get("x-bifrost-routing-info-primary-provider")
        or body_routing.get("primary_provider")
        or ""
    )

    # Extract fallback index
    fb_index_hdr = headers_lower.get("x-bifrost-fallback-index")
    fallback_index = int(fb_index_hdr) if fb_index_hdr and fb_index_hdr.isdigit() else None

    # Error classification if request failed OR if fallback occurred
    error_class: ErrorClass | None = None
    if status_code >= 400 or ("error" in body and not body.get("choices")):
        raw_reason = ""
        if isinstance(body.get("error"), dict):
            raw_reason = body["error"].get("message", "")
        elif isinstance(body.get("error"), str):
            raw_reason = body["error"]
        error_class = classify_error(status_code if status_code >= 400 else 500, raw_reason)
        model_used = ""
        provider_used = ""
    elif is_fallback:
        raw_reason = headers_lower.get("x-bifrost-fallback-reason") or body_routing.get("fallback_reason")
        error_class = classify_error(status_code if status_code >= 400 else 401, raw_reason)

    # Ensure model_used and primary_model are provider-prefixed (e.g. 'gemini/gemini-3.5-flash-lite')
    # Bifrost routing headers return bare model name without provider prefix
    if not provider_used and "/" in requested_model:
        provider_used = requested_model.split("/", 1)[0]
    if not primary_provider and "/" in requested_model:
        primary_provider = requested_model.split("/", 1)[0]

    if model_used and "/" not in model_used:
        prefix = provider_used or (requested_model.split("/", 1)[0] if "/" in requested_model else "")
        if prefix:
            model_used = f"{prefix}/{model_used}"

    if primary_model and "/" not in primary_model:
        prefix = primary_provider or (requested_model.split("/", 1)[0] if "/" in requested_model else "")
        if prefix:
            primary_model = f"{prefix}/{primary_model}"

    return RoutingInfo(
        model_used=model_used,
        provider_used=provider_used,
        is_fallback=is_fallback,
        primary_model=primary_model,
        primary_provider=primary_provider,
        fallback_index=fallback_index,
        error_class=error_class,
    )


def render_takeover_banner(
    routing: RoutingInfo,
    journal_seq: int = 1,
    cost_delta: float = 0.0,
) -> str:
    """Renders the required MODEL TAKEOVER ASCII banner (architecture/11 §5)."""
    err_cls = routing.error_class or "transient"
    primary = routing.primary_model or "primary model"
    answered = routing.model_used
    delta_str = f"-${abs(cost_delta):.4f}/turn" if cost_delta <= 0 else f"+${cost_delta:.4f}/turn"

    banner = (
        "+- MODEL TAKEOVER ---------------------------------------------------+\n"
        f"| {primary} failed: {err_cls} (primary unavailable)       |\n"
        f"| -> {answered} answered. Session intact (journal seq {journal_seq}). |\n"
        f"| Cost delta about {delta_str}. Reservation covered the most expensive model. |\n"
        "+---------------------------------------------------------------------+"
    )
    return banner
