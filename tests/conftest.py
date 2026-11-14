"""The app fixtures use explicitly enrolled, isolated state and a synthetic console."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def app_security(request, tmp_path, monkeypatch):
    if Path(str(request.fspath)).parent != Path(__file__).parent:
        yield None
        return
    # Unit fixtures never enumerate real credential backends or query Windows WMI.
    import keyring
    from security_support import confirm, enroll, install

    from crocodile import services
    from crocodile.security import approvals

    monkeypatch.setattr(keyring, "get_password", lambda *_: None)

    path = tmp_path / "security-state" / "state.db"
    monkeypatch.setenv("CROCODILE_STATE_DB", str(path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "settings"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(approvals, "_console_answer", confirm)
    state = enroll(path)
    # Reuse a fixture connection, never a verification result. Each check opens
    # a fresh read transaction and hashes the real rows, including tampered rows.
    reader = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    verify = state.verify_state

    def verify_fresh(connection=None):
        if connection is not None:
            return verify(connection)
        reader.execute("BEGIN")
        try:
            return verify(reader)
        finally:
            reader.rollback()

    monkeypatch.setattr(state, "verify_state", verify_fresh)
    reset = services.reset

    def reset_with_state():
        reset()
        install(state)

    monkeypatch.setattr(services, "reset", reset_with_state)
    reset_with_state()
    yield state
    reset()
    reader.close()
