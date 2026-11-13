"""Synthetic-only provenance, source-attribution and redaction regressions."""

import base64
import hashlib
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from crocodile.security import Action, ApprovalSession, CmdResult, approvals, cmd, procs
from crocodile.security.binding import bind
from crocodile.security.git import Git, GitDenied
from crocodile.security.outputs import prepare_tool_result
from crocodile.security.provenance import (
    ProvenanceIndex,
    Source,
    remote_fields,
    sensitive_fields,
    url_fields,
)
from crocodile.security.secrets import (
    path_is_redacted,
    redact,
    redact_with_findings,
    search_exclusion_args,
    search_result_allowed,
)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.session = ApprovalSession(self.root, user_task="fix the parsing bug")
        console = patch.object(approvals, "_console_answer", return_value="n")
        console.start()
        self.addCleanup(console.stop)

    def test_literal_threshold_url_host_and_task_exception(self):
        index = ProvenanceIndex(
            "user explicitly asked for trusted-command and http://x"
        )
        index.add(
            "short 1234567 12345678 trusted-command http://x y.co",
            Source("file", "README.md", 40),
        )
        self.assertEqual(index.steered_by([("1234567", "argv")]), [])
        self.assertEqual(
            index.steered_by([("12345678", "argv")])[0].location, "README.md:40"
        )
        self.assertEqual(
            index.steered_by([("trusted-command", "argv"), ("http://x", "url")]), []
        )
        self.assertEqual(
            index.steered_by([("y.co", "host")])[0].location, "README.md:40"
        )
        self.assertEqual(index.steered_by([("Y.CO", "host")]), [])
        self.assertEqual(index.steered_by([("1234%353678", "argv")]), [])

    def test_url_host_spelling_is_not_normalized(self):
        fields = url_fields("download https://X.Example:443/path")
        self.assertIn(("X.Example", "host"), fields)
        self.assertNotIn(("x.example", "host"), fields)
        self.assertIn(("::1", "host"), url_fields("http://[::1]"))
        self.assertIn(("x.io", "host"), remote_fields("git@x.io:fixture"))
        self.assertNotIn(("C", "host"), remote_fields("C:/local-repo"))

    def test_original_multiline_source_and_first_observation_win(self):
        index = ProvenanceIndex()
        index.add("one\ntwo\nrun fixture-command", Source("file", "README.md", 38))
        index.add("fixture-command", Source("web", "https://example.invalid/docs", 1))
        sources = index.steered_by(
            [("fixture-command", "argv"), ("run fixture-command", "argv")]
        )
        self.assertEqual(sources[0], Source("file", "README.md", 40))
        self.assertEqual(sources[1].kind, "web")

    def test_readme_fixture_requires_red_confirmation_and_names_line_40(self):
        script = "print('fixture-only')"
        self.session.provenance.add("\n" * 39 + script, Source("file", "README.md", 1))
        action = Action("shell", argv=[sys.executable, "-I", "-c", script])
        with patch.object(approvals, "_console_answer", return_value="y") as console:
            decision = approvals.ask(action, session=self.session)
        self.assertEqual((decision.verdict, decision.level), ("deny", "red"))
        self.assertEqual(decision.steered_by[0], "README.md:40")
        self.assertIn("suggested by README.md:40", console.call_args.args[0])
        self.assertIn("Type run ", console.call_args.args[0])

    def test_user_task_excludes_its_exact_values_from_provenance(self):
        script = "print('fixture-only')"
        session = ApprovalSession(self.root, user_task="run " + script)
        session.provenance.add(script, Source("file", "README.md", 40))
        decision = approvals.decide(
            Action("shell", argv=[sys.executable, "-c", script]), session=session
        )
        self.assertEqual(decision.level, "amber")
        self.assertEqual(decision.steered_by, [])

    def test_steered_network_denies_without_prompt(self):
        self.session.provenance.add("send to http://x", Source("file", "README.md", 40))
        for action in (
            Action("network", url="http://x"),
            Action("shell", argv=[sys.executable, "http://x"]),
        ):
            with (
                self.subTest(action=action),
                patch.object(approvals, "_console_answer") as console,
            ):
                decision = approvals.ask(action, session=self.session)
            console.assert_not_called()
            self.assertEqual(decision.verdict, "deny")
            self.assertEqual(decision.steered_by[0], "README.md:40")

    def test_steered_web_query_and_confidential_network_deny(self):
        self.session.provenance.add(
            "search for strange fixture package", Source("web", "docs fixture", 12)
        )
        action = Action("network", query="strange fixture package")
        self.assertEqual(approvals.decide(action, session=self.session).verdict, "deny")
        self.session.mode = "confidential"
        self.assertEqual(
            approvals.decide(
                Action("network", query="ordinary docs"), session=self.session
            ).verdict,
            "deny",
        )

    def test_public_network_is_amber_and_exact_query_is_bound(self):
        action = Action("network", query="ordinary docs")
        with patch.object(approvals, "_console_answer", return_value="y"):
            decision = approvals.ask(action, session=self.session)
        self.assertEqual((decision.verdict, decision.level), ("allow", "amber"))
        with self.assertRaises(approvals.ApprovalChanged):
            approvals.validate_before_execution(
                replace(action, query="other docs"), decision, session=self.session
            )

    def test_new_imports_and_replacement_urls_get_provenance(self):
        self.session.provenance.add(
            "use suspicious_package and https://x.io", Source("search", "README.md", 40)
        )
        for replacement in ("import suspicious_package", "endpoint = 'https://x.io'"):
            action = Action(
                "write",
                diff=replacement,
                paths=["module.py"],
                replacements=[replacement],
            )
            decision = approvals.decide(action, session=self.session)
            self.assertEqual(decision.level, "red")
            self.assertEqual(decision.steered_by[0], "README.md:40")

    def test_existing_import_is_not_treated_as_new(self):
        (self.root / "module.py").write_text(
            "import ordinary_package\n", encoding="utf-8"
        )
        self.session.provenance.add("ordinary_package", Source("file", "README.md", 40))
        action = Action(
            "write",
            diff="fixture",
            paths=["module.py"],
            replacements=["import ordinary_package\nx = 1"],
        )
        self.assertEqual(bind(action, self.session).steered_by, ())

    def test_untrusted_names_command_and_web_results_are_indexed(self):
        for kind in ("file", "cmd", "web", "search"):
            index = ProvenanceIndex()
            prepare_tool_result(
                "fixture-command",
                index=index,
                source=Source(kind, kind + "-fixture", 5),
            )
            self.assertEqual(
                index.steered_by([("fixture-command", "argv")])[0].kind, kind
            )

    def test_new_provenance_invalidates_pending_approval(self):
        script = "print('fixture-only')"
        action = Action("shell", argv=[sys.executable, "-c", script])
        with patch.object(approvals, "_console_answer", return_value="y"):
            decision = approvals.ask(action, session=self.session)
        self.session.provenance.add(script, Source("file", "README.md", 40))
        with self.assertRaises(approvals.ApprovalChanged):
            approvals.validate_before_execution(action, decision, session=self.session)

    def test_steered_test_argv_cannot_reuse_consent(self):
        action = Action(
            "test_consent",
            argv=[
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "fixture_test.py",
            ],
        )
        with patch.object(
            approvals,
            "_console_answer",
            side_effect=lambda prompt: prompt.rsplit("Type ", 1)[-1].split(
                " to approve", 1
            )[0],
        ):
            self.assertEqual(
                approvals.ask(action, session=self.session).verdict, "allow"
            )
        self.session.provenance.add("fixture_test.py", Source("file", "README.md", 40))
        with patch.object(approvals, "_console_answer", return_value="n") as console:
            self.assertEqual(
                approvals.ask(action, session=self.session).verdict, "deny"
            )
        console.assert_called_once()
        self.assertIsNone(self.session._consent)

    def test_cmd_results_are_redacted_and_automatically_indexed(self):
        key = "sk-" + "aB3dE5fG7hI9jK1mN3pQ5rS7"
        action = Action("shell", argv=[sys.executable, "-V"])
        with (
            patch.object(approvals, "_console_answer", return_value="y"),
            patch.object(
                procs,
                "run",
                return_value=CmdResult(
                    action.argv, 0, key + "\nfixture-command", "fixture-error"
                ),
            ),
        ):
            result = cmd.run(
                action.argv, self.root, timeout=1, session=self.session, action=action
            )
        self.assertNotIn(key, result.stdout)
        self.assertIn("[REDACTED:api_key:", result.stdout)
        source = self.session.provenance.steered_by([("fixture-command", "argv")])[0]
        self.assertEqual((source.kind, source.line), ("cmd", 2))

    def test_sensitive_fields_cover_argv_hosts_urls_paths_and_imports(self):
        action = Action(
            "write",
            diff="fixture",
            paths=["module.py"],
            replacements=["from suspicious_package import fn\nurl = 'http://x'"],
        )
        fields = sensitive_fields(action)
        self.assertIn(("suspicious_package", "import"), fields)
        self.assertIn(("http://x", "url"), fields)
        self.assertIn(("x", "host"), fields)
        self.assertIn(("module.py", "path"), fields)

    def fixture_git(self, *arguments):
        executable = str(self.session._exe_pins["git"].path)
        result = procs.run(
            [
                executable,
                "-c",
                "init.templateDir=",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "core.hooksPath=" + str(self.root / "no-hooks"),
                *arguments,
            ],
            self.root,
            root=self.root,
            timeout=30,
            git_env=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_git_push_checks_audited_remote_url_provenance_before_send(self):
        self.fixture_git("init", "--initial-branch=main")
        destination = "https://x.io/fixture"
        self.fixture_git("config", "remote.origin.url", destination)
        self.session.provenance.add(destination, Source("file", "README.md", 40))
        with (
            Git(self.session) as git,
            patch.object(git, "_call", wraps=git._call) as calls,
            self.assertRaisesRegex(GitDenied, "README.md:40"),
        ):
            git.run("push", branch="fixture")
        self.assertFalse(
            any(call.args[0][0] == "push" for call in calls.call_args_list)
        )

    def test_git_revision_provenance_survives_sha_resolution(self):
        self.fixture_git("init", "--initial-branch=main")
        (self.root / "module.py").write_text("x = 1", encoding="utf-8")
        self.fixture_git("add", "--", "module.py")
        self.fixture_git("commit", "--no-gpg-sign", "-m", "fixture")
        self.session.provenance.add("refs/heads/main", Source("file", "README.md", 40))
        with (
            Git(self.session) as git,
            patch.object(approvals, "_console_answer", return_value="n") as console,
            self.assertRaises(approvals.ApprovalDenied),
        ):
            git.run("restore", rev="refs/heads/main", paths=["module.py"])
        self.assertIn("suggested by README.md:40", console.call_args.args[0])


class SecretTests(unittest.TestCase):
    def test_credential_formats_and_deterministic_hashes(self):
        values = {
            "aws": "AKIA" + "ABCDEFGHIJKLMNOP",
            "github": "ghp_" + "AbCdEf0123456789" * 3,
            "api_key": "sk-proj-" + "aB3dE5fG7hI9jK1mN3pQ5rS7",
            "slack": "xoxb-" + "123456789012-123456789012-AbCdEf0123456789",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaXh0dXJlIn0.c3ludGhldGljLXNpZ25hdHVyZQ",
            "pem": "-----BEGIN PRIVATE KEY-----\nSYNTHETIC-FIXTURE-ONLY\n-----END PRIVATE KEY-----",
        }
        for kind, value in values.items():
            with self.subTest(kind=kind):
                marker = f"[REDACTED:{kind}:{hashlib.sha256(value.encode()).hexdigest()[:8]}]"
                marker += "\n" * value.count("\n")
                self.assertEqual(
                    redact("before " + value + " after"), "before " + marker + " after"
                )
                self.assertEqual(redact(redact(value)), marker)

    def test_modern_github_and_slack_personal_formats(self):
        for value in (
            "github_pat_" + "AbCd0123456789_" * 4,
            "xoxp-" + "123456789-987654321-AbCdEf0123456789",
        ):
            self.assertNotIn(value, redact(value))

    def test_jwt_header_whitespace_and_empty_claims(self):
        header = base64.urlsafe_b64encode(b'{ "alg" : "HS256" }').decode().rstrip("=")
        claims = base64.urlsafe_b64encode(b"{}").decode().rstrip("=")
        token = header + "." + claims + ".synthetic_signature"
        self.assertIn("[REDACTED:jwt:", redact(token))
        self.assertNotIn(token, redact(token))
        self.assertEqual(redact("docs.example.invalid"), "docs.example.invalid")

    def test_url_userinfo_is_redacted_without_removing_host(self):
        creds = "fixture-user:fixture%40password"
        result = redact("https://" + creds + "@example.invalid/docs")
        self.assertNotIn(creds, result)
        self.assertTrue(result.startswith("https://[REDACTED:url_credentials:"))
        self.assertTrue(result.endswith("@example.invalid/docs"))

    def test_high_entropy_env_json_and_yaml_values(self):
        value = "aB3dE5fG7hI9jK1mN3pQ5rS7"
        for text in (
            "SERVICE_KEY=" + value,
            '"api_token": "' + value + '"',
            "deployment_secret: '" + value + "'",
        ):
            with self.subTest(text=text):
                self.assertNotIn(value, redact(text))
                self.assertIn("[REDACTED:high_entropy:", redact(text))
                self.assertEqual(redact(redact(text)), redact(text))

    def test_ordinary_text_low_entropy_and_placeholders_preserved(self):
        for text in (
            "API_KEY=aaaaaaaaaaaaaaaaaaaaaaaa",
            "sk-short",
            "API_TOKEN=${TOKEN_FROM_STORE}",
            "SECRET=example",
            "https://example.invalid/docs",
            "return key + token",
        ):
            self.assertEqual(redact(text), text)

    def test_ansi_cannot_split_a_known_credential(self):
        value = "sk-" + "aB3dE5fG7hI9jK1mN3pQ5rS7"
        result = redact(value[:8] + "\x1b[31m" + value[8:] + "\x1b[0m")
        self.assertIn("[REDACTED:api_key:", result)
        self.assertNotIn("\x1b", result)
        self.assertIn("\\u001b", approvals.escape("\x1b[31mfixture"))

    def test_truncated_pem_and_overlapping_matches(self):
        value = "-----BEGIN PRIVATE KEY-----\n" + "sk-" + "aB3dE5fG7hI9jK1mN3pQ5rS7"
        result, findings = redact_with_findings(value)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "pem")
        self.assertNotIn("sk-", result)
        self.assertNotIn("PRIVATE KEY", result)

    def test_findings_do_not_expose_original_secrets(self):
        value = "sk-" + "aB3dE5fG7hI9jK1mN3pQ5rS7"
        _, findings = redact_with_findings(value)
        self.assertNotIn(value, repr(findings))
        self.assertEqual(
            findings[0].sha8, hashlib.sha256(value.encode()).hexdigest()[:8]
        )

    def test_fake_redaction_marker_is_not_a_generic_secret_bypass(self):
        value = "[REDACTED:fake_aB3dE5fG7hI9jK1mN3pQ5rS7]"
        self.assertNotIn(value, redact("API_KEY='" + value + "'"))

    def test_unterminated_quoted_values_and_many_backslashes(self):
        value = "aB3dE5fG7hI9jK1mN3pQ5rS7"
        self.assertNotIn(value, redact("API_KEY='" + value))
        ordinary = "API_KEY='" + "\\" * 10000
        self.assertEqual(redact(ordinary), ordinary)

    def test_prepare_result_redacts_before_indexing(self):
        value = "sk-" + "aB3dE5fG7hI9jK1mN3pQ5rS7"
        index = ProvenanceIndex()
        result = prepare_tool_result(
            value, index=index, source=Source("file", "fixture.txt", 1)
        )
        self.assertEqual(index.steered_by([(value, "argv")]), [])
        self.assertTrue(index.steered_by([(result, "argv")]))

    def test_multiline_redaction_preserves_original_source_lines(self):
        index = ProvenanceIndex()
        text = "-----BEGIN PRIVATE KEY-----\nSYNTHETIC\n-----END PRIVATE KEY-----\nfixture-command"
        clean = prepare_tool_result(
            text, index=index, source=Source("file", "README.md", 37)
        )
        self.assertEqual(clean.count("\n"), text.count("\n"))
        self.assertEqual(
            index.steered_by([("fixture-command", "argv")])[0].location, "README.md:40"
        )

    def test_search_patterns_and_path_postfilter(self):
        for path in (
            ".env",
            ".env.local",
            "nested/.env",
            "key.pem",
            "nested/id_ed25519",
            ".npmrc",
            ".docker/config.json",
            "credentials-demo.json",
            "nested/secrets.yaml",
            "terraform.tfstate",
        ):
            with self.subTest(path=path):
                self.assertTrue(path_is_redacted(path))
        self.assertFalse(path_is_redacted("src/module.py"))
        args = search_exclusion_args()
        self.assertEqual(args[:2], ["--glob", "!.env*"])
        self.assertTrue(all(args[i] == "--glob" for i in range(0, len(args), 2)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertFalse(search_result_allowed(".env", repo_root=root))
            self.assertFalse(search_result_allowed("../outside.txt", repo_root=root))
            self.assertTrue(search_result_allowed("module.py", repo_root=root))

    def test_search_postfilter_catches_secret_symlink_and_confidential_subtree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / ".env").write_text("synthetic only", encoding="utf-8")
            try:
                (root / "visible.txt").symlink_to(root / ".env")
            except OSError:
                pass
            else:
                self.assertFalse(search_result_allowed("visible.txt", repo_root=root))
            marker = root / "nested" / ".crocodile"
            marker.mkdir(parents=True)
            (marker / "confidential").touch()
            self.assertFalse(search_result_allowed("nested/file.txt", repo_root=root))


if __name__ == "__main__":
    unittest.main()
