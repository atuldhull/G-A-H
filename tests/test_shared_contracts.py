"""Upgrade/replay fixtures for the shared state, credential and journal contracts."""

import json
import sqlite3
from pathlib import Path

import pytest
from test_loop import FakeEgress
from typer.testing import CliRunner

from crocodile import services
from crocodile.adapters import GatewayEgress, GatewayJournal, _state_db
from crocodile.cli import app
from crocodile.credentials import VK_LOCAL, CredentialStore, CredentialUnavailable, copy_legacy_credential
from crocodile.gateway.journal import EventJournal
from crocodile.journal_contract import SESSION_STARTED, read_envelope
from crocodile.loop import Agent
from crocodile.runtime_security import SecurityContext, state_path
from crocodile.security.audit import audit_database
from crocodile.security.classification import RepoIdentity, SecurityStore, default_state_path
from crocodile.security.integrity import StateIntegrity
from crocodile.shared_state import StateLocationError, resolve_state_path


def locations(tmp_path, monkeypatch):
    roaming, local = tmp_path / "roaming", tmp_path / "local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("CROCODILE_STATE_DB", raising=False)
    return roaming / "crocodile/state.db", local / "crocodile/state.db"


def backup(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as original, sqlite3.connect(target) as destination:
        original.backup(destination)


def test_fresh_default_does_not_initialize_empty_state(tmp_path, monkeypatch):
    canonical, _ = locations(tmp_path, monkeypatch)
    assert resolve_state_path() == canonical
    assert state_path() == canonical == _state_db() == default_state_path()
    assert StateIntegrity().path == SecurityStore().path == canonical
    assert not canonical.exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_existing_installation_all_callers_and_resume_share_database(
    tmp_path, monkeypatch, app_security, legacy
):
    canonical, old = locations(tmp_path, monkeypatch)
    selected = old if legacy else canonical
    with sqlite3.connect(app_security.path) as db:
        db.execute("BEGIN IMMEDIATE")
        with app_security.authorized_write(db):
            db.execute("INSERT INTO grants VALUES ('existing-installation','[]')")
        db.commit()
    backup(app_security.path, selected)
    assert state_path() == _state_db() == default_state_path() == selected
    assert EventJournal().db_path == SecurityStore().path == StateIntegrity().path == selected
    gateway = GatewayEgress()
    assert gateway.client.budget_manager.db_path == selected
    gateway.client._http_client.close()
    repo = tmp_path / "repo"
    repo.mkdir()
    services.override("security_factory", SecurityContext)
    services.override("security_resume", SecurityContext.resume)
    services.override("egress", FakeEgress([]))
    agent = Agent(repo, "preserve the original task", flags=set(), step_cap=0)
    assert agent.security.p3.integrity.path == selected
    agent.run()
    resumed = Agent(repo, "", resume=agent.s.id, step_cap=0)
    assert resumed.security.p3.integrity.path == selected
    assert resumed.original_task == "preserve the original task"
    assert GatewayJournal().j.db_path == selected
    with sqlite3.connect(selected) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM grants WHERE session='existing-installation'").fetchone()[0] == 1
        )
    if legacy:
        assert not canonical.exists()


def test_ambiguous_paths_and_missing_override_refuse_new_state(tmp_path, monkeypatch, app_security):
    canonical, legacy = locations(tmp_path, monkeypatch)
    backup(app_security.path, legacy)
    monkeypatch.setenv("CROCODILE_STATE_DB", str(tmp_path / "missing.db"))
    with pytest.raises(StateLocationError, match="historical state exists"):
        resolve_state_path()
    monkeypatch.delenv("CROCODILE_STATE_DB")
    canonical.parent.mkdir(parents=True)
    canonical.touch()  # An empty new file must not hide the old database.
    with pytest.raises(StateLocationError, match="both APPDATA"):
        resolve_state_path()
    monkeypatch.setenv("CROCODILE_STATE_DB", str(legacy))
    assert resolve_state_path() == legacy
    assert canonical.stat().st_size == 0


def test_relative_override_and_orphaned_wal_refused(tmp_path, monkeypatch):
    canonical, legacy = locations(tmp_path, monkeypatch)
    monkeypatch.setenv("CROCODILE_STATE_DB", "state.db")
    with pytest.raises(StateLocationError, match="absolute"):
        resolve_state_path()
    monkeypatch.delenv("CROCODILE_STATE_DB")
    legacy.parent.mkdir(parents=True)
    Path(str(legacy) + "-wal").write_bytes(b"recover me")
    with pytest.raises(StateLocationError, match="orphaned"):
        resolve_state_path()
    assert not canonical.exists()


def test_doctor_state_is_independent_of_config_directory(tmp_path, monkeypatch, app_security):
    import crocodile.security.doctor as doctor

    repo = tmp_path / "repo"
    repo.mkdir()
    settings = tmp_path / "config"
    settings.mkdir()
    for name in ("config.yaml", "policy.yaml", "prices.yaml"):
        (settings / name).write_text("{}\n")
    seen = []
    monkeypatch.setattr("crocodile.gateway.diagnostics.collect_evidence", lambda *_args, **_kw: {})

    class Report:
        passed = True

        def render(self):
            return "OK fixture"

    def inspect(**kwargs):
        seen.append(kwargs["session"].integrity.path)
        kwargs["session"].integrity.verify_state()
        return Report()

    monkeypatch.setattr(doctor, "diagnose", inspect)
    result = CliRunner().invoke(app, ["doctor", "--repo", str(repo), "--config-dir", str(settings)])
    assert result.exit_code == 0, result.output
    assert seen == [app_security.path]
    assert not (settings / "state.db").exists()


def confidential_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".crocodile").mkdir(parents=True)
    (repo / ".crocodile/confidential").touch()
    return repo


def test_confidential_startup_and_model_use_only_canonical_local_key(
    tmp_path, credential_backend, monkeypatch
):
    repo = confidential_repo(tmp_path)
    services.override("egress", FakeEgress([]))
    agent = Agent(repo, "synthetic task", step_cap=0)
    agent.run()
    assert credential_backend.calls == [VK_LOCAL]
    gateway = GatewayEgress()
    seen = []

    def post(**kwargs):
        seen.append((kwargs["vk"], kwargs["vk_alias"]))
        return 200, {"model": "ollama/qwen2.5-coder:7b", "choices": [], "usage": {}}, {}

    monkeypatch.setattr(gateway.client, "post_bifrost", post)
    gateway.chat([], [], session=agent.s, tier="strong")
    with pytest.raises(PermissionError):
        gateway.web_search("must not load a Tavily credential", session=agent.s)
    assert seen == [(credential_backend.values[VK_LOCAL], "local")]
    assert set(credential_backend.calls) == {VK_LOCAL}
    gateway.client._http_client.close()


def test_missing_local_key_never_uses_env_legacy_public_or_tavily(tmp_path, monkeypatch, credential_backend):
    credential_backend.values.pop(VK_LOCAL)
    credential_backend.values["vk-local"] = "legacy-local"
    credential_backend.values["tavily_key"] = "tavily-present"
    for name in ("CROCODILE_VK_LOCAL", "CROCODILE_VK_PUBLIC", "CROCODILE_VK", "TAVILY_API_KEY"):
        monkeypatch.setenv(name, "environment-must-not-be-used")
    with pytest.raises(CredentialUnavailable, match="vk_local"):
        Agent(confidential_repo(tmp_path), "synthetic", step_cap=0)
    assert credential_backend.calls == [VK_LOCAL]


def test_explicit_credential_copy_preserves_legacy_and_refuses_conflict(credential_backend):
    credential_backend.values.pop(VK_LOCAL)
    credential_backend.values["vk-local"] = "legacy-fixture"
    with pytest.raises(CredentialUnavailable):
        CredentialStore().gateway("local")
    assert copy_legacy_credential("local", backend=credential_backend) is None
    assert CredentialStore().gateway("local") == "legacy-fixture"
    assert credential_backend.values["vk-local"] == "legacy-fixture"
    credential_backend.values[VK_LOCAL] = "different"
    with pytest.raises(CredentialUnavailable, match="conflict"):
        copy_legacy_credential("local", backend=credential_backend)
    assert credential_backend.values[VK_LOCAL] == "different"


@pytest.mark.parametrize("spelling", ["session_start", "session_started"])
def test_legacy_sqlite_replay_sticky_detection_and_audit(tmp_path, app_security, spelling):
    from crocodile.gateway.egress import log_egress

    repo = tmp_path / "repo"
    repo.mkdir()
    journal = EventJournal(app_security.path)
    payload = {"repo": str(repo), "mode": "confidential"}
    with sqlite3.connect(app_security.path) as db:
        db.execute(
            "INSERT INTO events(session,seq,ts,type,payload) VALUES (?,?,?,?,?)",
            ("private-session", 1, 1.0, spelling, json.dumps(payload)),
        )
    resumed = journal.resume("private-session")
    assert resumed.mode == "confidential" and resumed.repo_root == str(repo)
    assert resumed.events[0]["type"] == SESSION_STARTED
    assert journal.get_events("private-session")[0]["type"] == SESSION_STARTED
    assert SecurityStore(app_security.path).is_confidential(RepoIdentity(str(repo)))
    values = dict(
        session="private-session",
        request_id="r1",
        dest="http://127.0.0.1:8080",
        vk_alias="local",
        mode="confidential",
        model_requested="ollama/qwen2.5-coder:7b",
        fallbacks=[],
        model_actual="qwen2.5-coder:7b",
        provider_actual="ollama",
        payload_sha256="a" * 64,
        payload_bytes=20,
        canary_hits=0,
        verdict="sent",
    )
    log_egress(app_security.path, **values)
    evidence = {
        key: values[key]
        for key in (
            "session",
            "request_id",
            "vk_alias",
            "model_requested",
            "fallbacks",
            "payload_sha256",
            "payload_bytes",
        )
    }
    evidence.update(provider="ollama", model="qwen2.5-coder:7b")
    report = audit_database(
        app_security.path, allowlist=["qwen2.5-coder:7b"], gateway_logs=[evidence], all_sessions=True
    )
    assert report.status == "PASS", report.render()


@pytest.mark.parametrize("spelling", ["session_start", "session_started"])
@pytest.mark.parametrize("flat", [False, True])
def test_jsonl_legacy_envelopes_preserve_confidential_history(tmp_path, app_security, spelling, flat):
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = {"repo": str(repo), "mode": "confidential"}
    record = (
        {"ts": 1, "session": "s", "event": spelling, **payload}
        if flat
        else {"ts": 1, "session": "s", "type": spelling, "payload": payload}
    )
    path = tmp_path / "legacy.jsonl"
    path.write_text(json.dumps(record) + "\n")
    assert read_envelope(record)[0] == SESSION_STARTED
    store = SecurityStore(app_security.path, journals=[path])
    assert store.is_confidential(RepoIdentity(str(repo)))


def test_new_writes_canonical_and_replay_never_downgrades(app_security, tmp_path):
    journal = EventJournal(app_security.path)
    for spelling, mode in (("session_start", "confidential"), (SESSION_STARTED, "public")):
        journal.append("s", spelling, {"repo_root": str(tmp_path), "mode": mode})
    with sqlite3.connect(app_security.path) as db:
        assert db.execute("SELECT DISTINCT type FROM events").fetchall() == [(SESSION_STARTED,)]
    assert journal.resume("s").mode == "confidential"
    with pytest.raises(ValueError, match="conflicting"):
        read_envelope({"type": "session_start", "event": "other", "payload": {}})


def test_gateway_and_jsonl_producers_share_canonical_envelope(tmp_path):
    from crocodile.agent_types import Session
    from crocodile.runtime_security import session_directory

    root = tmp_path / "repo"
    root.mkdir()
    directory = session_directory("shared-event")
    directory.mkdir(parents=True)
    session = Session("shared-event", root, "confidential", state_dir=directory)
    journal = GatewayJournal()
    journal.append(session, "session_start", {"repo": str(root), "mode": "confidential"})
    stored = json.loads((directory / "journal.jsonl").read_text())
    assert stored["type"] == SESSION_STARTED and stored["payload"]["repo_root"] == str(root)
    replay = journal.resume(session.id)
    assert replay[0]["type"] == SESSION_STARTED and replay[0]["payload"]["mode"] == "confidential"


@pytest.mark.parametrize("bench", [False, True])
def test_public_and_bench_use_their_canonical_keys(
    tmp_path, app_security, credential_backend, monkeypatch, bench
):
    from crocodile.agent_types import Session
    from crocodile.security import ApprovalSession
    from crocodile.security.confidential import Detector

    scratch = tmp_path / "scratch"
    root = scratch / "repo"
    root.mkdir(parents=True)
    task = "trusted fixture"
    detector = Detector(SecurityStore(app_security.path, integrity=app_security))
    sec = (
        ApprovalSession.for_bench(
            root, parent=scratch, user_task=task, integrity=app_security, confidentiality=detector
        )
        if bench
        else ApprovalSession(root, user_task=task, integrity=app_security, confidentiality=detector)
    )
    context = SecurityContext(root, task, security_session=sec)
    session = Session("fixture", root, "public", approve_mode="auto" if bench else "ask", security=context)
    gateway = GatewayEgress()
    seen = []

    def post(**kwargs):
        seen.append((kwargs["vk_alias"], kwargs["vk"]))
        return 200, {"model": kwargs["body"]["model"], "choices": [], "usage": {}}, {}

    monkeypatch.setattr(gateway.client, "post_bifrost", post)
    try:
        gateway.chat([], [], session=session, tier="cheap")
        alias = "bench" if bench else "public"
        assert seen == [(alias, credential_backend.values["vk_" + alias])]
        assert credential_backend.calls == ["vk_" + alias]
    finally:
        gateway.client._http_client.close()
        if bench:
            sec.close_bench()


def test_resume_refuses_changed_database_and_reads_old_signed_checkpoint(tmp_path, app_security):
    from crocodile.runtime_security import session_directory
    from crocodile.security.integrity import IntegrityViolation

    root = tmp_path / "repo"
    root.mkdir()
    services.override("egress", FakeEgress([]))
    agent = Agent(root, "fixture", step_cap=0)
    alternate = tmp_path / "alternate.db"
    backup(app_security.path, alternate)
    with pytest.raises(IntegrityViolation, match="another state database"):
        SecurityContext.resume(root, agent.s.id, integrity=StateIntegrity(alternate, keys=app_security.keys))
    path = session_directory(agent.s.id) / "context.json"
    historical = json.loads(path.read_text())
    del historical["data"]["state_db"]
    historical["hmac"] = agent.security._signature(historical["data"])
    path.write_text(json.dumps(historical))
    resumed, _ = SecurityContext.resume(root, agent.s.id, integrity=app_security)
    assert resumed.original_task == "fixture"
