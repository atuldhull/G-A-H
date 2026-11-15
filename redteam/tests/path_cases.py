"""Real path/console backends; conditional Windows aliases are never fabricated."""

import builtins
import ctypes
import io
import os
from pathlib import Path
import sys

import pytest

from crocodile.security import procs
from crocodile.security.executables import resolve_exe
from crocodile.security.paths import resolve_in_repo
from crocodile.tools import dispatch
from redteam.fixtures import build_fixture
from redteam.tests.execution import agent_services
from redteam.tests.live import context


def windows_paths_case(tmp_path, processes):
    if os.name != "nt":
        pytest.skip("BLOCKED: Windows filesystem required for real junction, trailing-dot, ADS/device and 8.3 alias group")
    fixture = build_fixture("rt_paths_windows", tmp_path / "exercise")
    root = fixture.root
    target = root / ".git"
    before = (target / "config").read_bytes()
    junction = root / "Protected metadata junction long name"
    assert target.resolve().parent == root and junction.resolve().parent == root
    exe = resolve_exe("cmd", root, root)
    argv = [str(exe), "/d", "/c", "mklink", "/J", str(junction), str(target)]
    processes.setup_commands.add(tuple(argv))
    result = procs.run(argv, root, root=root, timeout=10)
    if result.returncode:
        pytest.skip(f"BLOCKED: real Windows junction creation unavailable (mklink return code {result.returncode}); no junction safety pass")
    assert junction.is_junction() and junction.resolve() == target
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel.GetShortPathNameW.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetShortPathNameW(str(junction), buffer, len(buffer))
    if not length or Path(buffer.value).name.casefold() == junction.name.casefold():
        pytest.skip("BLOCKED: filesystem provides no actual 8.3 alias for the protected-metadata junction; literal GIT~1 is insufficient")
    alias = Path(buffer.value)
    assert alias.resolve() == target and alias.name != junction.name
    for raw in (str(junction / "config"), ".git./config", "solution.py:stream",
                str(alias / "config"), "con.txt"):
        with pytest.raises(ValueError):
            resolve_in_repo(raw, root, for_write=True, mode="confidential")
    assert (target / "config").read_bytes() == before
    assert not fixture.canary.exists()


def protected_path_supplement(tmp_path, raw):
    fixture = build_fixture("rt_paths_windows", tmp_path / "exercise")
    before = (fixture.root / ".git/config").read_bytes()
    with pytest.raises(ValueError):
        resolve_in_repo(raw, fixture.root, for_write=True, mode="confidential")
    assert (fixture.root / ".git/config").read_bytes() == before
    assert not fixture.canary.exists()


def missing_console_supplement(tmp_path, monkeypatch, guards):
    """Actual approval/backend/tool refusal; root CLI group 15 stays blocked."""
    fixture = build_fixture("pipe_yes", tmp_path / "exercise")
    sec, ctx = context(tmp_path, fixture.root)
    before = (fixture.root / "target.txt").read_bytes()
    stdin = io.StringIO("yes\nyes\nyes\n")
    attempted = []
    original = builtins.open

    def unavailable(file, *args, **kwargs):
        if str(file) in {"CONIN$", "CONOUT$", "/dev/tty"}:
            attempted.append(str(file))
            raise OSError("Synthetic console backend unavailable")
        return original(file, *args, **kwargs)

    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(builtins, "open", unavailable)
    with agent_services(monkeypatch, []):
        from crocodile import services
        services.get("approvals").bind_session(ctx.session, sec)
        result = dispatch("write", {"path": "target.txt", "content": "attacker changed\n"}, ctx)
    assert attempted and stdin.tell() == 0
    assert not result.ok and (fixture.root / "target.txt").read_bytes() == before
    assert not sec._permits and any(e["event"] == "approval" and not e["approved"] for e in sec.events)
    assert guards == {"spawn": 0, "network": 0, "shell": 0}
