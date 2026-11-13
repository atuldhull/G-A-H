"""edit tool: staged SEARCH/REPLACE matcher (architecture/08 §4).

Stages: exact -> whitespace-normalised (same indent offset) -> drop leading blank line ->
`...` elision -> fuzzy (>= 0.9, only if exactly one candidate) -> "did you mean" (>= 0.6).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Result


@dataclass
class Match:
    start: int        # line index (inclusive)
    end: int          # line index (exclusive)
    stage: str
    score: float = 1.0
    indent_delta: str = ""


class NoMatch(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)


def _find_all(hay: list[str], needle: list[str]) -> list[int]:
    n = len(needle)
    return [i for i in range(len(hay) - n + 1) if hay[i:i + n] == needle]


def _indent(s: str) -> str:
    return s[: len(s) - len(s.lstrip())]


def _ws_match(hay: list[str], needle: list[str]) -> list[tuple[int, str]]:
    """Lines equal after stripping, with the same indent offset on every non-blank line."""
    n = len(needle)
    stripped = [x.strip() for x in needle]
    out = []
    for i in range(len(hay) - n + 1):
        if [x.strip() for x in hay[i:i + n]] != stripped:
            continue
        deltas = set()
        for h, s in zip(hay[i:i + n], needle, strict=True):
            if s.strip():
                hi, si = _indent(h), _indent(s)
                if hi.endswith(si):
                    deltas.add(hi[: len(hi) - len(si)])
                else:
                    deltas.add(None)
        if len(deltas) == 1 and None not in deltas:
            out.append((i, deltas.pop()))
    return out


def locate(content: str, search: str) -> Match:
    hay = content.splitlines()
    needle = search.splitlines()
    if not needle or not "".join(needle).strip():
        raise NoMatch("empty SEARCH block")
    # 1 exact
    hits = _find_all(hay, needle)
    if len(hits) == 1:
        return Match(hits[0], hits[0] + len(needle), "exact")
    if len(hits) > 1:
        raise NoMatch(f"SEARCH matches {len(hits)} places; add surrounding lines to make it unique")
    # 2 whitespace-normalised
    ws = _ws_match(hay, needle)
    if len(ws) == 1:
        i, delta = ws[0]
        return Match(i, i + len(needle), "whitespace", indent_delta=delta)
    # 3 drop leading/trailing blank lines
    trimmed = needle[:]
    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    if trimmed != needle and trimmed:
        hits = _find_all(hay, trimmed)
        if len(hits) == 1:
            return Match(hits[0], hits[0] + len(trimmed), "trim-blank")
    # 4 `...` elision: each piece must be unique and in order
    if any(x.strip() == "..." for x in needle):
        pieces, cur = [], []
        for x in needle:
            if x.strip() == "...":
                if cur:
                    pieces.append(cur)
                cur = []
            else:
                cur.append(x)
        if cur:
            pieces.append(cur)
        pos, first, last = 0, None, None
        for p in pieces:
            hs = [h for h in _find_all(hay, p) if h >= pos]
            if len(_find_all(hay, p)) != 1 or not hs:
                break
            first = hs[0] if first is None else first
            pos = last = hs[0] + len(p)
        else:
            if first is not None and last is not None:
                return Match(first, last, "elision")
    # 5 fuzzy, only with exactly one candidate >= 0.9
    n = len(needle)
    target = "\n".join(needle)
    scored = []
    for size in {n - 1, n, n + 1}:
        if size <= 0:
            continue
        for i in range(max(0, len(hay) - size) + 1):
            r = difflib.SequenceMatcher(None, "\n".join(hay[i:i + size]), target, autojunk=False)
            if r.real_quick_ratio() < 0.6 or r.quick_ratio() < 0.6:
                continue
            scored.append((r.ratio(), i, size))
    good = [s for s in scored if s[0] >= 0.9]
    if good:
        sc, i, sz = max(good)
        rivals = [g for g in good if g[1] + g[2] <= i or g[1] >= i + sz]   # non-overlapping candidates
        if not rivals:
            return Match(i, i + sz, "fuzzy", score=round(sc, 2))
    # 6 did you mean
    best = max(scored, default=None)
    if best and best[0] >= 0.6:
        _, i, sz = best
        lo, hi = max(0, i - 5), min(len(hay), i + sz + 5)
        snippet = "\n".join(f"{k + 1:>5}| {hay[k]}" for k in range(lo, hi))
        raise NoMatch(f"SEARCH not found. Did you mean lines {i + 1}-{i + sz}?\n{snippet}\n"
                      "Resend only this block with SEARCH copied exactly.")
    raise NoMatch("SEARCH not found and nothing similar. read() the file and copy the lines exactly.")


def apply_edit(content: str, search: str, replace: str) -> tuple[str, Match]:
    """Returns the new content and how it matched. Raises NoMatch."""
    m = locate(content, search)
    lines = content.splitlines()
    rep = replace.splitlines()
    if m.indent_delta:
        # Re-indent only if REPLACE is under-indented like SEARCH was; if the model already wrote
        # REPLACE at the file's indentation, adding the delta again would double-indent it.
        def min_indent(xs: list[str]) -> int:
            return min((len(x) - len(x.lstrip()) for x in xs if x.strip()), default=0)
        if min_indent(rep) < min_indent(lines[m.start:m.end]):
            rep = [m.indent_delta + x if x.strip() else x for x in rep]
    nl = "\r\n" if "\r\n" in content else "\n"
    trailing = content.endswith(("\n", "\r\n"))
    new = nl.join(lines[: m.start] + rep + lines[m.end:])
    return (new + nl if trailing or not content else new), m


# ---------- the tool ----------

def edit_tool(args: dict, ctx) -> Result:
    from .. import services
    from ..contracts import Action
    from .base import Result, ToolError, rel, resolve_in_repo

    path = str(args.get("path", ""))
    edits = args.get("edits") or []
    if not isinstance(edits, list) or not edits:
        raise ToolError("edits must be a non-empty list of {search, replace}")
    p = resolve_in_repo(path, ctx.root, for_write=True)
    r = rel(p, ctx.root) if p.exists() else p.relative_to(ctx.root.resolve()).as_posix()
    exists = p.is_file()
    if not exists and not (len(edits) == 1 and not str(edits[0].get("search", "")).strip()):
        raise ToolError(f"{path} does not exist; to create it send one edit with an empty search")
    if exists and r not in ctx.shown_paths:
        cur = p.read_text(encoding="utf-8", errors="replace")
        ctx.shown_paths.add(r)
        if len(cur) <= 6000:
            raise ToolError(f"{r} was not read yet, so nothing was changed. Current content:\n{cur}\n"
                            "Resend the edit with SEARCH copied exactly from this content.")
        raise ToolError(f"read('{r}') before editing it, so SEARCH matches what is on disk")
    old = p.read_text(encoding="utf-8", errors="replace") if exists else ""
    new = old
    notes, failed = [], []
    if not exists:
        new = str(edits[0].get("replace", ""))
        if new and not new.endswith("\n"):
            new += "\n"
        notes.append("created")
    else:
        for k, e in enumerate(edits, 1):
            s, rp = str(e.get("search", "")), str(e.get("replace", ""))
            ctx.thrash.record_edit(r, s, rp)
            try:
                new, m = apply_edit(new, s, rp)
                if m.stage != "exact":
                    notes.append(f"block {k}: {m.stage} match" + (f" {m.score}" if m.stage == "fuzzy" else ""))
            except NoMatch as err:
                if rp.strip() and rp.strip() in new:
                    failed.append(f"block {k}: already applied (REPLACE text is in the file); "
                                  "do not resend it, move to the next change")
                else:
                    failed.append(f"block {k}: {err}")
    if new == old:
        return Result("no change applied.\n" + "\n".join(failed), ok=False)
    diff = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{r}", f"b/{r}",
                                          lineterm="", n=2))
    is_test = r in ctx.oracle_files or p.name == "conftest.py" or p.name.startswith("test_") \
        or p.stem.endswith("_test")
    level = "red" if is_test else "amber"
    reasons = ["modifies the success criterion (test/conftest)"] if is_test else []
    d = services.get("approvals").ask(Action(kind="write", summary=f"edit {r}", diff=diff, level=level,
                                             reasons=reasons + notes), ctx.session)
    services.get("journal").append(ctx.session, "approval", {"kind": "write", "path": r,
                                                             "approved": d.approved, "level": level})
    if not d.approved:
        return Result(f"user declined the edit to {r}", ok=False)
    if ctx.on_before_write is not None:
        ctx.on_before_write(r, old if exists else None)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    ctx.readcache.invalidate(r)
    ctx.shown_paths.add(r)
    ctx.touched.add(r)
    if is_test and r in ctx.oracle_files:
        ctx.session.flags.add("_oracle_modified")
    plus = sum(1 for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++"))
    minus = sum(1 for x in diff.splitlines() if x.startswith("-") and not x.startswith("---"))
    msg = f"edited {r} (+{plus} -{minus})"
    if notes:
        msg += "; " + "; ".join(notes)
    if failed:
        msg += "\nFAILED blocks (resend only these):\n" + "\n".join(failed)
    return Result(msg, ok=not failed)


WRITE_MAX_LINES = 200


def write_tool(args: dict, ctx) -> Result:
    """Whole-file write for small files (weak models handle this far better than SEARCH/REPLACE)."""
    from .. import services
    from ..contracts import Action
    from .base import Result, ToolError, resolve_in_repo

    path = str(args.get("path", ""))
    content = args.get("content")
    if not isinstance(content, str):
        raise ToolError("content must be the full new file text")
    p = resolve_in_repo(path, ctx.root, for_write=True)
    r = p.relative_to(ctx.root.resolve()).as_posix()
    old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    if old.count("\n") > WRITE_MAX_LINES:
        raise ToolError(f"{r} has more than {WRITE_MAX_LINES} lines; use edit with SEARCH/REPLACE")
    if content and not content.endswith("\n"):
        content += "\n"
    if "\r\n" in old:
        content = content.replace("\r\n", "\n").replace("\n", "\r\n")
    if content == old:
        last = ctx.tests.last if ctx.tests is not None else None
        why = f"\nIt still fails:\n{last.failure_text[:1500]}" if last is not None and last.failed else ""
        return Result(f"no change: {r} already has exactly this content. Sending it again will not help; "
                      f"change the logic that the failing test exercises.{why}", ok=False)
    ctx.thrash.record_edit(r, "<write>", content)
    diff = "\n".join(difflib.unified_diff(old.splitlines(), content.splitlines(), f"a/{r}", f"b/{r}",
                                          lineterm="", n=2))
    is_test = r in ctx.oracle_files or p.name == "conftest.py" or p.name.startswith("test_") \
        or p.stem.endswith("_test")
    level = "red" if is_test else "amber"
    d = services.get("approvals").ask(Action(kind="write", summary=f"write {r}", diff=diff, level=level,
                                             reasons=["modifies the success criterion (test/conftest)"]
                                             if is_test else []), ctx.session)
    services.get("journal").append(ctx.session, "approval", {"kind": "write", "path": r,
                                                             "approved": d.approved, "level": level})
    if not d.approved:
        return Result(f"user declined the write to {r}", ok=False)
    if ctx.on_before_write is not None:
        ctx.on_before_write(r, old if p.is_file() else None)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    ctx.readcache.invalidate(r)
    ctx.shown_paths.add(r)
    ctx.touched.add(r)
    if is_test and r in ctx.oracle_files:
        ctx.session.flags.add("_oracle_modified")
    return Result(f"wrote {r} ({content.count(chr(10))} lines)")
