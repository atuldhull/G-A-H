"""Normal app entry points with real approvals, SQLite seals and disposable files."""

import json
import sqlite3
import sys

import pytest
from security_support import confirm
from test_loop import FakeEgress
from typer.testing import CliRunner

from crocodile import services
from crocodile.adapters import SecurityBridge
from crocodile.agent_types import Action, Session
from crocodile.cli import app
from crocodile.loop import Agent
from crocodile.runtime_security import SecurityContext, session_directory
from crocodile.security import approvals
from crocodile.security.integrity import IntegrityViolation
from crocodile.tools import dispatch


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return root


def agent(root, script=(), **kw):
    services.override("egress", FakeEgress(script))
    return Agent(root, "repair the fixture", flags=set(), **kw)


def test_root_commands_delegate(root, tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for command in ("quote", "audit", "undo", "doctor", "redteam"):
        assert command in result.output
        help_result = runner.invoke(app, [command, "--help"])
        assert help_result.exit_code == 0, help_result.output
    assert runner.invoke(app, ["quote", "repair", "--repo", str(root), "--ascii"]).exit_code == 0
    assert runner.invoke(app, ["redteam"]).exit_code == 2
    assert runner.invoke(app, ["redteam", "--inventory"]).exit_code == 0
    audit = runner.invoke(
        app, ["audit", "--all", "--allow-model", "ollama/fixture", "--state-db", str(tmp_path / "absent.db")]
    )
    assert audit.exit_code == 2, audit.output
    doctor = runner.invoke(app, ["doctor", "--repo", str(root), "--config-dir", str(tmp_path / "missing")])
    assert doctor.exit_code == 1, doctor.output


def test_unapproved_command_and_yes_never_execute(root):
    bridge = SecurityBridge()
    session = Session("unbound", root, "public", approve_mode="auto")
    argv = [sys.executable, "-c", "print('must not execute')"]
    assert not bridge.ask(Action("shell", "run", argv=argv), session).approved
    assert bridge.run(argv, root).exit_code == 126
    result = CliRunner().invoke(app, ["run", "repair", "--repo", str(root), "--yes"])
    assert result.exit_code == 2


def test_read_search_cache_spill_redact_and_attribute(root, monkeypatch):
    token = "ghp_" + "Z" * 36
    (root / "README.md").write_text("heading\nprint('readme-source')\n" + token + "\n")
    a = agent(root)
    output = dispatch("read", {"path": "README.md", "start": 2}, a.ctx)
    assert token not in output.shown
    dispatch("search", {"pattern": "readme-source", "path": "."}, a.ctx)
    dispatch("read", {"path": "README.md", "start": 2}, a.ctx)
    spill = a.ctx.spill.put(token)
    assert token not in a.ctx.spill.get(spill)
    previews = []
    monkeypatch.setattr(approvals, "_console_answer", lambda text: previews.append(text) or "n")
    bridge = services.get("approvals")
    decision = bridge.ask(Action("shell", "test", argv=[sys.executable, "-c", "print('readme-source')"]), a.s)
    assert not decision.approved
    assert any("README.md:2" in preview for preview in previews)


def test_write_preimage_race_is_refused(root, monkeypatch):
    path = root / "file.py"
    path.write_text("before\n")
    a = agent(root)
    dispatch("read", {"path": "file.py"}, a.ctx)

    def race(prompt):
        path.write_text("user changed it\n")
        return confirm(prompt)

    monkeypatch.setattr(approvals, "_console_answer", race)
    result = dispatch("write", {"path": "file.py", "content": "after"}, a.ctx)
    assert not result.ok
    assert path.read_text() == "user changed it\n"


@pytest.mark.parametrize("kind", ["modified", "created", "removed"])
def test_cli_undo_restores_edit_lifecycle(root, kind):
    path = root / "file.txt"
    if kind != "created":
        path.write_text("before\n")
    a = agent(root)
    if kind != "created":
        dispatch("read", {"path": "file.txt"}, a.ctx)
    result = dispatch(
        "delete" if kind == "removed" else "write", {"path": "file.txt", "content": "after"}, a.ctx
    )
    assert result.ok and result.edit_id, result.shown
    undo = CliRunner().invoke(app, ["undo", "--repo", str(root)])
    assert undo.exit_code == 0, undo.output
    assert path.read_text() == "before\n" if kind != "created" else not path.exists()


def test_undo_conflict_preserves_user_edit(root):
    path = root / "file.txt"
    path.write_text("before\n")
    a = agent(root)
    dispatch("read", {"path": "file.txt"}, a.ctx)
    assert dispatch("write", {"path": "file.txt", "content": "after"}, a.ctx).ok
    path.write_text("user changed it\n")
    result = CliRunner().invoke(app, ["undo", "--repo", str(root)])
    assert result.exit_code == 1, result.output
    assert path.read_text() == "user changed it\n"


def test_resume_preserves_original_context_and_refuses_tamper(root, app_security):
    (root / "README.md").write_text("python -m pytest\n")
    a = agent(root)
    dispatch("read", {"path": "README.md"}, a.ctx)
    a._save_context()
    resumed = agent(root, resume=a.s.id)
    assert resumed.original_task == "repair the fixture"
    assert resumed.security.p3.provenance.observations()
    assert not resumed.security.p3._permits and resumed.security.p3._consent is None
    with pytest.raises(ValueError, match="original user task"):
        Agent(root, "different", resume=a.s.id)
    path = session_directory(a.s.id) / "context.json"
    data = json.loads(path.read_text())
    data["data"]["original_task"] = "attacker"
    path.write_text(json.dumps(data))
    with pytest.raises(IntegrityViolation, match="signature"):
        SecurityContext.resume(root, a.s.id, integrity=app_security)


def test_pending_operation_cannot_be_replayed(root, app_security):
    a = agent(root)
    a._save_context(pending={"tool": "write", "id": "ambiguous"})
    with pytest.raises(IntegrityViolation, match="outcome unknown"):
        SecurityContext.resume(root, a.s.id, integrity=app_security)


def test_normal_run_and_resume_cli(root):
    services.override("egress", FakeEgress([]))
    runner = CliRunner()
    result = runner.invoke(app, ["run", "repair the fixture", "--repo", str(root), "--steps", "0", "--quiet"])
    assert result.exit_code == 1, result.output
    checkpoints = list(session_directory("placeholder").parent.glob("*/context.json"))
    assert len(checkpoints) == 1
    resumed = runner.invoke(
        app, ["run", "--repo", str(root), "--resume", checkpoints[0].parent.name, "--steps", "0", "--quiet"]
    )
    assert resumed.exit_code == 1, resumed.output


def test_state_tamper_aborts_before_next_request(root, app_security):
    a = agent(root)
    with sqlite3.connect(app_security.path) as db:
        db.execute("INSERT INTO grants VALUES ('tampered','[]')")
    receipt = a.run()
    assert receipt.status == "STOPPED: integrity violation"
    assert a.security.p3._aborted
    assert services.get("egress").calls == []


def test_consent_reuses_exact_command_and_invalidates_after_edit(root, monkeypatch):
    a = agent(root)
    previews = []
    monkeypatch.setattr(approvals, "_console_answer", lambda text: previews.append(text) or confirm(text))
    bridge = services.get("approvals")
    action = Action("test_consent", "tests", argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    assert bridge.ask(action, a.s).approved
    count = len(previews)
    assert count == 1 and "interpreter/executable:" in previews[-1]
    assert bridge.ask(action, a.s).approved and len(previews) == count
    changed = Action("test_consent", "tests", argv=[*action.argv, "test_fixture.py"])
    assert bridge.ask(changed, a.s).approved and len(previews) == count + 1
    (root / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert bridge.ask(changed, a.s).approved and len(previews) == count + 2
    assert "sha256" in previews[-1].lower()
    assert dispatch("write", {"path": "new.py", "content": "import subprocess\n"}, a.ctx).ok
    assert a.security.p3._consent is None
    count = len(previews)
    assert bridge.ask(changed, a.s).approved and len(previews) == count + 1
    consent = a.security.p3._consent
    monkeypatch.setattr(approvals, "_console_answer", lambda _: "n")
    assert not dispatch("write", {"path": "denied.py", "content": "import socket\n"}, a.ctx).ok
    assert a.security.p3._consent == consent


def test_confidential_context_restricts_gateway_and_web(root, monkeypatch):
    from types import SimpleNamespace

    from crocodile.adapters import GatewayEgress

    metadata = root / ".crocodile"
    metadata.mkdir()
    (metadata / "confidential").touch()
    a = agent(root)
    assert a.s.mode == "confidential" and "_web" not in a.s.flags
    gateway = GatewayEgress()
    seen = {}
    def fake_chat(*_args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text="fixture", tool_calls=[], model_used="ollama/fixture",
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_tokens=0),
            is_fallback=False, error_class=None, cost_usd=0)
    monkeypatch.setattr(gateway.client, "chat", fake_chat)
    monkeypatch.setattr(gateway, "_vk", lambda _: "fixture")
    gateway.chat([], [], session=a.s, tier="strong")
    assert seen["mode"] == "confidential" and seen["vk_alias"] == "local"
    assert seen["fallbacks"] == [] and all(model.startswith("ollama/") for model in seen["chain"])
    with pytest.raises(PermissionError):
        gateway.web_search("fixture", session=a.s)
