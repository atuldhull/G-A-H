"""Isolated classification state and synthetic egress/gateway evidence."""

import io
import json
import os
import re
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from crocodile.security import Action, ApprovalSession, approvals
from crocodile.security.audit import audit_database, audit_records
from crocodile.security.audit import main as audit_main
from crocodile.security.canaries import check
from crocodile.security.classification import (
    ClassificationError,
    RepoIdentity,
    SecurityStore,
)
from crocodile.security.confidential import Detector, mode_for, set_classification
from crocodile.security.paths import resolve_in_repo

ALLOW = ("qwen2.5-coder:7b",)


def confirm(prompt):
    match = re.search(r"Type ((?:public|confidential) \d{2}) to confirm", prompt)
    return match[1] if match else "n"


def row(session="private-session", request="r1", **changes):
    value = {
        "seq": 1,
        "ts": 1.0,
        "session": session,
        "request_id": request,
        "dest": "http://127.0.0.1:8080/v1/chat/completions",
        "vk_alias": "local",
        "mode": "confidential",
        "model_requested": "ollama/qwen2.5-coder:7b",
        "fallbacks": "[]",
        "model_actual": "qwen2.5-coder:7b",
        "provider_actual": "ollama",
        "payload_sha256": "a" * 64,
        "payload_bytes": 20,
        "canary_hits": 0,
        "verdict": "sent",
        "block_reason": None,
    }
    value.update(changes)
    return value


def log(request="r1", **changes):
    value = {"request_id": request, "provider": "ollama", "model": "qwen2.5-coder:7b"}
    value.update(changes)
    return value


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class Phase4Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        self.store = SecurityStore(self.base / "state.db")
        self.detector = Detector(
            self.store, identity_reader=lambda p: RepoIdentity(str(p))
        )
        self.addCleanup(self.cleanup_fixture)
        console = patch.object(approvals, "_console_answer", return_value="n")
        console.start()
        self.addCleanup(console.stop)

    def cleanup_fixture(self):
        deadline = time.monotonic() + 2
        while True:
            try:
                self.temporary.cleanup()
                return
            except PermissionError as error:
                if (
                    os.name != "nt"
                    or error.winerror != 32
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.05)

    def marker(self, root=None):
        root = self.root if root is None else root
        path = root / ".crocodile" / "confidential"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_public_directory_and_before_prompt_mode_interface(self):
        self.assertEqual(
            mode_for(self.root, root=self.root, store=self.store), "public"
        )
        self.assertFalse(self.store.path.exists())

    def test_ancestor_and_realpath_marker_detection(self):
        self.marker()
        child = self.root / "child"
        child.mkdir()
        result = self.detector.detect(child, root=self.root)
        self.assertEqual(result.mode, "confidential")
        alias = self.base / "alias"
        try:
            alias.symlink_to(child, target_is_directory=True)
        except OSError:
            return
        self.assertEqual(
            self.detector.detect(alias, root=self.root).mode, "confidential"
        )

    def test_repo_flag_and_cwd_both_affect_mode(self):
        outside = self.base / "other"
        outside.mkdir()
        self.marker(outside)
        result = self.detector.detect(self.root, root=self.root, cwd=outside)
        self.assertEqual(result.mode, "confidential")

    def test_relative_repo_and_tool_paths_resolve_against_declared_cwd(self):
        nested = self.root / "private"
        self.marker(nested)
        result = self.detector.detect(
            ".", cwd=self.root, root=self.root, tool_paths=["private/data.txt"]
        )
        self.assertEqual(result.mode, "confidential")

    def test_nested_subtree_is_denied_without_classifying_public_siblings(self):
        nested = self.root / "private"
        self.marker(nested)
        result = self.detector.detect(self.root, root=self.root)
        self.assertEqual(result.mode, "public")
        self.assertEqual(result.denied_subtrees, (nested,))
        (self.root / "ordinary.txt").write_text("public fixture", encoding="utf-8")
        self.assertEqual(
            resolve_in_repo("ordinary.txt", self.root, store=self.store),
            self.root / "ordinary.txt",
        )
        with self.assertRaises(ValueError):
            resolve_in_repo("private/data.txt", self.root, store=self.store)
        (nested / ".crocodile" / "confidential").unlink()
        with self.assertRaises(ValueError):
            resolve_in_repo("private/data.txt", self.root, store=self.store)

    def test_registry_and_journal_stickiness_survives_restart_and_row_deletion(self):
        marker = self.marker()
        self.assertEqual(
            self.detector.detect(self.root, root=self.root).mode, "confidential"
        )
        marker.unlink()
        with database(self.store.path) as db:
            db.execute("DELETE FROM confidential_repos")
        restarted = Detector(
            SecurityStore(self.store.path),
            identity_reader=lambda p: RepoIdentity(str(p)),
        )
        result = restarted.detect(self.root, root=self.root)
        self.assertEqual(result.mode, "confidential")
        self.assertTrue(result.alerts)
        with database(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM confidential_repos").fetchone()[0], 1
            )

    def test_clone_and_remote_aliases_are_sticky_across_sessions(self):
        original = RepoIdentity(
            str(self.root), "a" * 40, "https://example.invalid/repo"
        )
        self.store.record(original, "confidential")
        clone = self.base / "clone"
        clone.mkdir()
        detector = Detector(
            self.store,
            identity_reader=lambda p: RepoIdentity(
                str(p), "a" * 40, "https://example.invalid/changed"
            ),
        )
        self.assertEqual(detector.detect(clone, root=clone).mode, "confidential")
        self.assertTrue(
            self.store.is_confidential(
                RepoIdentity(
                    str(self.base / "third"), None, "https://example.invalid/changed"
                )
            )
        )

    def test_subfolder_run_uses_repository_root(self):
        (self.root / ".git").mkdir()
        self.marker()
        nested = self.root / "src"
        nested.mkdir()
        self.assertEqual(mode_for(nested, store=self.store), "confidential")

    def test_scan_cap_refuses_inconclusive_public_and_force_confidential_works(self):
        for name in ("one", "two", "three"):
            (self.root / name).touch()
        detector = Detector(
            self.store, cap=2, identity_reader=lambda p: RepoIdentity(str(p))
        )
        with self.assertRaisesRegex(ClassificationError, "use --confidential"):
            detector.detect(self.root, root=self.root)
        self.assertEqual(
            detector.detect(self.root, root=self.root, force_confidential=True).mode,
            "confidential",
        )

    def test_scan_skips_documented_directories(self):
        for name in (".git", "node_modules", ".venv"):
            self.marker(self.root / name)
        self.assertEqual(
            self.detector.detect(self.root, root=self.root).denied_subtrees, ()
        )

    def test_inaccessible_scan_is_not_public(self):
        with (
            patch(
                "crocodile.security.confidential.os.scandir",
                side_effect=PermissionError,
            ),
            self.assertRaises(ClassificationError),
        ):
            self.detector.detect(self.root, root=self.root)

    def test_public_session_does_not_clear_confidential_history(self):
        identity = RepoIdentity(str(self.root))
        self.store.record(identity, "confidential")
        self.store.record(
            identity, "public", kind="session_started", session="later-public"
        )
        self.assertTrue(self.store.is_confidential(identity))

    def test_jsonl_part2_journal_restores_sticky_classification(self):
        journal = self.base / "journal.jsonl"
        journal.write_text(
            json.dumps(
                {
                    "session": "s1",
                    "ts": 1.0,
                    "type": "session_started",
                    "payload": {
                        "repo_root": str(self.root),
                        "repo_id": {"realpath": str(self.root)},
                        "mode": "confidential",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        store = SecurityStore(self.base / "other-state.db", journals=[journal])
        detector = Detector(store, identity_reader=lambda p: RepoIdentity(str(p)))
        self.assertEqual(
            detector.detect(self.root, root=self.root).mode, "confidential"
        )

    def test_corrupt_journal_or_state_refuses_public(self):
        self.store.path.write_bytes(b"not a sqlite database")
        with self.assertRaises(ClassificationError):
            self.detector.detect(self.root, root=self.root)

    def test_interactive_init_registers_canary_and_optional_comment(self):
        source = self.root / "module.py"
        source.write_text("x = 1\n", encoding="utf-8")
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            result = set_classification(
                self.root,
                confidential=True,
                store=self.store,
                canary_source="module.py",
            )
        self.assertEqual(result.mode, "confidential")
        token = (self.root / ".crocodile" / "canary").read_text().strip()
        self.assertRegex(token, r"^CANARY-[0-9a-f]{32}$")
        self.assertIn(token, self.store.canaries())
        self.assertIn("# Crocodile canary: " + token, source.read_text())

    def test_public_clear_requires_exact_console_nonce_and_rejects_piped_input(self):
        self.marker()
        self.detector.detect(self.root, root=self.root)
        with (
            patch.object(approvals, "_console_answer", return_value="yes"),
            patch("sys.stdin", io.StringIO("public 47\n")),
            self.assertRaises(approvals.ApprovalDenied),
        ):
            set_classification(self.root, confidential=False, store=self.store)
        with (
            patch.object(
                approvals, "_console_answer", side_effect=OSError("no console")
            ),
            self.assertRaises(approvals.ApprovalDenied),
        ):
            set_classification(self.root, confidential=False, store=self.store)
        self.assertTrue(self.store.is_confidential(RepoIdentity(str(self.root))))

    def test_public_clear_overrides_old_journal_but_keeps_canaries(self):
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            set_classification(self.root, confidential=True, store=self.store)
            tokens = self.store.canaries()
            result = set_classification(self.root, confidential=False, store=self.store)
        self.assertEqual(result.mode, "public")
        self.assertFalse(self.store.is_confidential(RepoIdentity(str(self.root))))
        self.assertEqual(self.store.canaries(), tokens)
        self.assertEqual(self.detector.detect(self.root, root=self.root).mode, "public")

    def test_cannot_clear_an_ancestor_marker(self):
        self.marker(self.base)
        with self.assertRaises(ClassificationError):
            set_classification(self.root, confidential=False, store=self.store)

    def test_classification_change_revalidates_source_preimage(self):
        source = self.root / "module.py"
        source.write_text("x=1", encoding="utf-8")

        def change(prompt):
            source.write_text("changed", encoding="utf-8")
            return confirm(prompt)

        with (
            patch.object(approvals, "_console_answer", side_effect=change),
            self.assertRaises(approvals.ApprovalDenied),
        ):
            set_classification(
                self.root,
                confidential=True,
                store=self.store,
                canary_source="module.py",
            )
        self.assertFalse((self.root / ".crocodile" / "canary").exists())

    def test_session_recheck_promotes_mode_and_invalidates_approval(self):
        session = ApprovalSession(self.root, confidentiality=self.detector)
        action = Action("write", diff="x=1", paths=["module.py"], replacements=["x=1"])
        with patch.object(approvals, "_console_answer", return_value="y"):
            decision = approvals.ask(action, session=session)
        self.marker()
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(action, decision, session=session)
        self.assertEqual(session.mode, "confidential")

    def test_canary_send_time_check_plain_json_and_escaped_json(self):
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            set_classification(self.root, confidential=True, store=self.store)
        token = self.store.canaries()[0]
        for payload in (
            token,
            {"messages": [{"content": token}]},
            json.dumps({"content": token}).encode(),
            json.dumps({"content": token}).replace("C", "\\u0043"),
        ):
            result = check(payload, store=self.store)
            self.assertTrue(result.blocked)
            self.assertEqual(result.hits, 1)
            self.assertNotIn(token, repr(result))
        self.assertFalse(check({"content": "ordinary"}, store=self.store).blocked)
        for payload in (b"\xff", b"\0UTF16-like"):
            with self.assertRaises(ClassificationError):
                check(payload, store=self.store)

    def test_audit_good_local_route_and_blocked_attempt(self):
        blocked = row(
            request="blocked",
            verdict="blocked",
            model_requested="openai/requested",
            model_actual=None,
            provider_actual=None,
            vk_alias="none",
            dest="https://api.tavily.com/search",
            block_reason="confidential web denied",
        )
        report = audit_records(
            [row(), blocked],
            allowlist=ALLOW,
            gateway_logs=[log()],
            session_modes={"private-session": "confidential"},
        )
        self.assertTrue(report.passed, report)
        self.assertEqual(len(report.blocked), 1)
        self.assertIn("BLOCKED", report.render())

    def test_audit_rejects_every_confidential_routing_violation(self):
        for changes in (
            {"vk_alias": "public"},
            {"model_requested": "openai/gpt"},
            {"fallbacks": '["openai/gpt"]'},
            {"provider_actual": "openai"},
            {"model_actual": "qwen:cloud"},
            {"dest": "https://api.tavily.com/search"},
            {"dest": "http://example.invalid:8080"},
        ):
            report = audit_records(
                [row(**changes)],
                allowlist=ALLOW,
                gateway_logs=[log()],
                session_modes={"private-session": "confidential"},
            )
            self.assertEqual(report.status, "FAIL", (changes, report))

    def test_audit_gateway_correlation_and_missing_evidence_fail_closed(self):
        self.assertEqual(
            audit_records(
                [row()],
                allowlist=ALLOW,
                session_modes={"private-session": "confidential"},
            ).status,
            "INCOMPLETE",
        )
        self.assertEqual(
            audit_records([row()], allowlist=ALLOW, gateway_logs=[log()]).status,
            "INCOMPLETE",
        )
        report = audit_records(
            [row()],
            allowlist=ALLOW,
            gateway_logs=[log(provider="openai")],
            session_modes={"private-session": "confidential"},
        )
        self.assertEqual(report.status, "FAIL")

    def test_audit_public_canary_hit_and_session_mode_spoof_fail(self):
        report = audit_records(
            [row(mode="public", canary_hits=1)],
            allowlist=ALLOW,
            session_modes={"private-session": "public"},
        )
        self.assertEqual(report.status, "FAIL")
        report = audit_records(
            [row(mode="public")],
            allowlist=ALLOW,
            session_modes={"private-session": "confidential"},
        )
        self.assertEqual(report.status, "FAIL")

    def test_audit_empty_duplicate_and_malformed_rows_do_not_pass(self):
        self.assertEqual(audit_records([], allowlist=ALLOW).status, "INCOMPLETE")
        self.assertEqual(
            audit_records(
                [row(), row()],
                allowlist=ALLOW,
                gateway_logs=[log()],
                session_modes={"private-session": "confidential"},
            ).status,
            "FAIL",
        )
        self.assertEqual(
            audit_records(
                [row(canary_hits=False)],
                allowlist=ALLOW,
                gateway_logs=[log()],
                session_modes={"private-session": "confidential"},
            ).status,
            "FAIL",
        )

    def egress_fixture(self):
        self.store.record(
            RepoIdentity(str(self.root)),
            "confidential",
            kind="session_started",
            session="private-session",
        )
        self.store.record(
            RepoIdentity(str(self.base / "public-repo")),
            "public",
            kind="session_started",
            session="public-session",
        )
        with database(self.store.path) as db:
            sample = row()
            fields = ",".join(
                f"{key} {'INTEGER' if key in ('seq', 'payload_bytes', 'canary_hits') else 'REAL' if key == 'ts' else 'TEXT'}"
                for key in sample
            )
            db.execute("CREATE TABLE egress (" + fields + ")")
            for values in (
                sample,
                row(
                    session="public-session",
                    request="r2",
                    seq=2,
                    ts=2.0,
                    mode="public",
                    vk_alias="public",
                    model_requested="openai/gpt",
                    model_actual="gpt",
                    provider_actual="openai",
                    dest="http://127.0.0.1:8080",
                ),
            ):
                db.execute(
                    "INSERT INTO egress VALUES (" + ",".join("?" for _ in values) + ")",
                    tuple(values.values()),
                )

    def test_audit_database_latest_and_all_scopes_and_cli(self):
        self.egress_fixture()
        latest = audit_database(self.store.path, allowlist=ALLOW)
        self.assertTrue(latest.passed, latest)
        self.assertEqual(latest.checked, 1)
        all_rows = audit_database(
            self.store.path, allowlist=ALLOW, all_sessions=True, gateway_logs=[log()]
        )
        self.assertTrue(all_rows.passed, all_rows)
        self.assertEqual(all_rows.checked, 2)
        export = self.base / "gateway.json"
        export.write_text(json.dumps([log()]), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            result = audit_main(
                [
                    "--state-db",
                    str(self.store.path),
                    "--all",
                    "--allow-model",
                    ALLOW[0],
                    "--gateway-log",
                    str(export),
                ]
            )
        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("RESULT: PASS", output.getvalue())

    def test_missing_live_database_reports_incomplete(self):
        self.assertEqual(
            audit_database(self.base / "missing.db", allowlist=ALLOW).status,
            "INCOMPLETE",
        )

    def test_public_session_cannot_launder_sticky_private_history_in_audit(self):
        self.egress_fixture()
        self.store.record(
            RepoIdentity(str(self.root)),
            "public",
            kind="session_started",
            session="public-session",
        )
        self.assertEqual(
            audit_database(self.store.path, allowlist=ALLOW).status, "FAIL"
        )

    def test_jsonl_history_can_be_cleared_only_by_console_reclassification(self):
        journal = self.base / "journal.jsonl"
        journal.write_text(
            json.dumps(
                {
                    "session": "s1",
                    "ts": 1.0,
                    "type": "session_started",
                    "payload": {"repo_root": str(self.root), "mode": "confidential"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        store = SecurityStore(self.base / "with-journal.db", journals=[journal])
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            self.assertEqual(
                set_classification(self.root, confidential=False, store=store).mode,
                "public",
            )
        self.assertFalse(store.is_confidential(RepoIdentity(str(self.root))))
        journal.unlink()
        with self.assertRaises(ClassificationError):
            Detector(store).detect(self.root, root=self.root)

    def test_part2_sqlite_journal_is_read_without_writing_its_rows(self):
        with database(self.store.path) as db:
            db.execute(
                "CREATE TABLE events(session TEXT, seq INT, ts REAL, type TEXT, payload TEXT)"
            )
            db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?)",
                (
                    "s1",
                    1,
                    1.0,
                    "session_started",
                    json.dumps({"repo_root": str(self.root), "mode": "confidential"}),
                ),
            )
        self.assertEqual(
            self.detector.detect(self.root, root=self.root).mode, "confidential"
        )
        with database(self.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_invalid_canary_registry_and_payload_shape_refuse_send(self):
        self.store.record(
            RepoIdentity(str(self.root)),
            "confidential",
            canary=("invalid", self.root / "canary"),
        )
        with self.assertRaises(ClassificationError):
            check("ordinary payload", store=self.store)

    def test_invalid_allowlist_missing_hash_and_conflicting_gateway_logs_fail(self):
        for allowlist in (("qwen:CLOUD",), "qwen2.5-coder:7b"):
            self.assertEqual(
                audit_records(
                    [row()],
                    allowlist=allowlist,
                    gateway_logs=[log()],
                    session_modes={"private-session": "confidential"},
                ).status,
                "FAIL",
            )
        self.assertEqual(
            audit_records(
                [row(mode="public", payload_sha256=None)],
                allowlist=ALLOW,
                session_modes={"private-session": "public"},
            ).status,
            "FAIL",
        )
        self.assertEqual(
            audit_records(
                [row()],
                allowlist=ALLOW,
                gateway_logs=[log(), log(provider="openai")],
                session_modes={"private-session": "confidential"},
            ).status,
            "FAIL",
        )

    def test_classification_state_inside_repo_is_refused(self):
        with self.assertRaises(ClassificationError):
            Detector(SecurityStore(self.root / "state.db")).detect(
                self.root, root=self.root
            )
        with self.assertRaises(ClassificationError):
            Detector(
                SecurityStore(self.store.path, journals=[self.root / "untrusted.jsonl"])
            ).detect(self.root, root=self.root)

    def test_unreadable_state_metadata_cannot_be_treated_as_public(self):
        actual = Path.lstat

        def unreadable(path, *args, **kwargs):
            if path == self.store.path:
                raise PermissionError("fixture state denial")
            return actual(path, *args, **kwargs)

        with (
            patch.object(Path, "lstat", unreadable),
            self.assertRaises(ClassificationError),
        ):
            self.detector.detect(self.root, root=self.root)

    def test_real_git_identity_uses_hardened_reads(self):
        from crocodile.security import procs
        from crocodile.security.confidential import identity_for

        session = ApprovalSession(self.root)
        git = str(session._exe_pins["git"].path)

        def fixture(*arguments):
            result = procs.run(
                [
                    git,
                    "-c",
                    "init.templateDir=",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-c",
                    "core.hooksPath=" + str(self.base / "empty-hooks"),
                    *arguments,
                ],
                self.root,
                root=self.root,
                timeout=30,
                git_env=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        fixture("init", "--initial-branch=main")
        (self.root / "fixture.txt").write_text("fixture", encoding="utf-8")
        fixture("add", "--", "fixture.txt")
        fixture("commit", "--no-gpg-sign", "-m", "fixture")
        fixture("config", "remote.origin.url", "https://example.invalid/fixture")
        identity = identity_for(self.root)
        self.assertRegex(identity.first_commit, r"^[0-9a-f]{40}$")
        self.assertEqual(identity.remote, "https://example.invalid/fixture")

    def test_future_alias_changes_do_not_reclassify_past_public_sessions(self):
        private = RepoIdentity(str(self.root), remote="https://example.invalid/private")
        public = RepoIdentity(str(self.base / "public-repo"))
        self.store.record(private, "confidential")
        self.store.record(
            public, "public", kind="session_started", session="public-before"
        )
        stamp = next(
            event["ts"]
            for event in self.store.evidence()
            if event["session"] == "public-before"
        )
        self.store.record(
            RepoIdentity(public.realpath, remote=private.remote), "confidential"
        )
        self.assertTrue(self.store.is_confidential(public))
        self.assertFalse(self.store.is_confidential(public, at_time=stamp))

    def test_audit_uses_partial_git_identity_when_session_path_is_missing(self):
        self.egress_fixture()
        self.store.record(RepoIdentity(str(self.root), "a" * 40), "confidential")
        with database(self.store.path) as db:
            db.execute(
                "CREATE TABLE events(session TEXT,seq INT,ts REAL,type TEXT,payload TEXT)"
            )
            db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?)",
                (
                    "public-session",
                    1,
                    time.time() + 1,
                    "session_started",
                    json.dumps(
                        {"mode": "public", "repo_id": {"first_commit": "a" * 40}}
                    ),
                ),
            )
        self.assertEqual(
            audit_database(self.store.path, allowlist=ALLOW).status, "FAIL"
        )


if __name__ == "__main__":
    unittest.main()
