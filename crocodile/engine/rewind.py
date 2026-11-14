"""Progress-gated rewind (research/03 #6, extended).

After each failed verification:
- more oracle tests pass than at the checkpoint -> COMMIT: the attempt becomes the new checkpoint;
- otherwise -> REWIND: restore the files, cut the failed attempt out of the conversation (the cached
  prefix up to the checkpoint stays valid) and leave a compact note (diff <= 40 lines + why it failed).

Failed attempts therefore stop costing tokens on every later turn, partial progress is never thrown
away, and the model is not anchored on its own wrong trajectory.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

MAX_REWINDS = 3
NOTE_DIFF_LINES = 40


@dataclass
class Checkpoint:
    hist_len: int | None  # history length to cut back to (None until the first edit turn)
    score: int  # oracle tests passing at this checkpoint (-1 = unknown/broken)
    files: dict[str, str | None] = field(default_factory=dict)  # original content (None = did not exist)


class Rewinder:
    def __init__(self, root: Path, score: int, *, restore_files=None):
        self.root = root
        self.cp = Checkpoint(None, score)
        self.rewinds = 0
        self.commits = 0
        self.restore_files = restore_files

    def before_write(self, rel: str, old: str | None) -> None:
        """Called by edit/write before touching a file: remember its content at the checkpoint."""
        self.cp.files.setdefault(rel, old)

    def arm(self, hist_len: int) -> None:
        """First edit turn: the checkpoint is the history as it was before that turn."""
        if self.cp.hist_len is None:
            self.cp.hist_len = hist_len

    def improved(self, score: int) -> bool:
        return score > self.cp.score

    def commit(self, hist_len: int, score: int) -> None:
        self.cp = Checkpoint(hist_len, score)
        self.commits += 1

    def can_rewind(self) -> bool:
        return self.cp.hist_len is not None and self.rewinds < MAX_REWINDS and bool(self.cp.files)

    def diff(self) -> str:
        out: list[str] = []
        for rel, old in sorted(self.cp.files.items()):
            p = self.root / rel
            new = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            out += difflib.unified_diff(
                (old or "").splitlines(), new.splitlines(), f"a/{rel}", f"b/{rel}", lineterm="", n=1
            )
        if len(out) > NOTE_DIFF_LINES:
            out = out[:NOTE_DIFF_LINES] + [f"... [{len(out) - NOTE_DIFF_LINES} more diff lines]"]
        return "\n".join(out)

    def restore(self) -> list[str]:
        """Put every touched file back to its checkpoint content. Returns the restored paths."""
        if self.restore_files is None:
            raise PermissionError("checkpoint restoration requires the security write handler")
        restored = self.restore_files(self.cp.files)
        self.cp.files = {}
        self.rewinds += 1
        return restored
