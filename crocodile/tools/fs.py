"""Read-only tools: read, list, search. Reads are free (no approval)."""

from __future__ import annotations

import fnmatch
import os
import re

from ..security.secrets import path_is_redacted, secret_scan
from .base import SKIP_DIRS, Result, RunCtx, ToolError, observe_file, rel, secure_path

MAX_READ_LINES = 400
MAX_HITS = 50


def read(args: dict, ctx: RunCtx) -> Result:
    path = str(args.get("path", ""))
    start = args.get("start")
    end = args.get("end")
    if path.startswith("out:"):
        text = ctx.spill.get(path)
        if text is None:
            raise ToolError(f"unknown spill handle {path}")
        lines = text.splitlines()
        s = max(1, int(start or 1))
        e = min(len(lines), int(end or s + 199))
        return Result(f"{path} lines {s}-{e} of {len(lines)}\n" + "\n".join(lines[s - 1 : e]))
    p = secure_path(path, ctx)
    if not p.is_file():
        raise ToolError(f"not a file: {path}")
    if path_is_redacted(p.relative_to(ctx.root)):
        return Result("[REDACTED sensitive file]")
    if p.stat().st_size > 2_000_000:
        raise ToolError("file too large; use search or a line range")
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    n = len(lines)
    s = max(1, int(start or 1))
    e = min(n, int(end)) if end else min(n, s + MAX_READ_LINES - 1)
    window_text = "\n".join(lines[s - 1 : e])
    r = rel(p, ctx.root)
    window_text = observe_file(ctx, window_text, r, s)
    ctx.shown_paths.add(r)
    head = f"{r} (lines {s}-{e} of {n})" if (s > 1 or e < n) else f"{r} ({n} lines)"
    more = f"\n[more: read('{r}', {e + 1}, ...)]" if e < n else ""
    if ctx.flag("readcache"):
        short = ctx.readcache.lookup(r, (s, e), window_text, ctx.turn, ctx.masked)
        if short is not None:
            from ..engine.gate import est_tokens

            return Result(
                f"{head}\n{short}",
                tokens_avoided=max(0, est_tokens(window_text) - 20),
                read_key=(r, (s, e), window_text),
            )
    return Result(f"{head}\n{window_text}{more}", read_key=(r, (s, e), window_text))


def _walk(root, sub):
    for dirpath, dirnames, filenames in os.walk(sub):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".crocodile"))
        for f in sorted(filenames):
            yield os.path.join(dirpath, f)


def list_(args: dict, ctx: RunCtx) -> Result:
    p = secure_path(str(args.get("path") or "."), ctx)
    if not p.is_dir():
        raise ToolError("not a directory")
    depth = max(1, min(4, int(args.get("depth") or 2)))
    out = []
    base_parts = len(p.parts)
    for f in _walk(ctx.root, p):
        from pathlib import Path

        fp = Path(f)
        try:
            secure_path(str(fp), ctx)
        except (ValueError, ToolError):
            continue
        if len(fp.parts) - base_parts > depth:
            continue
        out.append(rel(fp, ctx.root))
        if len(out) >= 300:
            out.append("... [truncated at 300 entries]")
            break
    return Result("\n".join(out) or "(empty)")


def search(args: dict, ctx: RunCtx) -> Result:
    try:
        rx = re.compile(str(args["pattern"]))
    except re.error as e:
        raise ToolError(f"bad regex: {e}") from None
    p = secure_path(str(args.get("path") or "."), ctx)
    glob = args.get("glob")
    hits: list[str] = []
    files = [str(p)] if p.is_file() else _walk(ctx.root, p)
    total = 0
    for f in files:
        if glob and not fnmatch.fnmatch(os.path.basename(f), glob):
            continue
        try:
            fp = secure_path(f, ctx)
            if path_is_redacted(fp.relative_to(ctx.root)):
                continue
            if os.path.getsize(f) > 1_000_000:
                continue
            with open(f, encoding="utf-8", errors="strict") as fh:
                for i, line in enumerate(fh, 1):
                    if rx.search(line):
                        total += 1
                        if len(hits) < MAX_HITS:
                            from pathlib import Path

                            r = rel(Path(f), ctx.root)
                            text = observe_file(ctx, line.rstrip(), r, i)
                            hits.append(f"{r}:{i}: {secret_scan(text)[:200]}")
        except (UnicodeDecodeError, OSError, ValueError, ToolError):
            continue
    if not hits:
        return Result("no matches")
    more = f"\n[{total - MAX_HITS} more matches; narrow the pattern or path]" if total > MAX_HITS else ""
    return Result("\n".join(hits) + more)
