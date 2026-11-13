"""Harmless path, executable, environment, process-tree and Git fixtures."""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from crocodile.security import Action, ApprovalSession, approvals, cmd, procs
from crocodile.security.executables import resolve_exe, resolve_pinned, safe_path
from crocodile.security.git import Git, GitDenied
from crocodile.security.paths import atomic_write, resolve_in_repo


def confirm(prompt):
    import re

    match = re.search(r"Type ((?:run|apply|tests) \d{2}) to approve", prompt)
    return match[1] if match else "y"


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup_fixture)
        self.root = Path(self.temp.name).resolve()
        self.session = ApprovalSession(self.root)

    def cleanup_fixture(self):
        # Windows can briefly retain directory handles after process termination.
        # Retry only sharing violations, with a deadline; never hide a live child.
        deadline = time.monotonic() + 2
        while True:
            try:
                self.temp.cleanup()
                return
            except PermissionError as error:
                if (
                    os.name != "nt"
                    or error.winerror != 32
                    or time.monotonic() >= deadline
                ):
                    raise
                time.sleep(0.05)

    def command(self, script, timeout=10):
        with patch.object(approvals, "_console_answer", side_effect=confirm):
            return cmd.run(
                [sys.executable, "-I", "-c", script],
                self.root,
                timeout=timeout,
                session=self.session,
            )

    def test_windows_device_unc_ads_and_protected_aliases(self):
        for raw in (
            "../outside",
            ".git/config",
            ".git./config",
            ".env",
            ".vscode/settings.json",
            "nested/mcp.json",
            "file:stream",
            "con.txt",
            "NUL",
            "CONIN$",
            "CONOUT$",
            "COM1.log",
            "\\\\server\\share\\file",
            "\\\\?\\C:\\file",
            "\\\\.\\NUL",
            "C:relative",
            "bad\0path",
        ):
            with self.subTest(raw=raw), self.assertRaises((ValueError, OSError)):
                resolve_in_repo(raw, self.root, for_write=True)

    def test_normal_path_and_atomic_replacement(self):
        target = self.root / "module.txt"
        target.write_bytes(b"old")
        atomic_write("module.txt", b"new", root=self.root)
        self.assertEqual(target.read_bytes(), b"new")
        self.assertEqual(resolve_in_repo("module.txt", self.root), target)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["module.txt"])

    @unittest.skipUnless(os.name == "nt", "Windows trailing-name normalization")
    def test_windows_trailing_dots_spaces_and_short_names(self):
        target = self.root / "ordinary.txt"
        target.write_text("fixture", encoding="utf-8")
        self.assertEqual(resolve_in_repo("ordinary.txt. ", self.root), target)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetShortPathNameW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
        ]
        kernel.GetShortPathNameW.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetShortPathNameW(str(target), buffer, len(buffer))
        self.assertTrue(length)
        self.assertEqual(resolve_in_repo(buffer.value, self.root), target)

    def test_hard_link_write_is_refused(self):
        target = self.root / "original.txt"
        target.write_bytes(b"unchanged")
        os.link(target, self.root / "alias.txt")
        with self.assertRaises(ValueError):
            atomic_write("alias.txt", b"bad", root=self.root)
        self.assertEqual(target.read_bytes(), b"unchanged")

    def test_symlink_escape_and_protected_target(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        try:
            (self.root / "escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest(
                "symlink privilege unavailable; junction covered separately on Windows"
            )
        with self.assertRaises(ValueError):
            resolve_in_repo("escape/file.txt", self.root, for_write=True)
        metadata = self.root / ".git"
        metadata.mkdir()
        (self.root / "alias").symlink_to(metadata, target_is_directory=True)
        with self.assertRaises(ValueError):
            resolve_in_repo("alias/config", self.root, for_write=True)

    @unittest.skipUnless(os.name == "nt", "Windows junction")
    def test_junction_to_metadata_is_refused(self):
        metadata = self.root / ".git"
        metadata.mkdir()
        junction = self.root / "junction"
        # Trusted fixture only: fixed cmd.exe, paths generated by TemporaryDirectory.
        shell = str(Path(os.environ["SYSTEMROOT"], "System32", "cmd.exe"))
        result = subprocess.run(
            [shell, "/c", "mklink", "/J", str(junction), str(metadata)],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            self.skipTest("junction creation unavailable")
        self.addCleanup(junction.rmdir)
        with self.assertRaises(ValueError):
            resolve_in_repo("junction/config", self.root, for_write=True)

    def test_public_confidential_subtree_denies_paths(self):
        marker = self.root / "private" / ".crocodile"
        marker.mkdir(parents=True)
        (marker / "confidential").touch()
        with self.assertRaises(ValueError):
            resolve_in_repo("private/data.txt", self.root)
        self.assertEqual(
            resolve_in_repo("private/data.txt", self.root, mode="confidential"),
            self.root / "private/data.txt",
        )

    def test_binding_uses_shared_path_guard(self):
        action = Action(
            "write", diff="fixture", paths=[".git./config"], replacements=["x = 1"]
        )
        self.assertEqual(approvals.ask(action, session=self.session).verdict, "deny")
        with (
            patch.object(procs, "run") as spawn,
            self.assertRaises(approvals.ApprovalDenied),
        ):
            cmd.run(
                [sys.executable, "-V"],
                self.root.parent,
                timeout=1,
                session=self.session,
            )
        spawn.assert_not_called()

    def test_executable_search_excludes_repo_cwd_and_relative_path_entries(self):
        (self.root / "git.exe").write_bytes(b"not executable fixture")
        original = os.environ.get("PATH", "")
        with patch.dict(
            os.environ,
            {"PATH": os.pathsep.join((".", str(self.root), "relative", original))},
        ):
            directories = safe_path(self.root, self.root)
            self.assertNotIn(self.root, directories)
            self.assertTrue(all(path.is_absolute() for path in directories))
            git = resolve_exe("git", self.root, self.root)
            self.assertFalse(git.is_relative_to(self.root))

    def test_session_pin_ignores_later_path_changes(self):
        pin = self.session._exe_pins["python"]
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            self.assertEqual(
                resolve_pinned("python", self.root, self.root, self.session._exe_pins),
                pin.path,
            )

    def test_generic_git_and_self_invocation_are_refused(self):
        for argv in (
            ["git", "status"],
            [sys.executable, "-m", "crocodile", "init", "--public"],
        ):
            with self.subTest(argv=argv), self.assertRaises(approvals.ApprovalDenied):
                cmd.run(argv, self.root, timeout=1, session=self.session)

    def test_batch_metacharacters_are_denied_before_prompt(self):
        batch = self.root.parent / (self.root.name + ".cmd")
        batch.write_text("@echo harmless", encoding="utf-8")
        self.addCleanup(batch.unlink)
        for value in ("x&y", "x|y", "%PATH%", '"quoted"', "line\nnext"):
            action = Action("shell", argv=[str(batch), value])
            with (
                self.subTest(value=value),
                patch.object(approvals, "_console_answer") as console,
            ):
                self.assertEqual(
                    approvals.ask(action, session=self.session).verdict, "deny"
                )
                console.assert_not_called()

    def test_restricted_child_environment_and_scratch_profiles(self):
        values = {
            "OPENAI_API_KEY": "fixture",
            "BF_VK_PUBLIC": "fixture",
            "MY_SECRET": "fixture",
            "HTTP_PROXY": "fixture",
            "PYTHONPATH": "fixture",
            "GIT_CONFIG_COUNT": "99",
            "PYTEST_ADDOPTS": "--bad",
            "PYTEST_PLUGINS": "bad",
        }
        with patch.dict(os.environ, values):
            result = self.command("import os,json; print(json.dumps(dict(os.environ)))")
        env = json.loads(result.stdout)
        for name in values:
            self.assertNotIn(name, env)
        self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(
            {key.upper(): value for key, value in env.items()}[
                "NODEFAULTCURRENTDIRECTORYINEXEPATH"
            ],
            "1",
        )
        profiles = [
            env[key]
            for key in (
                "APPDATA",
                "LOCALAPPDATA",
                "USERPROFILE",
                "HOMEPATH",
                "TEMP",
                "TMP",
            )
        ]
        self.assertEqual(len(set(profiles)), 1)
        self.assertFalse(Path(profiles[0]).exists())

    def test_timeout_cleans_child(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.command("import time; time.sleep(10)", timeout=0.1)

    @unittest.skipUnless(os.name == "nt", "Windows job object process-tree proof")
    def test_job_kills_descendants_on_parent_exit_and_timeout(self):
        from ctypes import wintypes as w

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = (
            [w.DWORD, w.BOOL, w.DWORD],
            w.HANDLE,
        )
        kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = (
            [w.HANDLE, w.DWORD],
            w.DWORD,
        )
        kernel.CloseHandle.argtypes = [w.HANDLE]
        for timeout in (None, 10):
            pidfile = self.root / "descendant.pid"
            script = (
                "import subprocess,sys,pathlib,time; child=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(60)']); pathlib.Path('descendant.pid').write_text(str(child.pid)); "
                + ("time.sleep(60)" if timeout else "time.sleep(0.2)")
            )
            if timeout:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.command(script, timeout=timeout)
            else:
                self.assertEqual(self.command(script).returncode, 0)
            pid = int(pidfile.read_text())
            handle = kernel.OpenProcess(0x100000, False, pid)
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                finally:
                    kernel.CloseHandle(handle)
            pidfile.unlink()

    def fixture_git(self, *arguments):
        git = str(self.session._exe_pins["git"].path)
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
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=" + str(self.root / "empty-hooks"),
                *arguments,
            ],
            self.root,
            root=self.root,
            timeout=20,
            git_env=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def make_repo(self):
        self.fixture_git("init", "--initial-branch=main")
        self.fixture_git("config", "user.name", "Fixture")
        self.fixture_git("config", "user.email", "fixture@example.invalid")
        (self.root / "module.txt").write_text("fixture\n", encoding="utf-8")
        self.fixture_git("add", "--", "module.txt")
        self.fixture_git("commit", "-m", "fixture")

    def test_git_fixed_reads_and_sha_resolution(self):
        self.make_repo()
        with Git(self.session) as git:
            sha = git.validate_rev("HEAD")
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            for template in ("status", "log", "show", "diff"):
                result = git.run(template, rev="HEAD", paths=["module.txt"], count=1)
                self.assertEqual(result.returncode, 0, result.stderr)
                if template != "status":
                    self.assertIn(sha, result.argv)
                self.assertIn("--", result.argv)
            self.assertTrue(
                any(
                    event["event"] == "git_config_audited"
                    for event in self.session.events
                )
            )

    def test_git_rejects_options_revs_and_counts(self):
        self.make_repo()
        with Git(self.session) as git:
            for revision in (
                "--output=.git/config",
                "-c",
                "HEAD\nwhoami",
                "not-a-revision",
            ):
                with self.subTest(revision=revision), self.assertRaises(GitDenied):
                    git.validate_rev(revision)
            for count in (0, 201, True):
                with self.subTest(count=count), self.assertRaises(GitDenied):
                    git.run("log", count=count)
            with self.assertRaises(GitDenied):
                git.run("show", paths=["--output=.git/config"])

    def test_git_changed_config_disables_free_reads_without_running_helper(self):
        self.make_repo()
        marker = self.root / "helper-ran"
        with Git(self.session) as git:
            git.run("status")
            with (self.root / ".git" / "config").open("a", encoding="utf-8") as stream:
                stream.write('\n[core]\nfsmonitor = "echo fixture > helper-ran"\n')
            with self.assertRaisesRegex(GitDenied, "core.fsmonitor"):
                git.run("status")
            self.assertFalse(marker.exists())
            self.assertTrue(self.session._git_disabled)
            with self.assertRaises(GitDenied):
                git.run("log")

    def test_git_new_attributes_reaudited_and_filters_disabled(self):
        self.make_repo()
        with Git(self.session) as git:
            git.run("status")
            (self.root / ".gitattributes").write_text(
                "*.txt filter=fixture\n", encoding="utf-8"
            )
            result = git.run("diff")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("filter.fixture.process=", result.argv)
            self.assertIn("filter.fixture.required=false", result.argv)
            self.assertEqual(
                sum(e["event"] == "git_config_audited" for e in self.session.events), 2
            )

    def test_git_includes_and_filter_commands_are_not_allowed(self):
        self.make_repo()
        config = self.root / ".git" / "config"
        original = config.read_text()
        for suffix in (
            "\n[include]\npath = ../outside-config\n",
            '\n[filter "fixture"]\nclean = echo fixture\n',
        ):
            config.write_text(original + suffix, encoding="utf-8")
            self.session = ApprovalSession(self.root)
            with Git(self.session) as git, self.assertRaises(GitDenied):
                git.run("status")

    def test_git_mutation_denial_and_empty_hooks(self):
        self.make_repo()
        marker = self.root / "hook-ran"
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho fixture > hook-ran\n", encoding="utf-8")
        hook.chmod(0o755)
        (self.root / "module.txt").write_text("changed\n", encoding="utf-8")
        self.fixture_git("add", "--", "module.txt")
        with Git(self.session) as git:
            with (
                patch.object(approvals, "_console_answer", return_value="n"),
                self.assertRaises(approvals.ApprovalDenied),
            ):
                git.run("commit", message="denied fixture")
            with patch.object(approvals, "_console_answer", side_effect=confirm):
                result = git.run("commit", message="approved fixture")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())

    def test_confidential_push_is_denied(self):
        self.make_repo()
        self.session.mode = "confidential"
        with Git(self.session) as git, self.assertRaises(GitDenied):
            git.run("push", branch="fixture")

    @unittest.skipUnless(os.name == "nt", "Windows suspended child fail-closed proof")
    def test_job_assignment_failure_never_runs_child_code(self):
        from crocodile.security.windows_job import Job

        with (
            patch.object(
                Job,
                "attach_and_resume",
                side_effect=OSError("fixture assignment failure"),
            ),
            self.assertRaises(OSError),
        ):
            self.command("from pathlib import Path; Path('must-not-run').touch()")
        self.assertFalse((self.root / "must-not-run").exists())

    def test_git_metadata_change_during_prompt_prevents_mutation(self):
        self.make_repo()
        (self.root / "module.txt").write_text("staged fixture", encoding="utf-8")
        self.fixture_git("add", "--", "module.txt")
        with Git(self.session) as git:
            before = git.validate_rev("HEAD")

            def change(prompt):
                (self.root / ".gitattributes").write_text(
                    "*.txt filter=fixture", encoding="utf-8"
                )
                return confirm(prompt)

            with (
                patch.object(approvals, "_console_answer", side_effect=change),
                self.assertRaisesRegex(GitDenied, "changed before execution"),
            ):
                git.run("commit", message="must not commit")
            self.assertEqual(git.validate_rev("HEAD"), before)


if __name__ == "__main__":
    unittest.main()
