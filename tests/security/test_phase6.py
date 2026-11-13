"""Synthetic secrets, real SQLite/WAL and disposable child/Git fixtures."""

import copy
import io
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crocodile.security import Action, ApprovalSession, approvals, cmd, procs
from crocodile.security.classification import RepoIdentity, SecurityStore
from crocodile.security.doctor import (
    Diagnostic,
    DoctorReport,
    check_local_model,
    diagnose,
)
from crocodile.security.doctor import main as doctor_main
from crocodile.security.git import Git
from crocodile.security.integrity import (
    HMACKeys,
    IntegrityViolation,
    StateIntegrity,
    WatchSet,
    verify_state,
)


class Vault:
    def __init__(self):
        self.value = None
        self.writes = 0

    def get_password(self, service, username):
        assert (service, username) == ("crocodile", "hmac_key")
        return self.value

    def set_password(self, service, username, value):
        assert (service, username) == ("crocodile", "hmac_key")
        self.value = value
        self.writes += 1


def confirm(prompt):
    required = re.search(r"Type ([a-z]+ \d{2}) to approve", prompt)
    return required[1] if required else "y"


class Phase6Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        self.settings = self.base / "settings"
        self.settings.mkdir()
        for name in ("config.yaml", "policy.yaml", "prices.yaml"):
            (self.settings / name).write_text("synthetic: true\n")
        self.path = self.settings / "state.db"
        self.vault = Vault()
        self.integrity = StateIntegrity(self.path, keys=HMACKeys(backend=self.vault))
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE ledger(id TEXT PRIMARY KEY, window TEXT, reserved_usd REAL);
                CREATE TABLE grants(session TEXT, argv_json TEXT);
                CREATE TABLE confidential_repos(first_commit TEXT,realpath TEXT,remote TEXT,since REAL);
                INSERT INTO ledger VALUES ('fixture', '2000-01-01', 1.0);
            """)
            db.execute("BEGIN IMMEDIATE")
            self.integrity.initialize(db)
        self.session = ApprovalSession(
            self.root, mode="confidential", integrity=self.integrity
        )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def tearDown(self):
        deadline = time.monotonic() + 2
        while True:
            try:
                self.temporary.cleanup()
                return
            except OSError as error:
                if (
                    getattr(error, "winerror", None) != 32
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.05)

    def command(self, source, timeout=15):
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            return cmd.run(
                [sys.executable, "-I", "-c", source],
                self.root,
                timeout=timeout,
                session=self.session,
            )

    def test_key_create_read_no_rotation_and_missing_key_no_repair(self):
        self.assertEqual(self.vault.writes, 1)
        key = self.integrity.keys.load(create=True)
        self.assertEqual(len(key), 32)
        self.assertEqual(self.vault.writes, 1)
        self.vault.value = None
        with self.assertRaises(IntegrityViolation):
            self.integrity.verify_state()
        self.assertEqual(self.vault.writes, 1)
        self.assertIsNone(self.vault.value)

    def test_key_backend_failure_is_masked(self):
        with (
            patch.object(
                self.vault,
                "get_password",
                side_effect=OSError("password=synthetic-do-not-print"),
            ),
            self.assertRaises(IntegrityViolation) as raised,
        ):
            self.integrity.keys.load()
        self.assertNotIn("synthetic-do-not-print", str(raised.exception))

    def test_reinitialization_does_not_replace_a_lost_key(self):
        self.vault.value = None
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(IntegrityViolation):
                self.integrity.initialize(db)
        self.assertEqual(self.vault.writes, 1)
        self.assertIsNone(self.vault.value)

    def test_verify_all_windows_and_authorized_transaction(self):
        original = self.integrity.verify_state()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.assertEqual(self.integrity.before_reserve(db), original)
            with self.integrity.authorized_write(db):
                db.execute("UPDATE ledger SET reserved_usd=2")
                db.execute("INSERT INTO grants VALUES ('fixture', '[]')")
        self.assertNotEqual(self.integrity.verify_state(), original)
        with self.db() as db:
            db.execute("UPDATE ledger SET window='1999-12-31'")
        with self.assertRaises(IntegrityViolation):
            self.integrity.verify_state()

    def test_tamper_each_protected_table_and_seal(self):
        statements = (
            "DELETE FROM ledger",
            "INSERT INTO grants VALUES ('bad','[]')",
            "INSERT INTO confidential_repos VALUES(NULL,'tampered',NULL,1)",
            "UPDATE meta SET v='bad' WHERE k='hmac'",
            "DROP TABLE grants",
            "ALTER TABLE ledger ADD COLUMN altered TEXT",
        )
        baseline = self.path.read_bytes()
        for sql in statements:
            with self.subTest(sql=sql):
                with self.db() as db:
                    db.execute(sql)
                with self.assertRaises(IntegrityViolation):
                    self.integrity.verify_state()
                self.path.write_bytes(baseline)

    def test_authorized_write_cannot_bless_tampering_and_rolls_back_errors(self):
        original = self.integrity.verify_state()
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"), self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            with self.integrity.authorized_write(db):
                db.execute("DELETE FROM ledger")
                raise RuntimeError("synthetic failure")
        self.assertEqual(self.integrity.verify_state(), original)
        with self.db() as db:
            db.execute("DELETE FROM ledger")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            with (
                self.assertRaises(IntegrityViolation),
                self.integrity.authorized_write(db),
            ):
                self.fail("unverified owner write must never run")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(IntegrityViolation):
                self.integrity.initialize(db)

    def test_transaction_and_connection_identity_required(self):
        with self.db() as db, self.assertRaises(IntegrityViolation):
            self.integrity.before_reserve(db)
        other = sqlite3.connect(":memory:")
        try:
            other.execute("BEGIN")
            with self.assertRaises(IntegrityViolation):
                self.integrity.before_reserve(other)
        finally:
            other.close()

    def test_wal_tamper_is_detected_while_writer_remains_open(self):
        with self.db() as db:
            db.execute("UPDATE ledger SET reserved_usd=999")
            db.commit()
            self.assertTrue(Path(str(self.path) + "-wal").exists())
            with self.assertRaises(IntegrityViolation):
                self.integrity.verify_state()

    def test_registry_and_canary_authorized_writes_reseal(self):
        store = SecurityStore(self.path, integrity=self.integrity)
        identity = RepoIdentity(str(self.root))
        store.record(
            identity,
            "confidential",
            canary=("synthetic-canary", self.root / "source.py"),
        )
        self.integrity.verify_state()
        self.assertTrue(store.is_confidential(identity))
        self.assertEqual(store.canaries(), ("synthetic-canary",))
        with self.db() as db:
            db.execute("DELETE FROM canaries")
        with self.assertRaises(IntegrityViolation):
            store.canaries()

    def test_missing_sealed_database_is_never_empty_public_evidence(self):
        store = SecurityStore(self.path, integrity=self.integrity)
        self.path.unlink()
        with self.assertRaises(IntegrityViolation):
            store.evidence()
        with self.assertRaises(IntegrityViolation):
            store.canaries()

    def test_tool_decision_latches_abort_and_revokes_permits(self):
        self.session._consent = "fixture"
        self.session._permits["fixture"] = "permit"
        with self.db() as db:
            db.execute("DELETE FROM ledger")
        action = Action(
            "shell",
            argv=[sys.executable, "-I", "-c", "print('safe')"],
            cwd=str(self.root),
        )
        decision = approvals.ask(action, session=self.session)
        self.assertEqual(decision.verdict, "deny")
        self.assertTrue(self.session._aborted)
        self.assertIsNone(self.session._consent)
        self.assertFalse(self.session._permits)
        self.assertEqual(
            sum(e["event"] == "integrity_violation" for e in self.session.events), 1
        )
        with self.assertRaises(IntegrityViolation):
            verify_state(self.integrity, session=self.session)

    def test_real_child_tampering_aborts_and_discards_result(self):
        self.assertIn("safe", self.command("print('safe')").stdout)
        target = self.settings / "policy.yaml"
        source = (
            "from pathlib import Path; Path("
            + repr(str(target))
            + ").write_text('tampered'); print('must not return')"
        )
        with self.assertRaises(IntegrityViolation):
            self.command(source)
        self.assertTrue(self.session._aborted)
        with self.assertRaises(IntegrityViolation):
            self.session.verify_integrity()

    def test_watch_runs_even_when_command_raises(self):
        def failure(*args, before_spawn, **kwargs):
            before_spawn()
            (self.root / ".crocodile").mkdir()
            raise OSError("synthetic spawn failure")

        with (
            patch("crocodile.security.cmd.procs.run", side_effect=failure),
            self.assertRaises(IntegrityViolation),
        ):
            self.command("print('safe')")
        self.assertTrue(self.session._aborted)

    def test_real_child_ledger_tamper_aborts(self):
        source = (
            "import sqlite3; db=sqlite3.connect("
            + repr(str(self.path))
            + "); db.execute('DELETE FROM ledger'); db.commit(); db.close()"
        )
        with self.assertRaises(IntegrityViolation):
            self.command(source)
        self.assertTrue(self.session._aborted)
        self.assertTrue(
            any(e["event"] == "integrity_violation" for e in self.session.events)
        )

    def test_watch_set_covers_metadata_and_nested_markers(self):
        (self.root / ".git" / "hooks").mkdir(parents=True)
        (self.root / ".git" / "info").mkdir()
        hooks = self.base / "empty-hooks"
        hooks.mkdir()
        watcher = WatchSet(
            self.root, config_dir=self.settings, state=self.integrity, extra=(hooks,)
        )
        before = watcher.snapshot()
        targets = (
            self.root / ".git" / "config",
            self.root / ".git" / "hooks" / "pre-commit",
            self.root / ".git" / "info" / "attributes",
            self.root / ".gitattributes",
            self.root / ".gitmodules",
            self.settings / "config.yaml",
            self.settings / "prices.yaml",
            hooks / "unexpected",
        )
        for target in targets:
            with self.subTest(target=target.name):
                target.write_text("synthetic")
                self.assertNotEqual(watcher.snapshot(), before)
                target.unlink()
                if target.parent == self.settings:
                    target.write_text("synthetic: true\n")
                self.assertEqual(watcher.snapshot(), before)

    def test_watch_caps_and_hardlinks_fail_closed(self):
        watcher = WatchSet(self.root, config_dir=self.settings)
        with (
            patch("crocodile.security.integrity.MAX_ENTRIES", 1),
            self.assertRaises(IntegrityViolation),
        ):
            watcher.snapshot()
        os.link(self.settings / "config.yaml", self.base / "alias")
        with self.assertRaises(IntegrityViolation):
            watcher.snapshot()

    def test_git_mutation_watch_and_aborted_free_reads(self):
        # Fixture initialization uses the same hardened process boundary.
        exe = str(self.session._exe_pins["git"].path)
        result = procs.run(
            [exe, "init", "--template=", str(self.root)],
            self.root,
            root=self.root,
            timeout=20,
            git_env=True,
        )
        self.assertEqual(result.returncode, 0)
        original_run = procs.run

        def mutate(argv, *args, **kwargs):
            result = original_run(argv, *args, **kwargs)
            if "status" in argv:
                (self.root / ".gitmodules").write_text("unexpected")
            return result

        with (
            Git(self.session) as git,
            patch.object(procs, "run", side_effect=mutate),
            patch.object(approvals, "_console_answer", side_effect=confirm),
            self.assertRaises(IntegrityViolation),
        ):
            git._call(["status", "--porcelain"], mutation=True)
        with Git(self.session) as git, self.assertRaises(IntegrityViolation):
            git.run("status")

    def doctor_inputs(self):
        config = {
            "models": {
                "cheap": {"chain": ["openai/test"]},
                "strong": {"chain": ["openai/test"]},
                "local": {"chain": ["ollama/local:7b"], "ctx_window": 32768},
            },
            "confidential": {
                "local_model_allowlist": ["local:7b"],
                "ollama_host": "http://127.0.0.1:11434",
            },
            "bifrost": {"base_url": "http://127.0.0.1:8080"},
        }
        prices = {
            name: {"tiers": [{"upto": None, "in": 0, "cache_read": 0, "out": 0}]}
            for name in ("openai/test", "ollama/*")
        }
        evidence = {
            "ollama_tags": {
                "models": [{"name": "local:7b", "digest": "a" * 64, "size": 123}]
            },
            "ollama_show": {"local:7b": {"model_info": {"context_length": 32768}}},
            "gateway": {
                "reachable": True,
                "inference_auth": True,
                "vk_alias": "local",
                "requested_model": "openai/test",
                "refusal_status": 403,
                "provider_calls": 0,
            },
            "socket_guard_active": True,
            "limits_admin_owned": True,
            "limits_user_writable": False,
        }
        environment = {"OLLAMA_CONTEXT_LENGTH": "32768", "OLLAMA_NO_CLOUD": "1"}
        return {
            "session": self.session,
            "config": config,
            "prices": prices,
            "evidence": evidence,
            "environment": environment,
        }

    def test_doctor_success_with_trusted_owner_evidence(self):
        # Machine tool availability is independent of the diagnostic logic.
        with patch(
            "crocodile.security.doctor.resolve_pinned",
            return_value=Path(sys.executable),
        ):
            report = diagnose(**self.doctor_inputs())
        self.assertTrue(report.passed, report.render())
        self.assertNotIn(self.vault.value, report.render())

    def test_doctor_failures_and_missing_evidence(self):
        inputs = self.doctor_inputs()
        variants = []
        for kind in (
            "missing probe",
            "cloud model",
            "remote host",
            "TBD price",
            "remote show",
            "missing blob",
            "provider call",
            "writable limits",
            "small context",
        ):
            item = copy.deepcopy({k: v for k, v in inputs.items() if k != "session"})
            if kind == "missing probe":
                item["evidence"] = {}
            if kind == "cloud model":
                item["config"]["models"]["local"]["chain"] = ["ollama/local:cloud"]
            if kind == "remote host":
                item["environment"]["OLLAMA_HOST"] = "http://192.0.2.1:11434"
            if kind == "TBD price":
                item["prices"]["openai/test"]["tiers"][0]["out"] = "TBD"
            if kind == "remote show":
                item["evidence"]["ollama_show"]["local:7b"]["remote_host"] = (
                    "cloud.example"
                )
            if kind == "missing blob":
                item["evidence"]["ollama_tags"]["models"] = []
            if kind == "provider call":
                item["evidence"]["gateway"]["provider_calls"] = 1
            if kind == "writable limits":
                item["evidence"]["limits_user_writable"] = True
            if kind == "small context":
                item["environment"]["OLLAMA_CONTEXT_LENGTH"] = "4096"
            variants.append((kind, item))
        with patch(
            "crocodile.security.doctor.resolve_pinned",
            return_value=Path(sys.executable),
        ):
            for kind, item in variants:
                with self.subTest(kind=kind):
                    self.assertFalse(diagnose(session=self.session, **item).passed)

    def test_diagnostic_output_masks_credentials_and_control_characters(self):
        secret = "tvly-" + "x" * 32
        report = DoctorReport(
            (Diagnostic("fixture\x1b[31m", "FAIL", "token=" + secret),)
        )
        rendered = report.render()
        self.assertNotIn(secret, rendered)
        self.assertNotIn("\x1b", rendered)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(
                doctor_main(
                    [
                        "--config-dir",
                        str(self.base / "missing"),
                        "--repo",
                        str(self.root),
                    ]
                ),
                1,
            )
        self.assertIn("FAIL", output.getvalue())

    def test_local_model_url_and_tag_rejections(self):
        for tag in (
            "local:cloud",
            "local-cloud",
            "nested/local:7b",
            "local@sha",
            "other",
        ):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                check_local_model(
                    "ollama/" + tag,
                    ["local:7b"] if tag == "other" else [tag],
                    "http://127.0.0.1:11434",
                )
        for host in (
            "https://127.0.0.1:11434",
            "http://user:password@127.0.0.1:11434",
            "http://192.0.2.1:11434",
            "http://127.0.0.1:8080",
        ):
            with self.subTest(host=host), self.assertRaises(ValueError):
                check_local_model("ollama/local:7b", ["local:7b"], host)

    def test_doctor_rejects_repo_config_before_accessing_credentials(self):
        for name in ("config.yaml", "policy.yaml", "prices.yaml"):
            (self.root / name).write_text("synthetic: true\n")
        with (
            patch.dict(sys.modules, {"yaml": SimpleNamespace(safe_load=lambda _: {})}),
            patch("crocodile.security.doctor.StateIntegrity") as state,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                doctor_main(["--repo", str(self.root), "--config-dir", str(self.root)]),
                1,
            )
        state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
