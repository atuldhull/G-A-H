"""Trusted disposable bench mode keeps approvals and hardened execution bound."""

import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from crocodile.security import Action, ApprovalSession, approvals, cmd, procs
from crocodile.security.provenance import Source


class BenchSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "task"
        self.root.mkdir()
        self.events = []
        self.session = ApprovalSession.for_bench(
            self.root, parent=self.base, events=self.events, user_task="fix the task"
        )
        self.action = Action(
            "shell", argv=[sys.executable, "-I", "-c", "print('bench fixture')"]
        )

    def tearDown(self):
        if not self.session._bench_closed:
            self.session.close_bench()
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

    def test_normal_session_still_requires_console(self):
        normal = ApprovalSession(self.root)
        with patch.object(approvals, "_console_answer", return_value="n") as console:
            decision = approvals.ask(self.action, session=normal)
        self.assertEqual(decision.verdict, "deny")
        console.assert_called_once()
        self.assertFalse(normal.bench_auto)

    def test_factory_refuses_populated_repo_or_wrong_parent(self):
        with self.assertRaises(ValueError):
            ApprovalSession.for_bench(self.root, parent=self.root)
        (self.root / "source.py").write_text("print('existing source')\n")
        with self.assertRaises(ValueError):
            ApprovalSession.for_bench(self.root, parent=self.base)
        self.assertTrue((self.root / "source.py").exists())

    def test_hardened_command_runs_without_console_and_logs_bench(self):
        script = "import os; print(os.environ.get('BENCH_FIXTURE_SECRET', 'absent')); print(os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'])"
        with (
            patch.dict(os.environ, {"BENCH_FIXTURE_SECRET": "synthetic-only"}),
            patch.object(approvals, "_console_answer") as console,
            patch.object(procs, "run", wraps=procs.run) as runner,
        ):
            result = cmd.run(
                [sys.executable, "-I", "-c", script],
                self.root,
                timeout=20,
                session=self.session,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ["absent", "1"])
        console.assert_not_called()
        runner.assert_called_once()
        self.assertTrue(callable(runner.call_args.kwargs["before_spawn"]))
        approved = [
            event
            for event in self.events
            if event["event"] == "approval" and event.get("approved")
        ]
        self.assertEqual(approved[-1]["by"], "bench")
        self.assertEqual(approved[-1]["argv"][0], str(Path(sys.executable).resolve()))
        self.assertEqual(len(approved[-1]["action_digest"]), 64)
        self.assertTrue(any(event["event"] == "approval_used" for event in self.events))

    def test_bench_permits_are_exact_single_use_and_session_bound(self):
        with patch.object(approvals, "_console_answer") as console:
            decision = approvals.ask(self.action, session=self.session)
            self.assertEqual(
                approvals.decide(self.action, session=self.session).verdict, "allow"
            )
        console.assert_not_called()
        normal = ApprovalSession(self.root)
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(self.action, decision, session=normal)
        approvals.validate_before_execution(self.action, decision, session=self.session)
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(
                self.action, decision, session=self.session
            )
        next_decision = approvals.ask(self.action, session=self.session)
        changed = replace(
            self.action, argv=[sys.executable, "-I", "-c", "print('changed')"]
        )
        with self.assertRaises(approvals.ApprovalChanged):
            approvals.validate_before_execution(
                changed, next_decision, session=self.session
            )

    def test_pytest_exact_argv_and_config_changes_invalidate_old_permits(self):
        action = Action(
            "test_consent",
            argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        )
        with patch.object(approvals, "_console_answer") as console:
            decision = approvals.ask(action, session=self.session)
            self.assertEqual((decision.verdict, decision.level), ("allow", "red"))
            (self.root / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
            with self.assertRaises(approvals.ApprovalChanged):
                approvals.validate_before_execution(
                    action, decision, session=self.session
                )
            fresh = approvals.ask(action, session=self.session)
            self.assertEqual(fresh.verdict, "allow")
            self.assertTrue(
                any(
                    item["path"].endswith("pytest.ini")
                    for item in self.events[-1]["config_hashes"]
                )
            )
            with self.assertRaises(approvals.ApprovalChanged):
                approvals.validate_before_execution(
                    replace(action, argv=[*action.argv, "-v"]),
                    fresh,
                    session=self.session,
                )
        console.assert_not_called()

    def test_edit_revocation_still_applies_in_bench_mode(self):
        decision = approvals.ask(self.action, session=self.session)
        self.session.record_edit(["import subprocess"])
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(
                self.action, decision, session=self.session
            )

    def test_local_steered_action_keeps_source_and_red_level_in_bench_event(self):
        self.session.provenance.add(
            "\n" * 39 + self.action.argv[-1], Source("file", "README.md", 1)
        )
        with patch.object(approvals, "_console_answer") as console:
            decision = approvals.ask(self.action, session=self.session)
        self.assertEqual((decision.verdict, decision.level), ("allow", "red"))
        self.assertEqual(decision.steered_by, ["README.md:40"])
        self.assertEqual(self.events[-1]["by"], "bench")
        self.assertEqual(self.events[-1]["steered_by"], ["README.md:40"])
        console.assert_not_called()

    def test_hard_denials_network_git_metadata_and_repo_exe_remain(self):
        exe = self.root / "planted.exe"
        exe.write_bytes(b"synthetic, never executed")
        cases = (
            Action(
                "write", paths=[".git/config"], diff="change", replacements=["change"]
            ),
            Action(
                "write", paths=["../outside"], diff="change", replacements=["change"]
            ),
            Action("network", url="https://example.invalid"),
            Action("shell", argv=[sys.executable, "https://example.invalid"]),
            Action("shell", argv=[str(exe)]),
            Action("git", argv=["git", "status"]),
        )
        with patch.object(approvals, "_console_answer") as console:
            for action in cases:
                with self.subTest(kind=action.kind, argv=action.argv):
                    self.assertEqual(
                        approvals.ask(action, session=self.session).verdict, "deny"
                    )
        console.assert_not_called()

    def test_confidential_promotion_refuses_auto_approval(self):
        self.session.mode = "confidential"
        with patch.object(approvals, "_console_answer") as console:
            self.assertEqual(
                approvals.ask(self.action, session=self.session).verdict, "deny"
            )
        console.assert_not_called()

    def test_replaced_root_aborts_instead_of_reusing_bench_authority(self):
        self.root.rename(self.base / "original")
        self.root.mkdir()
        with patch.object(approvals, "_console_answer") as console:
            self.assertEqual(
                approvals.ask(self.action, session=self.session).verdict, "deny"
            )
        console.assert_not_called()
        self.assertTrue(self.session._aborted)
        self.assertTrue(any(e["event"] == "integrity_violation" for e in self.events))

    def test_close_revokes_permits_without_falling_back_to_console(self):
        decision = approvals.ask(self.action, session=self.session)
        self.session.close_bench()
        self.assertFalse(self.session.bench_auto)
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(
                self.action, decision, session=self.session
            )
        with patch.object(approvals, "_console_answer") as console:
            self.assertEqual(
                approvals.ask(self.action, session=self.session).verdict, "deny"
            )
        console.assert_not_called()

    def test_bench_command_watch_still_aborts_on_metadata_tampering(self):
        (self.root / ".git").mkdir()
        config = self.root / ".git" / "config"
        config.write_text("before")
        script = "from pathlib import Path; Path('.git/config').write_text('tampered')"
        from crocodile.security.integrity import IntegrityViolation

        with (
            patch.object(approvals, "_console_answer") as console,
            self.assertRaises(IntegrityViolation),
        ):
            cmd.run(
                [sys.executable, "-I", "-c", script],
                self.root,
                timeout=20,
                session=self.session,
            )
        console.assert_not_called()
        self.assertTrue(self.session._aborted)


if __name__ == "__main__":
    unittest.main()
