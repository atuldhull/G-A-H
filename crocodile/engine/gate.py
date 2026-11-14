"""Output gate (architecture/08 §2): strip ANSI, scan secrets, spill full output, show a compact view.

The model sees: kind-specific summary (pytest) or tail-biased head+tail, plus every must-keep line
grouped by signature, plus a spill handle `out:N` it can page through with read().
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
MUST_KEEP = re.compile(
    r"(Error\b|Exception\b|Traceback|^E\s|FAILED|ERROR|assert|panic|fatal|^\s*File \".*\", line \d+)",
    re.IGNORECASE,
)
NUM_PATH = re.compile(r"(0x[0-9a-f]+|\d+|[A-Za-z]:\\[^\s:]+|/[^\s:]+)")
# Minimal fallback secret scan; Part 3's crocodile.security.secrets.scan replaces it when present.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|tvly-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:(?:api[_-]?key|secret|token|password)\s*[:=]\s*)['\"]?[^\s'\"]{8,})"
)

CAP_CHARS = 10_240
CAP_LINES = 256


def _secret_scan(text: str) -> str:
    """Part 3's scanner (crocodile.security.secrets.secret_scan) when present, else a minimal fallback."""
    try:
        from crocodile.security.secrets import secret_scan  # type: ignore[import-not-found]
    except ImportError:
        return _SECRET.sub("[REDACTED]", text)
    return secret_scan(text, strip_ansi=False)


def est_tokens(text: str) -> int:
    return (len(text) + 3) // 4


@dataclass
class Gated:
    shown: str
    spill: str | None
    raw_tokens: int
    shown_tokens: int

    @property
    def avoided(self) -> int:
        return max(0, self.raw_tokens - self.shown_tokens)


class Spill:
    """Session-scoped spill store. Handles are `out:N` with an integer N only."""

    def __init__(self, root: Path | None):
        self.root = root
        self.n = 0
        self.mem: dict[int, str] = {}

    def put(self, text: str) -> str:
        text = _secret_scan(text)
        self.n += 1
        if self.root is not None:
            (self.root / "out").mkdir(parents=True, exist_ok=True)
            (self.root / "out" / f"{self.n}.txt").write_text(text, encoding="utf-8")
        else:
            self.mem[self.n] = text
        return f"out:{self.n}"

    def get(self, handle: str) -> str | None:
        m = re.fullmatch(r"out:(\d+)", handle.strip())
        if not m:
            return None
        n = int(m.group(1))
        if self.root is not None:
            p = self.root / "out" / f"{n}.txt"
            return _secret_scan(p.read_text(encoding="utf-8")) if p.is_file() else None
        text = self.mem.get(n)
        return _secret_scan(text) if text is not None else None


def head_tail(lines: list[str], max_lines: int, max_chars: int, head: float = 0.2) -> list[str]:
    text_len = sum(len(x) + 1 for x in lines)
    if len(lines) <= max_lines and text_len <= max_chars:
        return lines
    h = max(1, int(max_lines * head))
    t = max_lines - h
    out_h, out_t = lines[:h], lines[-t:] if t else []
    budget = max_chars
    keep_h: list[str] = []
    for ln in out_h:
        if budget - len(ln) < max_chars * (1 - head):
            break
        keep_h.append(ln[:400])
        budget -= len(ln) + 1
    keep_t: list[str] = []
    for ln in reversed(out_t):
        if budget - len(ln) < 0:
            break
        keep_t.append(ln[:400])
        budget -= len(ln) + 1
    keep_t.reverse()
    skipped = len(lines) - len(keep_h) - len(keep_t)
    return keep_h + [f"... [{skipped} lines omitted] ..."] + keep_t


def signature(line: str) -> str:
    return NUM_PATH.sub("#", line.strip())[:160]


def must_keep_grouped(lines: list[str], limit: int = 40) -> list[str]:
    groups: OrderedDict[str, list[str]] = OrderedDict()
    for ln in lines:
        if MUST_KEEP.search(ln):
            groups.setdefault(signature(ln), []).append(ln.rstrip()[:300])
    out = []
    for items in list(groups.values())[:limit]:
        out.append(items[0] if len(items) == 1 else f"x{len(items)} {items[0]}")
    return out


def gate(
    raw: str, exit_code: int | None, spill: Spill, *, enabled: bool = True, summary: str | None = None
) -> Gated:
    """`summary` is a kind-specific view (e.g. pytest format_failure); else head+tail+must-keep."""
    text = _secret_scan(ANSI.sub("", raw))
    raw_tokens = est_tokens(text)
    lines = text.splitlines()
    if not enabled:
        shown = text
        handle = None
    elif summary is None and len(lines) <= 60 and len(text) <= 4000:
        shown, handle = text, None
    else:
        handle = spill.put(text)
        if summary is not None:
            body = _secret_scan(ANSI.sub("", summary))
        else:
            ht = head_tail(lines, CAP_LINES, CAP_CHARS)
            visible = set(ht)
            extra = [x for x in must_keep_grouped(lines) if x not in visible]
            body = "\n".join(ht + (["[must-keep lines]"] + extra if extra else []))
        shown = f"{body}\n[full output: {handle} ({len(lines)} lines) -> read('{handle}', start, end)]"
    if exit_code is not None:
        shown = f"{shown}\n[exit {exit_code}]"
    return Gated(shown, handle, raw_tokens, est_tokens(shown))
