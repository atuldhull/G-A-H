"""Resolves each service the loop uses to the real part (via crocodile.adapters) or a stub.

- egress:       Part 2 gateway (Bifrost) when installed; the direct-provider stub when
                CROCODILE_API_KEY_ENV is set (dev testing) or the gateway is absent.
- journal:      Part 2 EventJournal (+ JSONL), else JSONL only.
- approvals/cmd: Part 3 security bridge (one shared object), else console/subprocess stubs.
- confidential: Part 3 mode_for, else always "public".

Tests and the bench can override any service with `services.override(name, impl)`.
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
        if os.environ.get("CROCODILE_API_KEY_ENV") or not _has("crocodile.gateway.egress"):
            return _stubs.StubEgress()
        return adapters.GatewayEgress()
    if name == "journal":
        return adapters.GatewayJournal() if _has("crocodile.gateway.journal") else _stubs.StubJournal()
    if name in ("approvals", "cmd"):
        if _has("crocodile.security.approvals") and _has("crocodile.security.cmd"):
            bridge = _cache.get("_security") or adapters.SecurityBridge()
            _cache["_security"] = bridge
            return bridge
        return _stubs.StubApprovals() if name == "approvals" else _stubs.StubCmd()
    if name == "confidential":
        return adapters.SecurityConfidential() if _has("crocodile.security.confidential") \
            else _stubs.StubConfidential()
    raise KeyError(name)


def get(name: str) -> Any:
    if name not in _cache:
        _cache[name] = _build(name)
    return _cache[name]


def is_stub(name: str) -> bool:
    return type(get(name)).__module__ == _stubs.__name__


def git_read(op: str, session) -> Any:
    """Read-only git (status/diff/log): Part 3 fixed templates when present, else a hardened argv."""
    impl = get("cmd")
    if hasattr(impl, "git_read"):
        return impl.git_read(op, session)
    from .tools.cmd import _GIT_READ
    argv = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=", "--no-pager", *_GIT_READ[op]]
    return impl.run(argv, session.repo, timeout=30)


def override(name: str, impl: Any) -> None:
    _cache[name] = impl


def reset() -> None:
    _cache.clear()
