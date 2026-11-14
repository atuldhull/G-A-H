"""Trusted destination configuration and per-request, mode-specific socket pairs."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit


class DestinationDenied(PermissionError):
    pass


def endpoint(raw):
    try:
        value = urlsplit(raw)
        if (
            value.scheme not in ("http", "https")
            or not value.hostname
            or value.username is not None
            or value.password is not None
            or value.query
            or value.fragment
            or value.path not in ("", "/")
        ):
            raise ValueError()
        port = value.port or (443 if value.scheme == "https" else 80)
        host = value.hostname.lower()
        if "%" in host:
            raise ValueError()
        return value.scheme, host, port
    except (ValueError, TypeError, AttributeError) as error:
        raise DestinationDenied("invalid gateway endpoint") from error


def local_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class NetworkPolicy:
    """Caller-owned settings; no repo/model fields extend the allowlist."""

    gateways: tuple[str, ...] = ("http://127.0.0.1:8080", "http://[::1]:8080", "http://localhost:8080")
    ollama: tuple[str, ...] = ("http://127.0.0.1:11434", "http://[::1]:11434", "http://localhost:11434")
    public_services: tuple[str, ...] = ("https://api.tavily.com:443",)

    def validate(self, raw, *, mode, service):
        if mode not in ("public", "confidential"):
            raise DestinationDenied("unknown egress mode")
        target = endpoint(raw)
        configured = (
            self.gateways
            if service == "gateway"
            else self.ollama
            if service == "ollama"
            else self.public_services
            if service == "public"
            else ()
        )
        if target not in {endpoint(item) for item in configured}:
            raise DestinationDenied("destination is outside the configured host-and-port allowlist")
        if mode == "confidential" and (service == "public" or not local_host(target[1])):
            raise DestinationDenied("confidential destination must be an approved local endpoint")
        return target
