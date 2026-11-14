"""Bind the agent to the budgeted gateway and initialized Part 3 security bridge.

Missing execution/egress implementations fail closed. Trusted fixture and harness
code can inject services; repository text and model arguments cannot choose them.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

from . import _stubs

_cache: dict[str, Any] = {}


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def _build(name: str) -> Any:
    from . import adapters

    if name == "egress":
        if os.environ.get("CROCODILE_API_KEY_ENV"):
            raise RuntimeError("direct-provider fallback is disabled; use the budgeted gateway")
        if not _has("crocodile.gateway.egress"):
            raise RuntimeError("gateway implementation is required")
        return adapters.GatewayEgress()
    if name == "journal":
        return adapters.GatewayJournal() if _has("crocodile.gateway.journal") else _stubs.StubJournal()
    if name in ("approvals", "cmd"):
        if _has("crocodile.security.approvals") and _has("crocodile.security.cmd"):
            bridge = _cache.get("_security") or adapters.SecurityBridge()
            _cache["_security"] = bridge
            return bridge
        raise RuntimeError("Part 3 security implementation is required")
    if name == "confidential":
        return (
            adapters.SecurityConfidential()
            if _has("crocodile.security.confidential")
            else _stubs.StubConfidential()
        )
    raise KeyError(name)


def get(name: str) -> Any:
    if name not in _cache:
        _cache[name] = _build(name)
    return _cache[name]


def is_stub(name: str) -> bool:
    return type(get(name)).__module__ == _stubs.__name__


def git_read(op: str, session) -> Any:
    """Read-only Git must use Part 3's audited fixed templates."""
    impl = get("cmd")
    if hasattr(impl, "git_read"):
        return impl.git_read(op, session)
    raise RuntimeError("the audited Git implementation is required")


def override(name: str, impl: Any) -> None:
    _cache[name] = impl


def reset() -> None:
    _cache.clear()


def security(session):
    if session.security is None:
        raise RuntimeError("security context was not initialized")
    session.security.check(session)
    return session.security
