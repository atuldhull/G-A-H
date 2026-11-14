"""Tool registry. The loop calls dispatch(); schemas live in base.SCHEMAS."""

from __future__ import annotations

from .base import SCHEMAS, Result, RunCtx, ToolError
from .cmd import git, run_cmd
from .edit import edit_tool, write_tool
from .fs import list_, read, search
from .tests import run_tests
from .web import web_docs

TOOLS = {
    "read": read, "list": list_, "search": search, "edit": edit_tool, "write": write_tool,
    "run_tests": run_tests, "run_cmd": run_cmd, "git": git, "web_docs": web_docs,
}
READ_ONLY = {"read", "list", "search", "git"}

__all__ = ["READ_ONLY", "SCHEMAS", "TOOLS", "Result", "RunCtx", "ToolError", "dispatch"]


def dispatch(name: str, args: dict, ctx: RunCtx) -> Result:
    fn = TOOLS.get(name)
    if fn is None:
        return Result(f"unknown tool {name}", ok=False)
    if not isinstance(args, dict) or "_raw" in args:
        return Result("arguments were not valid JSON; resend the call", ok=False)
    try:
        return fn(args, ctx)
    except ToolError as e:
        return Result(f"error: {e}", ok=False)
    except (OSError, ValueError, TypeError, KeyError) as e:
        return Result(f"error: {type(e).__name__}: {e}", ok=False)
