"""Tool registry. The loop calls dispatch(); schemas live in base.SCHEMAS."""

from __future__ import annotations

from .base import SCHEMAS, Result, RunCtx, ToolError
from .cmd import git, run_cmd
from .edit import delete_tool, edit_tool, write_tool
from .fs import list_, read, search
from .tests import run_tests
from .web import web_docs

TOOLS = {
    "read": read,
    "list": list_,
    "search": search,
    "edit": edit_tool,
    "write": write_tool,
    "run_tests": run_tests,
    "run_cmd": run_cmd,
    "git": git,
    "web_docs": web_docs,
    "delete": delete_tool,
}
READ_ONLY = {"read", "list", "search", "git"}

__all__ = ["READ_ONLY", "SCHEMAS", "TOOLS", "Result", "RunCtx", "ToolError", "dispatch"]


def dispatch(name: str, args: dict, ctx: RunCtx) -> Result:
    from .. import services
    from ..engine.gate import gate
    from ..security.provenance import Source

    context = services.security(ctx.session)
    fn = TOOLS.get(name)
    if fn is None:
        return Result(f"unknown tool {name}", ok=False)
    if not isinstance(args, dict) or "_raw" in args:
        return Result("arguments were not valid JSON; resend the call", ok=False)
    try:
        result = fn(args, ctx)
    except ToolError as e:
        result = Result(f"error: {e}", ok=False)
    except (OSError, ValueError, TypeError, KeyError) as e:
        result = Result(f"error: {type(e).__name__}: {e}", ok=False)
    raw = context.observe(result.shown, Source("cmd", f"{name}:{ctx.call_id}"))
    shown = gate(raw, None, ctx.spill, enabled=ctx.flag("gate"))
    result.shown = shown.shown
    result.spill = result.spill or shown.spill
    result.tokens_avoided += shown.avoided
    return result
