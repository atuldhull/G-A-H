"""Trusted Phase 0 fixtures; no repo code is passed to the child interpreter."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crocodile.security import Action, CmdResult, Decision, approvals, cmd, confidential


class Phase0Tests(unittest.TestCase):
    def test_console_confirmation(self):
        for answer, verdict in (
            ("y\n", "allow"),
            ("yes\n", "allow"),
            ("n\n", "deny"),
            ("\n", "deny"),
            ("maybe", "deny"),
        ):
            with self.subTest(answer=answer):
                with patch.object(approvals, "_console_answer", return_value=answer):
                    result = approvals.ask(Action("write", diff="trusted fixture"))
                self.assertIsInstance(result, Decision)
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(bool(result), verdict == "allow")

    def test_no_console_denies(self):
        with patch.object(approvals, "_console_answer", side_effect=OSError):
            self.assertEqual(
                approvals.ask(Action("shell", argv=["fixture"])).verdict, "deny"
            )

    def test_preview_does_not_render_controls(self):
        with patch.object(approvals, "_console_answer", return_value="n") as reader:
            approvals.ask(Action("git", argv=["\x1b[2J"], source="README.md:40"))
        preview = reader.call_args.args[0]
        self.assertNotIn("\x1b", preview)
        self.assertIn("README.md:40", preview)

    def test_unknown_action_denies_without_console(self):
        with patch.object(approvals, "_console_answer") as reader:
            result = approvals.ask(Action("unknown"))
        self.assertEqual(result.verdict, "deny")
        reader.assert_not_called()

    def test_command_smoke_preserves_arguments_cwd_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            argument = "literal & | $() ; spaces"
            result = cmd.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        "import os,sys; print(os.getcwd()); print(sys.argv[1]); "
                        "print('fixture error', file=sys.stderr); sys.exit(7)"
                    ),
                    argument,
                ],
                directory,
                timeout=10,
            )
            self.assertIsInstance(result, CmdResult)
            self.assertEqual(result.returncode, 7)
            lines = result.stdout.splitlines()
            self.assertEqual(Path(lines[0]).resolve(), Path(directory).resolve())
            self.assertEqual(lines[1], argument)
            self.assertEqual(result.stderr.strip(), "fixture error")

    def test_command_stdin_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = cmd.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import sys; print(repr(sys.stdin.read()))",
                ],
                directory,
                timeout=10,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "''")

    def test_command_timeout_propagates(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            cmd.run(
                [sys.executable, "-I", "-c", "import time; time.sleep(5)"],
                directory,
                timeout=0.1,
            )

    def test_command_spawn_error_propagates(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(OSError):
            cmd.run([str(Path(directory) / "missing-executable")], directory, timeout=1)

    def test_reject_command_strings_and_invalid_timeouts(self):
        with self.assertRaises(TypeError):
            cmd.run("echo fixture", ".", timeout=1)
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                cmd.run([sys.executable], ".", timeout=timeout)

    def test_public_mode_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(confidential.mode_for(directory), "public")
            self.assertEqual(confidential.mode_for(Path(directory)), "public")


if __name__ == "__main__":
    unittest.main()
