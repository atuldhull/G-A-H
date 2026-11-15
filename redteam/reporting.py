"""Per-architecture verdicts and sanitized fixture evidence, separate from framework passes."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from crocodile.security.secrets import secret_scan


def source_digest():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for folder in ("crocodile", "redteam"):
        for path in sorted((root / folder).rglob("*.py")):
            digest.update(str(path.relative_to(root)).replace("\\", "/").encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


class ReportPlugin:
    def __init__(self, output):
        self.output = Path(output)
        self.results = {}
        self.flows = {}

    def pytest_sessionstart(self, session):
        sha = os.environ.get("GITHUB_SHA")
        if not sha:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                timeout=10,
                check=False,
            )
            sha = result.stdout.decode().strip() if result.returncode == 0 else None
        self.header = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "git_revision": sha,
            "source_tree_sha256": source_digest(),
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "fixture_scope": "real owner code; disposable state; scripted models/synthetic credentials; live egress is separate",
        }

    def pytest_runtest_logreport(self, report):
        if not any(name in report.nodeid for name in ("test_security_case[", "test_cli_flow[")):
            return
        if report.when != "call" and report.passed:
            return
        group = (
            int(report.nodeid.split("test_security_case[")[1].split("-")[0])
            if "test_security_case[" in report.nodeid
            else None
        )
        evidence = next((value for key, value in report.user_properties if key == "evidence"), {})
        value = {
            "group": group,
            "nodeid": report.nodeid,
            "status": "passed" if report.passed else "blocked" if report.skipped else "failed",
            "evidence": evidence,
            "details": str(report.longrepr) if not report.passed else "",
        }
        if group is None:
            self.flows[report.nodeid] = value
        else:
            self.results[group] = value

    def pytest_sessionfinish(self, session, exitstatus):
        cases = [
            self.results.get(
                group, {"group": group, "status": "blocked", "details": "case did not produce a verdict"}
            )
            for group in range(1, 16)
        ]
        result = {
            **self.header,
            "pytest_exit_status": int(exitstatus),
            "cases": cases,
            "cli_flows": list(self.flows.values()),
            "counts": {
                status: sum(case["status"] == status for case in cases)
                for status in ("passed", "failed", "blocked")
            },
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(secret_scan(json.dumps(result, indent=2)), encoding="utf-8")
