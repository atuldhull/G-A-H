"""run_cmd (argv only, approval required) and read-only git templates (free)."""

from __future__ import annotations

from .. import services
from ..agent_types import Action
from ..engine.gate import gate
from .base import Result, RunCtx, ToolError

_GIT_READ = {
    "status": ["status", "--porcelain=v1", "-b"],
    "diff": ["diff", "--no-ext-diff", "--no-color", "--stat", "-p"],
    "log": ["log", "--oneline", "--no-color", "-n", "15"],
}


def run_cmd(args: dict, ctx: RunCtx) -> Result:
    argv = args.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ToolError("argv must be a non-empty list of strings (no shell strings)")
    name = argv[0].lower().replace("\\", "/").rsplit("/", 1)[-1]
    if name in ("pytest", "py.test") or (len(argv) > 2 and argv[1:3] == ["-m", "pytest"]):
        raise ToolError("use run_tests for pytest")
    if name in ("git", "git.exe"):
        raise ToolError("use the git tool for read-only git; mutations are not available to the agent")
    d = services.get("approvals").ask(Action(kind="shell", summary="run command", argv=argv), ctx.session)
    services.get("journal").append(
        ctx.session, "approval", {"kind": "shell", "argv": argv, "approved": d.approved}
    )
    if not d.approved:
        return Result("user declined this command", ok=False)
    r = services.get("cmd").run(argv, ctx.root, timeout=120, session=ctx.session)
    g = gate(
        (r.stdout or "") + ("\n" + r.stderr if r.stderr else ""),
        r.exit_code,
        ctx.spill,
        enabled=ctx.flag("gate"),
    )
    return Result(g.shown, ok=r.exit_code == 0, spill=g.spill, exit=r.exit_code, tokens_avoided=g.avoided)


def git(args: dict, ctx: RunCtx) -> Result:
    op = args.get("op")
    if op not in _GIT_READ:
        raise ToolError("op must be status, diff or log")
    r = services.git_read(op, ctx.session)
    g = gate((r.stdout or "") + (r.stderr or ""), r.exit_code, ctx.spill, enabled=ctx.flag("gate"))
    return Result(
        g.shown or "(empty)", ok=r.exit_code == 0, spill=g.spill, exit=r.exit_code, tokens_avoided=g.avoided
    )
