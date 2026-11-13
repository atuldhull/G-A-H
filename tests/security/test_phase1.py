"""Approval/consent invariants using trusted fixtures and a fake console."""

import io
import os
import re
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from crocodile.security import Action, ApprovalSession, Decision, approvals, cmd
from crocodile.security.binding import bind
from crocodile.security.consent import discover
from crocodile.security.surfaces import changes_execution


def confirm(preview):
    match = re.search(r"Type ((?:tests|apply|run) \d{2}) to approve:", preview)
    return match[1] if match else "y"


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.session = ApprovalSession(self.root)
        self.edit = Action(
            "write", diff="-x = 0\n+x = 1", paths=["module.py"], replacements=["x = 1"]
        )
        self.shell = Action(
            "shell", argv=[sys.executable, "-I", "-c", "print('fixture')"]
        )
        # Trusted fixture for the owner-built test argv; never executed as pytest.
        self.test = Action(
            "test_consent",
            argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        )

    def allow(self, action):
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            decision = approvals.ask(action, session=self.session)
        self.assertEqual(decision.verdict, "allow", decision.reasons)
        return decision

    def test_policy_levels_and_hard_denials(self):
        cases = [
            (self.edit, "ask", "green"),
            (replace(self.edit, paths=[f"m{i}.py" for i in range(4)]), "ask", "amber"),
            (replace(self.edit, replacements=["import subprocess"]), "ask", "amber"),
            (replace(self.edit, paths=["tests/test_x.py"]), "ask", "red"),
            (replace(self.edit, source="README.md:40"), "ask", "red"),
            (replace(self.edit, paths=[".git/config"]), "deny", None),
            (replace(self.edit, paths=["../escape.py"]), "deny", None),
            (self.shell, "ask", "amber"),
            (self.test, "ask", "red"),
            (Action("unknown"), "deny", None),
            (replace(self.shell, argv="echo fixture"), "deny", None),
        ]
        for action, verdict, level in cases:
            with self.subTest(action=action):
                decision = approvals.decide(action, session=self.session)
                self.assertEqual((decision.verdict, decision.level), (verdict, level))

    def test_confidential_and_provenance_network_denials(self):
        network = replace(self.shell, argv=[sys.executable, "https://example.invalid"])
        self.assertEqual(
            approvals.decide(
                replace(network, source="README.md:40"), session=self.session
            ).verdict,
            "deny",
        )
        self.session.mode = "confidential"
        self.assertEqual(
            approvals.decide(network, session=self.session).verdict, "deny"
        )
        self.assertEqual(
            approvals.decide(self.shell, session=self.session).level, "red"
        )
        with patch.object(approvals, "_console_answer", return_value="n") as reader:
            approvals.ask(self.shell, session=self.session)
        self.assertIn(
            "network is not blocked for child processes", reader.call_args.args[0]
        )

    def test_green_and_amber_default_deny(self):
        for action in (self.edit, self.shell):
            for answer in ("", "n", "maybe"):
                with (
                    self.subTest(action=action, answer=answer),
                    patch.object(approvals, "_console_answer", return_value=answer),
                ):
                    self.assertEqual(
                        approvals.ask(action, session=self.session).verdict, "deny"
                    )

    def test_red_requires_current_word_and_nonce(self):
        action = replace(self.edit, source="README.md:40")
        for answer in ("y", "yes", "apply", "run 47", "apply 48", "APPLY 47"):
            with (
                self.subTest(answer=answer),
                patch.object(approvals.secrets, "randbelow", return_value=47),
                patch.object(approvals, "_console_answer", return_value=answer),
            ):
                self.assertEqual(
                    approvals.ask(action, session=self.session).verdict, "deny"
                )
        decision = self.allow(action)
        self.assertEqual(decision.level, "red")

    def test_no_console_and_piped_stdin_cannot_approve(self):
        with (
            patch.object(
                approvals, "_console_answer", side_effect=OSError("no console")
            ),
            patch.object(sys, "stdin", io.StringIO("yes\n")),
        ):
            self.assertEqual(
                approvals.ask(self.edit, session=self.session).verdict, "deny"
            )

    @unittest.skipUnless(os.name == "nt", "Windows console backend")
    def test_windows_drains_pending_keys_before_prompt(self):
        import msvcrt

        reader, writer = Mock(), Mock()
        reader.readline.return_value = "y\n"
        reader.__enter__ = Mock(return_value=reader)
        reader.__exit__ = Mock(return_value=False)
        writer.__enter__ = Mock(return_value=writer)
        writer.__exit__ = Mock(return_value=False)
        order = []
        with (
            patch("builtins.open", side_effect=[reader, writer]) as opened,
            patch.object(msvcrt, "kbhit", side_effect=[True, True, False]),
            patch.object(msvcrt, "getwch", side_effect=lambda: order.append("drain")),
        ):
            writer.write.side_effect = lambda _: order.append("prompt")
            self.assertEqual(approvals._console_answer("trusted prompt"), "y\n")
        self.assertEqual(order, ["drain", "drain", "prompt"])
        self.assertEqual(opened.call_args_list[0].args[0], "CONIN$")

    def test_escape_and_omitted_count(self):
        raw = "\x1b]0;spoof\x07\r\u202e\u200b\0"
        shown = approvals.escape(raw)
        for value in ("\x1b", "\x07", "\r", "\u202e", "\u200b", "\0"):
            self.assertNotIn(value, shown)
        self.assertIn("\\u202e", shown)
        self.assertEqual(approvals.escape("abcdef", 3), "abc [+3 chars omitted]")

    def test_single_use_and_cross_session_denial(self):
        decision = self.allow(self.edit)
        other = ApprovalSession(self.root)
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(self.edit, decision, session=other)
        bound = approvals.validate_before_execution(
            self.edit, decision, session=self.session
        )
        self.assertEqual(bound.paths, (str(self.root / "module.py"),))
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(
                self.edit, decision, session=self.session
            )
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(
                self.edit, Decision("allow", token="invented"), session=self.session
            )

    def test_diff_paths_preimage_cwd_and_argv_are_bound(self):
        (self.root / "subdir").mkdir()
        mutations = [
            (self.edit, replace(self.edit, diff="different")),
            (self.edit, replace(self.edit, paths=["other.py"])),
            (self.shell, replace(self.shell, cwd="subdir")),
            (self.shell, replace(self.shell, argv=[sys.executable, "-V"])),
        ]
        for original, changed in mutations:
            decision = self.allow(original)
            with (
                self.subTest(changed=changed),
                self.assertRaises(approvals.ApprovalChanged),
            ):
                approvals.validate_before_execution(
                    changed, decision, session=self.session
                )
        decision = self.allow(self.edit)
        (self.root / "module.py").write_text("user edit", encoding="utf-8")
        with self.assertRaises(approvals.ApprovalChanged):
            approvals.validate_before_execution(
                self.edit, decision, session=self.session
            )

    def test_changed_while_prompting_denies(self):
        def change(_):
            (self.root / "module.py").write_text("changed", encoding="utf-8")
            return "y"

        with patch.object(approvals, "_console_answer", side_effect=change):
            self.assertEqual(
                approvals.ask(self.edit, session=self.session).verdict, "deny"
            )

    def test_executable_metadata_is_bound(self):
        decision = self.allow(self.shell)
        actual = Path.stat

        def changed(path, *args, **kwargs):
            stat = actual(path, *args, **kwargs)
            if str(path) == str(Path(sys.executable).resolve()):
                values = list(stat)
                values[6] += 1
                return os.stat_result(values)
            return stat

        with (
            patch.object(Path, "stat", changed),
            self.assertRaises(approvals.ApprovalChanged),
        ):
            approvals.validate_before_execution(
                self.shell, decision, session=self.session
            )

    def test_consent_inventory_is_static_and_shown(self):
        marker = self.root / "executed"
        (self.root / "conftest.py").write_text(
            f"open({str(marker)!r}, 'w').write('bad')\npytest_plugins = ['fixture_plugin']",
            encoding="utf-8",
        )
        (self.root / "pytest.ini").write_text(
            "[pytest]\naddopts = -x", encoding="utf-8"
        )
        with patch.object(approvals, "_console_answer", side_effect=confirm) as reader:
            decision = approvals.ask(self.test, session=self.session)
        self.assertEqual(decision.verdict, "allow", decision.reasons)
        preview = reader.call_args.args[0]
        for value in (
            "THIS EXECUTES CODE FROM THE REPO",
            "conftest.py",
            "sha256=",
            "addopts",
            "pytest_plugins",
            "no:cacheprovider",
            "interpreter/executable",
        ):
            self.assertIn(value, preview)
        self.assertFalse(marker.exists())

    def test_consent_reuse_and_journaling(self):
        self.allow(self.test)
        with patch.object(approvals, "_console_answer") as reader:
            decision = approvals.ask(self.test, session=self.session)
        reader.assert_not_called()
        self.assertEqual(decision.verdict, "allow")
        self.assertEqual(self.session.events[-1]["by"], "consent")
        approvals.validate_before_execution(self.test, decision, session=self.session)

    def test_config_changes_additions_removals_reprompt(self):
        config = self.root / "pytest.ini"
        config.write_text("[pytest]", encoding="utf-8")
        for mutation in (
            lambda: config.write_text("[pytest]\naddopts=-x", encoding="utf-8"),
            lambda: (self.root / "conftest.py").write_text("# added", encoding="utf-8"),
            config.unlink,
        ):
            self.allow(self.test)
            mutation()
            with patch.object(approvals, "_console_answer", return_value="n") as reader:
                self.assertEqual(
                    approvals.ask(self.test, session=self.session).verdict, "deny"
                )
            reader.assert_called_once()

    def test_changed_argv_and_steered_test_never_reuse_consent(self):
        for changed in (
            replace(self.test, argv=[*self.test.argv, "-x"]),
            replace(self.test, source="README.md:40"),
        ):
            self.allow(self.test)
            with patch.object(approvals, "_console_answer", return_value="n") as reader:
                self.assertEqual(
                    approvals.ask(changed, session=self.session).verdict, "deny"
                )
            reader.assert_called_once()
            self.assertIsNone(self.session._consent)

    def test_edit_invalidation_and_fresh_red_panel(self):
        self.allow(self.test)
        self.session.record_edit(["x = 2"])
        with patch.object(approvals, "_console_answer") as reader:
            approvals.ask(self.test, session=self.session)
        reader.assert_not_called()
        self.session.record_edit(["import subprocess\nsubprocess.run(['fixture'])"])
        with patch.object(approvals, "_console_answer", return_value="y") as reader:
            decision = approvals.ask(self.test, session=self.session)
        self.assertEqual(decision.verdict, "deny")
        self.assertIn("will execute edited code", reader.call_args.args[0])
        self.assertIn("Type tests ", reader.call_args.args[0])

    def test_config_change_after_consent_prevents_spawn(self):
        decision = self.allow(self.test)
        (self.root / "conftest.py").write_text("# changed", encoding="utf-8")
        with (
            patch.object(cmd.subprocess, "run") as spawn,
            self.assertRaises(approvals.ApprovalChanged),
        ):
            cmd.run(
                self.test.argv,
                self.root,
                timeout=1,
                session=self.session,
                action=self.test,
                decision=decision,
            )
        spawn.assert_not_called()

    def test_denial_prevents_command_execution(self):
        with (
            patch.object(approvals, "_console_answer", return_value="n"),
            patch.object(cmd.subprocess, "run") as spawn,
            self.assertRaises(approvals.ApprovalDenied),
        ):
            cmd.run(self.shell.argv, self.root, timeout=1, session=self.session)
        spawn.assert_not_called()

    def test_test_environment_and_resolved_execution(self):
        decision = self.allow(self.test)
        with (
            patch.dict(
                os.environ, {"PYTEST_ADDOPTS": "--bad", "PYTEST_PLUGINS": "bad"}
            ),
            patch.object(cmd.subprocess, "run") as spawn,
        ):
            spawn.return_value = Mock(returncode=0, stdout="", stderr="")
            cmd.run(
                self.test.argv,
                self.root,
                timeout=1,
                session=self.session,
                action=self.test,
                decision=decision,
            )
        self.assertEqual(
            spawn.call_args.args[0][0], str(Path(sys.executable).resolve())
        )
        env = spawn.call_args.kwargs["env"]
        self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertNotIn("PYTEST_ADDOPTS", env)
        self.assertNotIn("PYTEST_PLUGINS", env)

    def test_yes_green_never_allows_test_execution(self):
        self.session.yes_green = True
        with patch.object(approvals, "_console_answer") as reader:
            self.assertEqual(
                approvals.ask(self.test, session=self.session).verdict, "deny"
            )
        reader.assert_not_called()

    def test_scanner_cap_and_errors_fail_closed(self):
        (self.root / "conftest.py").write_text("# fixture", encoding="utf-8")
        with self.assertRaises(ValueError):
            discover(self.root, self.root, cap=0)
        with patch(
            "crocodile.security.binding.discover", side_effect=OSError("unreadable")
        ):
            self.assertEqual(
                approvals.ask(self.test, session=self.session).verdict, "deny"
            )

    def test_ast_execution_surfaces(self):
        for text in (
            "import subprocess as sp",
            "from os import system as launch\nlaunch('x')",
            "os.spawnv(1, 'x', [])",
            "eval('x')",
            "pickle.loads(data)",
            "shutil.rmtree('x')",
            "import requests",
            "if incomplete:",
        ):
            with self.subTest(text=text):
                self.assertTrue(changes_execution(text))
        self.assertFalse(changes_execution("x = 1\n# subprocess.run is just a comment"))

    def test_snapshot_does_not_execute_any_code(self):
        self.assertEqual(
            bind(self.shell, self.session).argv[0], str(Path(sys.executable).resolve())
        )

    def test_collection_outside_inventory_and_config_overrides_deny(self):
        for suffix in (
            [".."],
            [".venv"],
            ["../outside/test_x.py"],
            [".venv/tests/test_x.py"],
            ["--pyargs", "package"],
            ["-c", "other.ini"],
            ["@args.txt"],
        ):
            action = replace(self.test, argv=[*self.test.argv, *suffix])
            with (
                self.subTest(suffix=suffix),
                patch.object(approvals, "_console_answer") as reader,
            ):
                self.assertEqual(
                    approvals.ask(action, session=self.session).verdict, "deny"
                )
                reader.assert_not_called()

    def test_config_addopts_cannot_hide_external_configuration(self):
        config = self.root / "pytest.ini"
        for options in ("-c /tmp/other.ini", "'--pyargs' package", "../outside"):
            config.write_text("[pytest]\naddopts=" + options, encoding="utf-8")
            with self.subTest(options=options):
                self.assertEqual(
                    approvals.decide(self.test, session=self.session).verdict, "deny"
                )

    def test_toml_config_hash_changes_invalidate_consent(self):
        config = self.root / "pytest.toml"
        config.write_text('[pytest]\naddopts = ["-x"]', encoding="utf-8")
        self.allow(self.test)
        config.write_text('[pytest]\naddopts = ["-v"]', encoding="utf-8")
        with patch.object(approvals, "_console_answer", return_value="n") as reader:
            self.assertEqual(
                approvals.ask(self.test, session=self.session).verdict, "deny"
            )
        reader.assert_called_once()

    def test_new_consent_request_revokes_old_pending_permit(self):
        old = self.allow(self.test)
        changed = replace(self.test, argv=[*self.test.argv, "-x"])
        with patch.object(approvals, "_console_answer", return_value="n"):
            approvals.ask(changed, session=self.session)
        with self.assertRaises(approvals.ApprovalDenied):
            approvals.validate_before_execution(self.test, old, session=self.session)

    def test_repo_executable_is_denied(self):
        planted = self.root / "python.exe"
        planted.write_bytes(b"fixture only")
        action = replace(self.shell, argv=[str(planted)])
        with patch.object(approvals, "_console_answer") as reader:
            self.assertEqual(
                approvals.ask(action, session=self.session).verdict, "deny"
            )
        reader.assert_not_called()

    def test_existing_call_alias_is_conservatively_an_execution_surface(self):
        self.assertTrue(changes_execution("launch('fixture')"))
        self.assertTrue(changes_execution("sp.run(['fixture'])"))
        self.assertFalse(changes_execution("count = len([1, 2])"))
        self.assertTrue(changes_execution("pytest_plugins = ['new_plugin']"))

    def test_configured_collection_paths_stay_inside_inventory(self):
        config = self.root / "pytest.ini"
        for value in ("../outside", ".venv/tests", "'../outside'"):
            config.write_text("[pytest]\ntestpaths = " + value, encoding="utf-8")
            with self.subTest(value=value):
                self.assertEqual(
                    approvals.decide(self.test, session=self.session).verdict, "deny"
                )
        config.write_text("[pytest]\ntestpaths = tests", encoding="utf-8")
        self.assertEqual(
            approvals.decide(self.test, session=self.session).verdict, "ask"
        )

    def test_relative_cwd_command_uses_resolved_approved_directory(self):
        with (
            patch.object(approvals, "_console_answer", return_value="y"),
            patch.object(cmd.subprocess, "run") as spawn,
        ):
            spawn.return_value = Mock(returncode=0, stdout="", stderr="")
            cmd.run([sys.executable, "-V"], ".", timeout=1)
        self.assertEqual(spawn.call_args.kwargs["cwd"], str(Path.cwd().resolve()))


if __name__ == "__main__":
    unittest.main()
