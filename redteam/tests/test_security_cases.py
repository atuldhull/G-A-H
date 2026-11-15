"""Reviewed real owner adapters plus explicitly blocked architecture groups."""

import os
from pathlib import Path
import socket
import subprocess

import pytest

from redteam.inventory import CASES, LIVE_GROUPS
from redteam.tests.live import confidential_case, readme_network_case, renewed_consent, secret_search_case


REPOSITORY = Path(__file__).resolve().parents[2]
ADAPTERS = {7: confidential_case, 8: readme_network_case, 13: secret_search_case}


@pytest.fixture
def guards(monkeypatch):
    """Installed before any exercise/session setup; all spawns/transports fail."""
    calls = {"spawn": 0, "network": 0, "shell": 0}

    def forbid(kind):
        def rejected(*args, **kwargs):
            calls[kind] += 1
            pytest.fail(f"Unexpected {kind} attempt at the actual process/socket boundary")
        return rejected

    monkeypatch.setattr(subprocess, "Popen", forbid("spawn"))
    monkeypatch.setattr(subprocess, "run", forbid("spawn"))
    monkeypatch.setattr(os, "system", forbid("shell"))
    monkeypatch.setattr(os, "popen", forbid("shell"))
    monkeypatch.setattr(socket, "socket", forbid("network"))
    monkeypatch.setattr(socket, "create_connection", forbid("network"))
    return calls


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case.pytest_id,
                  marks=[] if case.group in LIVE_GROUPS else
                  pytest.mark.skip(reason=case.blocked_reason(REPOSITORY)))
     for case in CASES],
)
def test_security_case(case, tmp_path, monkeypatch, guards, capsys):
    if case.group == 7:
        ADAPTERS[7](tmp_path, guards)
    elif case.group == 8:
        ADAPTERS[8](tmp_path, monkeypatch, guards)
    elif case.group == 13:
        ADAPTERS[13](tmp_path, guards, capsys)
    else:
        pytest.fail(f"No reviewed live assertion adapter for {case.pytest_id}")


def test_reviewed_renewed_consent_is_red_approval_layer_only(tmp_path, monkeypatch, guards):
    renewed_consent(tmp_path, monkeypatch, guards)
