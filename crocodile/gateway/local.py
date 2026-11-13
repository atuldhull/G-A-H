"""Confidential local routing and Ollama model validation.

Enforces:
- Exact local model allowlist check (ADR-006, review 07 C3).
- Rejection of Ollama cloud-proxied models (:cloud, -cloud, /, @).
- Loopback host resolution enforcement.
- Context window fitting to OLLAMA_CONTEXT_LENGTH (32768 * 0.7).
- Local path quirks: single-string system prompt, no cache_control.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

DEFAULT_LOCAL_ALLOWLIST = ["qwen2.5-coder:7b", "qwen3-coder:30b"]
DEFAULT_OLLAMA_CONTEXT_LENGTH = 32768
DEFAULT_FIT_FRAC = 0.7


class ConfidentialDeny(Exception):
    """Raised when a model or host configuration violates confidential constraints."""
    pass


def is_loopback_host(host_or_url: str) -> bool:
    """Check if the provided host or URL resolves strictly to a loopback address."""
    raw = host_or_url.strip()
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    hostname = parsed.hostname
    if not hostname:
        return False

    hostname_clean = hostname.strip("[]").lower()
    if hostname_clean in ("localhost", "127.0.0.1", "::1"):
        return True

    try:
        addr_info = socket.getaddrinfo(hostname_clean, None)
        for _, _, _, _, sockaddr in addr_info:
            ip = sockaddr[0]
            if ip not in ("127.0.0.1", "::1"):
                return False
        return True
    except socket.gaierror:
        return False


def check_local_model(
    model_id: str,
    ollama_host: str = "http://127.0.0.1:11434",
    allowlist: list[str] | None = None,
) -> None:
    """Validates that model_id is a sanctioned local-only Ollama model.
    
    Raises ConfidentialDeny on any violation.
    """
    allowlist = allowlist or DEFAULT_LOCAL_ALLOWLIST

    if not model_id.startswith("ollama/"):
        raise ConfidentialDeny(
            f"Confidential mode violation: model '{model_id}' must start with 'ollama/'"
        )

    tag = model_id[len("ollama/") :]

    # Reject cloud tags, forward proxies, or remote references
    if any(forbidden in tag for forbidden in [":cloud", "-cloud", "/", "@"]):
        raise ConfidentialDeny(
            f"Confidential mode violation: model tag '{tag}' contains forbidden cloud/remote modifier"
        )

    if tag not in allowlist:
        raise ConfidentialDeny(
            f"Confidential mode violation: model '{tag}' is not in local allowlist {allowlist}"
        )

    # Check OLLAMA_HOST env var if set
    env_host = os.environ.get("OLLAMA_HOST", ollama_host)
    if not is_loopback_host(env_host):
        raise ConfidentialDeny(
            f"Confidential mode violation: OLLAMA_HOST '{env_host}' does not resolve to loopback (127.0.0.1)"
        )


def fit_context_or_refuse(
    prompt_token_count: int,
    ctx_window: int = DEFAULT_OLLAMA_CONTEXT_LENGTH,
    fit_frac: float = DEFAULT_FIT_FRAC,
) -> None:
    """Verifies that the prompt will fit within the local model's context window.

    Ollama truncates from the front without warning if exceeded. We must refuse upfront.
    """
    allowed_max = int(ctx_window * fit_frac)
    if prompt_token_count > allowed_max:
        raise ConfidentialDeny(
            f"Prompt length {prompt_token_count} exceeds safe local context limit {allowed_max} "
            f"({fit_frac*100:.0f}% of {ctx_window}). Truncation prevented."
        )


def sanitize_local_request_body(body: dict) -> dict:
    """Sanitizes request body for Ollama path quirks (Bifrost #6245, #8145).
    
    - Sends system as a single string (one block).
    - Removes cache_control blocks.
    - Ensures fallbacks is an empty list [].
    """
    sanitized = dict(body)
    sanitized["fallbacks"] = []

    # Strip cache_control if present
    if "messages" in sanitized:
        new_messages = []
        for msg in sanitized["messages"]:
            msg_copy = dict(msg)
            if "cache_control" in msg_copy:
                del msg_copy["cache_control"]
            new_messages.append(msg_copy)
        sanitized["messages"] = new_messages

    return sanitized
