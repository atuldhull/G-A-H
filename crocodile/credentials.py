"""Canonical Credential Manager identifiers; no on-read legacy or env fallbacks."""

SERVICE = "crocodile"
VK_LOCAL = "vk_local"
VK_PUBLIC = "vk_public"
VK_BENCH = "vk_bench"
TAVILY = "tavily_key"
HMAC_KEY = "hmac_key"
GATEWAY_KEYS = {"local": VK_LOCAL, "public": VK_PUBLIC, "bench": VK_BENCH}


class CredentialUnavailable(RuntimeError):
    pass


def windows_backend():
    import os

    if os.name != "nt":
        raise CredentialUnavailable("Windows Credential Manager is unavailable")
    try:
        from keyring.backends.Windows import WinVaultKeyring

        backend = WinVaultKeyring()
        if backend.priority <= 0:
            raise RuntimeError()
        return backend
    except Exception as error:
        raise CredentialUnavailable("Windows Credential Manager backend unavailable") from error


class CredentialStore:
    def __init__(self, *, backend=None):
        self._backend = backend

    def get(self, name, *, required=True):
        if name not in (*GATEWAY_KEYS.values(), TAVILY, HMAC_KEY):
            raise ValueError("unknown canonical credential identifier")
        try:
            backend = self._backend if self._backend is not None else windows_backend()
            value = backend.get_password(SERVICE, name)
        except Exception as error:
            if required:
                raise CredentialUnavailable("canonical Credential Manager credential unavailable") from error
            return None
        if not isinstance(value, str) or not value:
            if required:
                raise CredentialUnavailable("missing canonical credential: " + name)
            return None
        return value

    def gateway(self, alias):
        if alias not in GATEWAY_KEYS:
            raise ValueError("unknown gateway credential alias")
        return self.get(GATEWAY_KEYS[alias])


def copy_legacy_credential(alias, *, backend):
    """Explicit trusted provisioning helper; never called by startup/execution.

    Preserve old entries, refuse conflicts, verify readback. No secret is returned.
    """
    names = {
        "local": (VK_LOCAL, "vk-local"),
        "public": (VK_PUBLIC, "vk-public"),
        "bench": (VK_BENCH, "vk-bench"),
        "tavily": (TAVILY, "tavily"),
    }
    canonical, legacy = names[alias]
    current = backend.get_password(SERVICE, canonical)
    previous = backend.get_password(SERVICE, legacy)
    if not previous:
        raise CredentialUnavailable("legacy credential missing; provision the canonical name explicitly")
    if current and current != previous:
        raise CredentialUnavailable(
            "canonical and legacy credentials conflict; explicit owner review required"
        )
    if not current:
        backend.set_password(SERVICE, canonical, previous)
    if backend.get_password(SERVICE, canonical) != previous:
        raise CredentialUnavailable("credential copy verification failed")
