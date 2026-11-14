"""Read cache (architecture/08 §3): don't resend a file the model has already seen unchanged."""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass


@dataclass
class Seen:
    sha: str
    turn: int
    window: tuple[int, int]
    text: str
    msg_index: int  # index of the history message that carried it (to detect masking)


class ReadCache:
    def __init__(self) -> None:
        self.seen: dict[str, Seen] = {}

    @staticmethod
    def sha(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()

    def lookup(
        self, path: str, window: tuple[int, int], text: str, turn: int, masked: set[int]
    ) -> str | None:
        """Return a short replacement for `text`, or None to send the full window."""
        prev = self.seen.get(path)
        if prev is None or prev.window != window or prev.msg_index in masked:
            return None
        h = self.sha(text)
        if h == prev.sha:
            return (
                f"[unchanged: you already have this exact content in your turn-{prev.turn} read result "
                f"(sha {h[:7]}). Do not read it again; use it and move on (e.g. edit).]"
            )
        diff = list(
            difflib.unified_diff(prev.text.splitlines(), text.splitlines(), "before", "now", lineterm="", n=2)
        )
        diff_text = "\n".join(diff)
        if len(diff_text) < 0.4 * len(text):
            return f"[changed since turn {prev.turn}; diff:]\n{diff_text}"
        return None

    def record(self, path: str, window: tuple[int, int], text: str, turn: int, msg_index: int) -> None:
        from ..security.secrets import secret_scan

        text = secret_scan(text)
        self.seen[path] = Seen(self.sha(text), turn, window, text, msg_index)

    def invalidate(self, path: str) -> None:
        self.seen.pop(path, None)
