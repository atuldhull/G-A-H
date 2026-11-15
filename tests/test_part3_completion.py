"""Normal CLI and contract regressions for the Part 3 completion audit."""

import re
import sqlite3
import sys
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from crocodile import contracts
from crocodile.adapters import bifrost_url
from crocodile.cli import _write_default_settings, app
from crocodile.gateway.diagnostics import collect_evidence
from crocodile.gateway.network_policy import NetworkPolicy
from crocodile.gateway_settings import gateway_url
from crocodile.security import approvals, cmd, confidential
from crocodile.security.classification import ClassificationError, RepoIdentity, SecurityStore
from crocodile.security.integrity import IntegrityViolation
from crocodile.security.session import ApprovalSession


def classify_answer(preview):
    return re.search(r"Type ([a-z]+ \d{2}) to confirm", preview)[1]


def test_root_init_classifies_registers_canary_and_clears_with_valid_hmac(
    tmp_path, monkeypatch, app_security
):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "source.py").write_text("answer = 42\n")
    monkeypatch.setattr(approvals, "_console_answer", classify_answer)
    runner = CliRunner()
    result = runner.invoke(
        app, ["init", "--repo", str(root), "--confidential", "--canary-source", "source.py"]
    )
    assert result.exit_code == 0, result.output
    app_security.verify_state()
    token = (root / ".crocodile/canary").read_text().strip()
    assert token in SecurityStore(app_security.path, integrity=app_security).canaries()
    assert token in (root / "source.py").read_text()
    assert (root / ".crocodile/confidential").exists()
    cleared = runner.invoke(app, ["init", "--repo", str(root), "--public"])
    assert cleared.exit_code == 0, cleared.output
    assert not (root / ".crocodile/confidential").exists()
    app_security.verify_state()
    assert (
        confidential.mode_for(root, root=root, store=SecurityStore(app_security.path, integrity=app_security))
        == "public"
    )


def test_refused_classification_and_invalid_options_have_no_effect(tmp_path, monkeypatch, app_security):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(approvals, "_console_answer", lambda _: "n")
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--repo", str(root), "--confidential"])
    assert result.exit_code == 1
    assert not (root / ".crocodile").exists()
    app_security.verify_state()
    for args in (["--confidential", "--public"], ["--canary-source", "source.py"], ["--repo", str(root)]):
        assert runner.invoke(app, ["init", *args]).exit_code == 2


def test_standalone_classification_uses_integrity_transaction(tmp_path, monkeypatch, app_security):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(approvals, "_console_answer", classify_answer)
    assert (
        confidential.main(
            ["init", "--repo", str(root), "--state-db", str(app_security.path), "--confidential"]
        )
        == 0
    )
    app_security.verify_state()


def test_unsigned_classification_cannot_poison_sealed_state(tmp_path, app_security):
    before = app_security.verify_state()
    with pytest.raises(ClassificationError, match="attached state integrity"):
        SecurityStore(app_security.path).record(RepoIdentity(str(tmp_path)), "confidential")
    assert app_security.verify_state() == before


def test_init_does_not_accept_a_tampered_existing_seal(app_security):
    with sqlite3.connect(app_security.path) as db:
        db.execute("UPDATE meta SET v='tampered' WHERE k='hmac'")
    assert CliRunner().invoke(app, ["init"]).exit_code == 1
    with pytest.raises(IntegrityViolation):
        app_security.verify_state()


def test_shared_action_works_with_approval_and_hardened_runner(tmp_path, app_security):
    root = tmp_path / "repo"
    root.mkdir()
    session = ApprovalSession(root, integrity=app_security)
    action = contracts.Action("shell", argv=[sys.executable, "-c", "print('shared contract fixture')"])
    grant = approvals.ask(action, session=session)
    assert isinstance(grant, contracts.Decision) and grant.verdict == "allow"
    result = cmd.run(action.argv, root, timeout=20, session=session, action=action, decision=grant)
    assert isinstance(result, contracts.CmdResult)
    assert result.returncode == 0 and result.stdout.strip() == "shared contract fixture"
    with pytest.raises(approvals.ApprovalDenied):
        cmd.run(action.argv, root, timeout=20, session=session, action=action, decision=grant)


def test_shared_action_changes_during_preview_are_refused(tmp_path, monkeypatch, app_security):
    root = tmp_path / "repo"
    root.mkdir()
    session = ApprovalSession(root, integrity=app_security)
    action = contracts.Action("shell", argv=[sys.executable, "-c", "print('original')"])

    def changed(_preview):
        action.argv[-1] = "print('changed')"
        return "y"

    monkeypatch.setattr(approvals, "_console_answer", changed)
    assert approvals.ask(action, session=session).verdict == "deny"


def test_generated_and_legacy_settings_share_runtime_and_doctor_reader(monkeypatch, app_security):
    monkeypatch.delenv("CROCODILE_BIFROST_URL", raising=False)
    folder = app_security.path.parent
    _write_default_settings(folder)
    settings = yaml.safe_load((folder / "config.yaml").read_text())
    assert "bifrost" in settings and "bifrost_url" not in settings
    assert gateway_url(settings) == bifrost_url()
    client = SimpleNamespace(network_policy=NetworkPolicy(), probe=lambda *_a, **_kw: (503, {}))
    evidence = collect_evidence(settings, client=client)
    assert "gateway reachability" in evidence["probe_status"]
    assert evidence["probe_status"]["gateway reachability"] == "FAIL"
    legacy = {**settings, "bifrost_url": gateway_url(settings)}
    del legacy["bifrost"]
    (folder / "config.yaml").write_text(yaml.safe_dump(legacy))
    assert bifrost_url() == gateway_url(settings)
    _write_default_settings(folder)
    assert yaml.safe_load((folder / "config.yaml").read_text()) == legacy
    assert "gateway reachability" in collect_evidence(legacy, client=client)["probe_status"]
    with pytest.raises(ValueError, match="conflicting"):
        gateway_url({"bifrost_url": "http://127.0.0.1:8081", "bifrost": settings["bifrost"]})


def test_unknown_action_objects_are_denied():
    # Shared type adaptation must not introduce permissive object deserialization.
    class Untrusted:
        kind = "shell"

    assert approvals.ask(Untrusted()).verdict == "deny"
