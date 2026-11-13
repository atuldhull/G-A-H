"""Resolves each shared interface to the real module if its owner has shipped it, else to a stub.

Tests and the bench can override any service with `services.override(name, impl)`.
"""

from __future__ import annotations

import importlib
from typing import Any

from . import _stubs

_REAL = {
    "egress": ("crocodile.gateway.egress", _stubs.StubEgress),
    "journal": ("crocodile.gateway.journal", _stubs.StubJournal),
    "approvals": ("crocodile.security.approvals", _stubs.StubApprovals),
    "cmd": ("crocodile.security.cmd", _stubs.StubCmd),
    "confidential": ("crocodile.security.confidential", _stubs.StubConfidential),
}
_cache: dict[str, Any] = {}


def get(name: str) -> Any:
    if name in _cache:
        return _cache[name]
    modname, stub = _REAL[name]
    try:
        impl: Any = importlib.import_module(modname)   # module exposing the contract functions
    except ModuleNotFoundError as e:
        if e.name and modname.startswith(e.name):
            impl = stub()
        else:
            raise
    _cache[name] = impl
    return impl


def is_stub(name: str) -> bool:
    return type(get(name)).__module__ == _stubs.__name__


def override(name: str, impl: Any) -> None:
    _cache[name] = impl


def reset() -> None:
    _cache.clear()
