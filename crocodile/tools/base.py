"""Tool context, path rules and the frozen tool schemas sent to the model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contracts import Session
from ..engine.gate import Spill
from ..engine.readcache import ReadCache
from ..engine.thrash import Thrash

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", ".crocodile", ".idea", ".vscode"}


class ToolError(Exception):
    """Shown to the model as the tool result; never crashes the loop."""


@dataclass
class Result:
    shown: str
    ok: bool = True
    spill: str | None = None
    exit: int | None = None
    tokens_avoided: int = 0
    read_key: tuple[str, tuple[int, int], str] | None = None   # (path, window, text) for the read cache


@dataclass
class RunCtx:
    session: Session
    spill: Spill
    readcache: ReadCache
    thrash: Thrash
    turn: int = 0
    masked: set[int] = field(default_factory=set)
    touched: set[str] = field(default_factory=set)
    shown_paths: set[str] = field(default_factory=set)   # files read() has shown (edit locality rule)
    oracle_files: set[str] = field(default_factory=set)  # test files frozen at start: edits are red
    tests: Any = None                                    # tools.tests.TestRunner
    on_before_write: Any = None                          # (rel, old_content|None) -> None; rewind hook

    @property
    def root(self) -> Path:
        return self.session.repo

    def flag(self, name: str) -> bool:
        return name in self.session.flags


def resolve_in_repo(p: str, root: Path, *, for_write: bool = False) -> Path:
    """Minimal containment check. Part 3's security.paths adds the full Windows rules."""
    if not p or "\x00" in p:
        raise ToolError("empty or invalid path")
    q = (root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    r = root.resolve()
    if q != r and r not in q.parents:
        raise ToolError(f"path outside the repo: {p}")
    rel = q.relative_to(r)
    if rel.parts and rel.parts[0] in (".git", ".crocodile"):
        raise ToolError(f"protected path: {p}")
    if for_write and q.name.lower() in {"conftest.py"}:
        pass  # allowed but red (handled by the edit tool)
    return q


def rel(p: Path, root: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required,
                       "additionalProperties": False}}}


# Frozen and sorted by name: part of the cache-stable prefix. Keep descriptions terse.
SCHEMAS: list[dict] = sorted([
    _fn("edit", "Edit a file with SEARCH/REPLACE blocks. SEARCH must copy existing lines exactly "
        "(<=60 lines, unique). Empty search + new path creates the file.",
        {"path": {"type": "string"},
         "edits": {"type": "array", "items": {"type": "object", "properties": {
             "search": {"type": "string"}, "replace": {"type": "string"}},
             "required": ["search", "replace"]}}},
        ["path", "edits"]),
    _fn("finish", "Stop. Use when the task is done or impossible. Tests are checked automatically.",
        {"summary": {"type": "string"}}, ["summary"]),
    _fn("git", "Read-only git: status, diff or log.",
        {"op": {"type": "string", "enum": ["status", "diff", "log"]}}, ["op"]),
    _fn("list", "List files under a directory.",
        {"path": {"type": "string"}, "depth": {"type": "integer"}}, []),
    _fn("read", "Read a file (or a spill handle like out:3). Optional 1-based line range.",
        {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}},
        ["path"]),
    _fn("run_cmd", "Run one command as an argv list (no shell). Needs user approval.",
        {"argv": {"type": "array", "items": {"type": "string"}}}, ["argv"]),
    _fn("run_tests", "Run pytest. Optional test ids or files; default: the task's tests.",
        {"ids": {"type": "array", "items": {"type": "string"}}}, []),
    _fn("write", "Replace a whole file (<=200 lines) or create one. Send the complete new content.",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("search", "Regex search in repo files. Returns file:line: text.",
        {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}},
        ["pattern"]),
], key=lambda s: s["function"]["name"])
