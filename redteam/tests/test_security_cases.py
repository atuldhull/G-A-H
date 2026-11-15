"""Reviewed real owner adapters plus explicitly blocked architecture groups."""

import os
from pathlib import Path
import socket
import subprocess
import tempfile

import pytest

from redteam.inventory import CASES, LIVE_GROUPS
from redteam.tests.live import confidential_case, readme_network_case, renewed_consent, secret_search_case
from redteam.tests.execution import Processes, argv_case, consent_case, git_config_case, git_revision_case, oracle_case
from redteam.tests.path_cases import missing_console_supplement, protected_path_supplement, windows_paths_case


REPOSITORY = Path(__file__).resolve().parents[2]
ADAPTERS = {7: confidential_case, 8: readme_network_case, 13: secret_search_case}


@pytest.fixture
def guards(monkeypatch, tmp_path):
    """Installed before any exercise/session setup; all spawns/transports fail."""
    calls = {"spawn": 0, "network": 0, "shell": 0}
    # Path-policy defaults must never inspect the operator's personal registry.
    # Explicit session detectors still use their real sealed fixture stores.
    from crocodile.security import classification
    monkeypatch.setattr(classification, "default_state_path", lambda: tmp_path / "state.db")

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
    if case.group in {2, 3} and os.name == "nt" and len(str(tmp_path)) > 120:
        # Windows Git's private-shadow paths exceed legacy limits under the
        # desktop sandbox's long TEMP. Use a direct compact TEMP child and the
        # owner's explicit ShadowUndo storage seam; policy/mutation stay real.
        parent = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory(prefix=".rt-", dir=parent) as compact:
            local = Path(compact).resolve()
            assert local.parent == parent and local.name.startswith(".rt-")
            from crocodile.security import undo
            original = undo.ShadowUndo

            def local_storage(root, **kwargs):
                return original(root, storage=local / "undo", **kwargs)

            monkeypatch.setattr(undo, "ShadowUndo", local_storage)
            processes = Processes(local, monkeypatch)
            consent_case(local, monkeypatch, processes, renewed=case.group == 3)
        return
    if case.group in {2, 3, 10, 11, 12, 14}:
        processes = Processes(tmp_path, monkeypatch)
        if case.group in {2, 3}:
            consent_case(tmp_path, monkeypatch, processes, renewed=case.group == 3)
        elif case.group == 10:
            git_config_case(tmp_path, monkeypatch, processes)
        elif case.group == 11:
            git_revision_case(tmp_path, processes)
        elif case.group == 12:
            windows_paths_case(tmp_path, processes)
        else:
            oracle_case(tmp_path, monkeypatch, processes)
    elif case.group == 9:
        argv_case(tmp_path, monkeypatch, guards)
    elif case.group == 7:
        ADAPTERS[7](tmp_path, guards)
    elif case.group == 8:
        ADAPTERS[8](tmp_path, monkeypatch, guards)
    elif case.group == 13:
        ADAPTERS[13](tmp_path, guards, capsys)
    else:
        pytest.fail(f"No reviewed live assertion adapter for {case.pytest_id}")


def test_reviewed_renewed_consent_is_red_approval_layer_only(tmp_path, monkeypatch, guards):
    renewed_consent(tmp_path, monkeypatch, guards)


@pytest.mark.parametrize("raw", [".git./config", "solution.py:stream", "con.txt"])
def test_protected_write_spellings_supplemental_only(tmp_path, raw, guards):
    protected_path_supplement(tmp_path, raw)
    assert guards == {"spawn": 0, "network": 0, "shell": 0}


def test_missing_console_cannot_consume_yes_stdin_supplemental_only(tmp_path, monkeypatch, guards):
    missing_console_supplement(tmp_path, monkeypatch, guards)
