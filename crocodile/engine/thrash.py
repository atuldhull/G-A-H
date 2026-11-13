"""Thrash detector (architecture/08 §10): spot repeated failures and drive escalate -> stop."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

_STRIP = re.compile(r"(0x[0-9a-f]+|\d+(\.\d+)?|[A-Za-z]:\\\S+|/\S+)")


def failure_sig(failing_ids: list[str], first_error: str) -> str:
    core = _STRIP.sub("#", first_error.strip())[:200]
    return hashlib.sha1(("|".join(sorted(failing_ids)) + "||" + core).encode()).hexdigest()[:12]


class Thrash:
    def __init__(self) -> None:
        self.sigs: list[str] = []
        self.edit_hashes: list[str] = []
        self.calls: list[str] = []
        self.idle = 0          # turns without an applied edit, counted after the first edit
        self.switches = 0
        self.reason = ""

    def record_failure(self, sig: str) -> None:
        self.sigs.append(sig)

    def record_edit(self, path: str, search: str, replace: str) -> None:
        self.edit_hashes.append(hashlib.sha1(f"{path}\0{search}\0{replace}".encode()).hexdigest())

    def record_call(self, name: str, args: dict) -> None:
        import json
        self.calls.append(name + json.dumps(args, sort_keys=True, default=str))

    def record_turn(self, edited: bool, after_first_edit: bool) -> None:
        if edited:
            self.idle = 0
        elif after_first_edit:
            self.idle += 1

    def check(self) -> Literal["escalate", "stop_report"] | None:
        hit = None
        if len(self.sigs) >= 2 and self.sigs[-1] == self.sigs[-2]:
            hit = "same failure twice"
        elif len(self.edit_hashes) >= 2 and self.edit_hashes[-1] in self.edit_hashes[:-1]:
            hit = "same edit proposed twice"
        elif len(self.calls) >= 3 and len(set(self.calls[-3:])) == 1:
            hit = "same call repeated 3 times"
        elif self.idle >= 5:
            hit = "5 turns without an edit"
        if not hit:
            return None
        self.reason = hit
        self.sigs.clear()
        self.edit_hashes.clear()
        self.calls.clear()
        self.idle = 0
        self.switches += 1
        return "escalate" if self.switches == 1 else "stop_report"
