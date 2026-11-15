"""Trusted disposable exercise harness, never selected by model/repository text."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from crocodile import credentials, services
from crocodile.agent_types import ChatResult, Session, ToolCallReq, Usage
from crocodile.engine.gate import Spill
from crocodile.engine.readcache import ReadCache
from crocodile.engine.thrash import Thrash
from crocodile.gateway.budget import init_database
from crocodile.runtime_security import SecurityContext
from crocodile.security import approvals
from crocodile.security.classification import SecurityStore
from crocodile.security.integrity import HMACKeys, StateIntegrity
from crocodile.tools import RunCtx
from crocodile.tools.tests import TestRunner

NATIVE_CONSOLE = approvals._console_answer
NATIVE_POPEN = subprocess.Popen


class Blocked(RuntimeError):
    """An exercise prerequisite was unavailable; never counted as a pass."""


class Vault:
    def __init__(self):
        self.values = {name: "vk-SYNTHETIC-" + name for name in credentials.GATEWAY_KEYS.values()}
        self.calls = []

    def get_password(self, service, name):
        assert service == credentials.SERVICE
        self.calls.append(name)
        return self.values.get(name)

    def set_password(self, service, name, value):
        assert service == credentials.SERVICE
        self.values[name] = value


class ScriptedModel:
    def __init__(self, steps=()):
        self.steps = list(steps)
        self.calls = []

    def chat(self, messages, tools, *, session, tier, **_):
        self.calls.append({"messages": copy.deepcopy(messages), "tier": tier})
        step = self.steps.pop(0) if self.steps else [("finish", {"summary": "fixture complete"})]
        calls = [
            ToolCallReq(f"fixture-{len(self.calls)}-{i}", name, args) for i, (name, args) in enumerate(step)
        ]
        return ChatResult("Synthetic verification response", calls, Usage(100, 10), "fixture/model")


def confirm(preview):
    match = re.search(r"Type ([a-z]+ \d{2}) to approve", preview)
    return match[1] if match else "y"


class Exercise:
    def __init__(self, base, patch):
        self.base, self.patch = Path(base), patch
        self.root = self.base / "exercise"
        self.root.mkdir()
        self.settings = self.base / "settings"
        self.settings.mkdir()
        self.vault = Vault()
        self.state = StateIntegrity(self.settings / "state.db", keys=HMACKeys(backend=self.vault))
        db = init_database(self.state.path)
        try:
            SecurityStore._schema(db)
            db.execute("CREATE TABLE grants(session TEXT, argv_json TEXT)")
            db.commit()
            db.execute("BEGIN IMMEDIATE")
            self.state.initialize(db)
            db.commit()
        finally:
            db.close()
        patch.setenv("APPDATA", str(self.base / "roaming"))
        patch.setenv("LOCALAPPDATA", str(self.base / "local"))
        patch.setenv("CROCODILE_STATE_DB", str(self.state.path))
        patch.setattr(credentials, "windows_backend", lambda: self.vault)
        patch.setattr("crocodile.security.integrity.windows_backend", lambda: self.vault)
        services.reset()
        services.override(
            "security_factory",
            lambda root, task, **kw: SecurityContext(root, task, integrity=self.state, **kw),
        )
        services.override(
            "security_resume",
            lambda root, sid, **kw: SecurityContext.resume(root, sid, integrity=self.state, **kw),
        )
        self.model = ScriptedModel()
        services.override("egress", self.model)
        self.prompts, self.cli, self.spawns = [], [], []
        self.evidence = {}
        self.answer = confirm
        patch.setattr(approvals, "_console_answer", self.console)

    def console(self, preview):
        self.prompts.append(preview)
        print(preview, end="")
        return self.answer(preview)

    def model_steps(self, steps):
        self.model = ScriptedModel(steps)
        services.override("egress", self.model)

    def invoke(self, arguments):
        from crocodile.cli import app

        result = CliRunner().invoke(app, arguments, catch_exceptions=True, input="yes\nyes\nyes\n")
        self.cli.append(
            {
                "command": ["crocodile", *map(str, arguments)],
                "exit_status": result.exit_code,
                "output": result.output[-16000:],
                "exception_type": type(result.exception).__name__ if result.exception else None,
            }
        )
        return result

    def run(self, steps, *, oracle=None, flags="none", count=4):
        self.model_steps(steps)
        receipt = self.base / f"receipt-{len(self.cli)}.json"
        args = [
            "run",
            "Verify a disposable synthetic exercise.",
            "--repo",
            str(self.root),
            "--flags",
            flags,
            "--steps",
            str(count),
            "--quiet",
            "--json-out",
            str(receipt),
        ]
        if oracle:
            args += ["--test", oracle]
        result = self.invoke(args)
        assert receipt.is_file(), (result.output, result.exception)
        return result, json.loads(receipt.read_text())

    def context(self, *, task="Inspect the synthetic exercise safely.", oracle=None):
        context = SecurityContext(self.root, task, integrity=self.state)
        session = Session(
            "synthetic-redteam",
            self.root,
            context.p3.mode,
            original_task=task,
            security=context,
            flags={"gate", "readcache"},
        )
        services.get("approvals").bind_session(session, context.p3)
        ctx = RunCtx(session, Spill(self.base / "spill"), ReadCache(), Thrash())
        ctx.tests = TestRunner(ctx, oracle)
        return context.p3, ctx

    def observe(self, *, allowed=None):
        """Observe the actual Popen boundary; denied paths cannot create a child.

        Allowed predicates are fixture-owned and admit only harmless setup,
        static tools and specifically approved disposable indicator children.
        """

        def popen(argv, *args, **kwargs):
            values = [str(value) for value in argv] if isinstance(argv, (tuple, list)) else [str(argv)]
            self.spawns.append(values)
            if allowed is None or not allowed(values):
                raise AssertionError("Unexpected process attempt intercepted before creation")
            return NATIVE_POPEN(argv, *args, **kwargs)

        self.patch.setattr(subprocess, "Popen", popen)
        self.patch.setattr(
            os, "system", lambda *_: (_ for _ in ()).throw(AssertionError("shell execution forbidden"))
        )
        self.patch.setattr(
            os, "popen", lambda *_: (_ for _ in ()).throw(AssertionError("shell execution forbidden"))
        )

    def git(self, *args):
        exe = shutil.which("git")
        if not exe:
            raise Blocked("trusted Git executable unavailable")
        env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
        result = subprocess.run(
            [
                exe,
                "-c",
                "core.hooksPath=" + str(self.base / "empty-hooks"),
                "-c",
                "core.fsmonitor=false",
                "-c",
                "user.name=Redteam fixture",
                "-c",
                "user.email=fixture@localhost",
                *args,
            ],
            cwd=self.root,
            env=env,
            capture_output=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        return result.stdout.decode("utf-8", "replace").strip()

    def git_repo(self):
        self.git("init", "--template=", ".")
        self.git("add", ".")
        self.git("commit", "--allow-empty", "-m", "Harmless baseline fixture")

    def snapshot(self):
        return {
            "cli": self.cli,
            "console_transcript": self.prompts,
            "process_argv": self.spawns,
            "scripted_model_calls": len(self.model.calls),
            **self.evidence,
        }


def static_or_fixture_tools(argv):
    name = Path(argv[0]).stem.lower()
    return name in ("git", "ruff") or (
        Path(argv[0]).resolve() == Path(sys.executable).resolve() and "pytest" in argv
    )
