"""Pinned task state (architecture/08 §6): rendered last in every prompt, never masked."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .engine.gate import est_tokens

_PLAN = re.compile(r"^\s*PLAN:\s*(.+)$", re.MULTILINE)


@dataclass
class TaskState:
    task: str
    oracle: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    failing: list[str] = field(default_factory=list)
    phase: str = "explore"
    tier: str = "cheap"
    switches: int = 0
    edits: int = 0
    attempts: list[str] = field(default_factory=list)   # failed approaches (survive rewinds)

    def absorb(self, model_text: str) -> None:
        m = _PLAN.findall(model_text or "")
        if m:
            self.plan = [x.strip() for x in re.split(r";|\s\d+\.\s", m[-1]) if x.strip()][:8]

    def render(self, max_tokens: int = 600) -> str:
        def build(dec: list[str]) -> str:
            parts = ["[TASK STATE]", f"phase: {self.phase} | model tier: {self.tier} | edits: {self.edits}"]
            if self.oracle:
                parts.append("success = these tests pass: " + ", ".join(self.oracle[:10]))
            if self.failing:
                parts.append("failing now: " + ", ".join(self.failing[:10])
                             + (f" (+{len(self.failing) - 10})" if len(self.failing) > 10 else ""))
            if self.plan:
                parts.append("plan: " + "; ".join(self.plan))
            if dec:
                parts.append("decisions: " + "; ".join(dec))
            if self.attempts:
                parts.append("already tried and FAILED (do not repeat): " + " | ".join(self.attempts[-4:]))
            if self.switches:
                parts.append(f"strategy switches: {self.switches}")
            return "\n".join(parts)

        dec = list(self.decisions)
        out = build(dec)
        while dec and est_tokens(out) > max_tokens:   # oldest decisions go first; never the task/tests
            dec.pop(0)
            out = build(dec)
        return out
