"""run_tests + oracle (architecture/08 §8-9, ADR-004).

Only this module builds a pytest argv. Running tests executes repo code (conftest.py), so the first
run in a session needs explicit test consent; consent is voided if a conftest/config file changes.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .. import services
from ..agent_types import Action
from ..engine.gate import gate
from .base import Result, RunCtx, ToolError

CONFIG_NAMES = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
_RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+)")
_SUMMARY = re.compile(r"^=*\s*(\d+ (passed|failed|error|errors|skipped|xfailed|xpassed).*?)\s*=*$")
_SECTION = re.compile(r"^_{3,}\s+(.+?)\s+_{3,}$")


@dataclass
class TestReport:
    passed: set[str] = field(default_factory=set)
    failed: set[str] = field(default_factory=set)
    summary: str = ""
    exit_code: int = 0
    timed_out: bool = False
    failure_text: str = ""     # compact format_failure view
    first_error: str = ""
    raw: str = ""

    @property
    def collected_nothing(self) -> bool:
        return self.exit_code == 5 or (not self.passed and not self.failed)


def _hash(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12] if p.is_file() else "-"


def exec_surface(root: Path) -> dict[str, str]:
    """Files pytest will import or read before any test runs."""
    out = {}
    for name in CONFIG_NAMES:
        for p in [root / name, *root.glob(f"*/{name}")]:
            if p.is_file():
                out[p.relative_to(root).as_posix()] = _hash(p)
    return out


def format_failure(raw: str, root: Path, max_fail: int = 5) -> tuple[str, str]:
    """Per failing test: id, the E lines (expected vs actual), <=3 in-repo frames. Returns (text, first_error)."""
    blocks: list[tuple[str, list[str]]] = []
    cur: list[str] | None = None
    in_fail = False
    for ln in raw.splitlines():
        if ln.startswith("=") and "FAILURES" in ln or ln.startswith("=") and "ERRORS" in ln:
            in_fail = True
            continue
        if in_fail and ln.startswith("=") and "short test summary" in ln:
            break
        if not in_fail:
            continue
        m = _SECTION.match(ln)
        if m:
            cur = []
            blocks.append((m.group(1), cur))
        elif cur is not None:
            cur.append(ln)
    out, first_err = [], ""
    for name, lines in blocks[:max_fail]:
        e_lines = [x for x in lines if x.startswith("E ")][:8]
        frames = [x.strip() for x in lines if re.match(r"^\S.*:\d+: \w*", x)
                  and not x.startswith(("E ", ">"))][-3:]
        code = [x for x in lines if x.startswith(">")][-1:]
        if not first_err and e_lines:
            first_err = e_lines[0]
        out.append(f"FAIL {name}\n" + "\n".join(code + e_lines + frames))
    if len(blocks) > max_fail:
        out.append(f"... {len(blocks) - max_fail} more failures (see spill)")
    return "\n".join(out), first_err


def parse(raw: str, exit_code: int, root: Path) -> TestReport:
    rep = TestReport(exit_code=exit_code, raw=raw)
    for ln in raw.splitlines():
        m = _RESULT_LINE.match(ln.strip())
        if m:
            status, tid = m.groups()
            if status in ("PASSED", "XPASS"):
                rep.passed.add(tid)
            elif status in ("FAILED", "ERROR"):
                rep.failed.add(tid)
        s = _SUMMARY.match(ln.strip())
        if s:
            rep.summary = s.group(1)
    rep.failure_text, rep.first_error = format_failure(raw, root)
    if not rep.first_error:
        err = [x for x in raw.splitlines() if "Error" in x]
        rep.first_error = err[0] if err else ""
    return rep


class TestRunner:
    def __init__(self, ctx: RunCtx, oracle_ids: list[str] | None = None):
        self.ctx = ctx
        self.consent: dict[str, str] | None = None
        self.oracle_ids = oracle_ids or []
        self.full_targets: list[str] | None = None   # [] = whole suite after oracle green; None = skip
        self.baseline_passed: set[str] = set()
        self.last: TestReport | None = None
        self.runs = 0
        self._approved: set = set()

    def _consent(self, argv: list[str]) -> None:
        """Consent is per exact argv + exec surface (Part 3 binds the permit to what will run)."""
        surface = exec_surface(self.ctx.root)
        key = (tuple(argv), tuple(sorted(surface.items())))
        if key in self._approved:
            return
        listing = "\n".join(f"  {k}  {v}" for k, v in surface.items()) or "  (no conftest/config files)"
        d = services.get("approvals").ask(Action(
            kind="test_consent", level="red",
            summary="THIS EXECUTES CODE FROM THE REPO (pytest imports conftest.py and the tests)",
            argv=list(argv), reasons=["exec surface:\n" + listing]), self.ctx.session)
        services.get("journal").append(self.ctx.session, "approval",
                                       {"kind": "test_consent", "approved": d.approved})
        if not d.approved:
            raise ToolError("test run not approved by the user; tests cannot run this session")
        self._approved.add(key)
        self.consent = surface

    def run(self, ids: list[str] | None = None, timeout: int = 90) -> TestReport:
        targets = list(self.oracle_ids) if ids is None else list(ids)   # [] = whole suite
        argv = [sys.executable, "-m", "pytest", "-q", "-rA", "--tb=short", "--no-header",
                "-p", "no:cacheprovider", *targets]
        self._consent(argv)
        r = services.get("cmd").run(argv, self.ctx.root, timeout=timeout)
        raw = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        rep = parse(raw, r.exit_code, self.ctx.root)
        rep.timed_out = r.timed_out
        self.last = rep
        self.runs += 1
        return rep

    def show(self, rep: TestReport) -> Result:
        head = rep.summary or f"exit {rep.exit_code}"
        if rep.timed_out:
            head += " (TIMED OUT)"
        summary = head if not rep.failed else f"{rep.failure_text}\n{head}"
        if rep.exit_code not in (0, 1) and not rep.failed:
            summary = None   # collection/usage error: fall back to head+tail+must-keep
        g = gate(rep.raw, rep.exit_code, self.ctx.spill, enabled=self.ctx.flag("gate"), summary=summary)
        return Result(g.shown, ok=rep.exit_code == 0, spill=g.spill, exit=rep.exit_code,
                      tokens_avoided=g.avoided)


def run_tests(args: dict, ctx: RunCtx) -> Result:
    if ctx.tests is None:
        raise ToolError("tests unavailable")
    ids = [str(x) for x in (args.get("ids") or [])]
    for i in ids:
        if i.startswith("-"):
            raise ToolError("pass test ids or files only, not pytest options")
    rep = ctx.tests.run(ids or None)
    return ctx.tests.show(rep)
