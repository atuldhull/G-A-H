"""Verification ladder + green check (architecture/08 §9).

syntax (in-process compile, no exec) -> lint (ruff isolated, if installed) -> oracle tests -> full suite.
Green = oracle passes AND nothing that passed at baseline fails now AND oracle files untouched.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import services
from .gate import gate


@dataclass
class Verdict:
    stage: str  # syntax | lint | oracle | full
    ok: bool
    green: bool
    shown: str
    sig_ids: list[str]
    first_error: str
    passed: int = -1  # oracle tests passing (-1 = syntax/lint failure or unknown)


def _syntax(root: Path, touched: list[str]) -> tuple[bool, str]:
    errs = []
    for r in touched:
        if not r.endswith(".py"):
            continue
        p = root / r
        if not p.is_file():
            continue
        try:
            compile(p.read_text(encoding="utf-8", errors="replace"), r, "exec", dont_inherit=True)
        except SyntaxError as e:
            errs.append(f"{r}:{e.lineno}:{e.offset}: SyntaxError: {e.msg}\n    {(e.text or '').rstrip()}")
    return (not errs), "\n".join(errs)


def _lint(ctx, touched: list[str]) -> tuple[bool, str]:
    root = ctx.root
    py = [r for r in touched if r.endswith(".py") and (root / r).is_file()]
    exe = shutil.which("ruff")
    if not py or not exe or Path(exe).resolve().is_relative_to(root.resolve()):
        return True, ""
    argv = [
        exe,
        "check",
        "--isolated",
        "--no-cache",
        "--select",
        "F821,F822,F823,E9",
        "--output-format",
        "concise",
        *py,
    ]
    from ..agent_types import Action

    decision = services.get("approvals").ask(Action("shell", "isolated static lint", argv=argv), ctx.session)
    if not decision.approved:
        return False, "lint was not approved"
    r = services.get("cmd").run(argv, root, timeout=60, session=ctx.session)
    if r.exit_code == 0:
        return True, ""
    lines = [x for x in r.stdout.splitlines() if ":" in x and not x.startswith("Found")]
    return False, "\n".join(lines[:20])


def verify(ctx, touched: list[str], *, full: bool = True) -> Verdict:
    from ..tools.base import secure_path

    services.security(ctx.session)
    for path in touched:
        secure_path(path, ctx)
    ok, msg = _syntax(ctx.root, touched)
    if not ok:
        return Verdict("syntax", False, False, msg, [], msg.splitlines()[0])
    ok, msg = _lint(ctx, touched)
    if not ok:
        return Verdict("lint", False, False, msg, [], msg.splitlines()[0] if msg else "")
    tr = ctx.tests
    if tr is None or not tr.oracle_ids or "_no_test_consent" in ctx.session.flags:
        return Verdict("lint", True, False, "syntax+lint ok; no oracle tests", [], "")
    rep = tr.run()
    oracle_ok = rep.exit_code == 0 and not rep.failed and bool(rep.passed)
    if not oracle_ok:
        shown = tr.show(rep).shown
        return Verdict("oracle", False, False, shown, sorted(rep.failed), rep.first_error, len(rep.passed))
    if "_oracle_modified" in ctx.session.flags:
        return Verdict(
            "oracle",
            True,
            False,
            "oracle passes but a test file was modified; green is void until the user re-confirms",
            [],
            "oracle modified",
        )
    # Flake guard: rerun the oracle once on first green. Unattended runs only (bench/--yes); an
    # interactive user would face an extra "THIS EXECUTES CODE" prompt for the same command.
    if ctx.session.approve_mode == "auto":
        tr.run()
        if not (tr.last and tr.last.exit_code == 0 and not tr.last.failed):
            return Verdict("oracle", False, False, "oracle flaky: passed then failed on rerun", [], "flaky")
    if full and tr.full_targets is not None:
        frep = tr.run(tr.full_targets)
        regressed = sorted(tr.baseline_passed - frep.passed)
        if regressed:
            g = gate("\n".join(regressed), None, ctx.spill)
            return Verdict(
                "full",
                False,
                False,
                "regressions (passed before, fail now):\n" + g.shown,
                regressed,
                f"regression {regressed[0]}",
            )
    return Verdict(
        "full" if full and tr.full_targets is not None else "oracle",
        True,
        True,
        rep.summary or "tests pass",
        [],
        "",
    )
