"""Counterfactual savings receipt (research/03 #4): per-technique tokens saved, from the run itself.

First-order estimate, no reruns: a chunk of N tokens that a technique kept out of the conversation at
step s would otherwise have been re-sent on every later model call, so it is worth N x (calls after s).
Label it "estimated, first-order" wherever it is shown; Part 4 calibrates it against the ablation bench.
"""

from __future__ import annotations

from collections import defaultdict


class Savings:
    def __init__(self) -> None:
        self.items: list[tuple[str, int, int, str]] = []   # (technique, tokens, step, mode)

    def carried(self, technique: str, tokens: int, step: int) -> None:
        """Tokens kept out of history at `step` (would have been re-sent on calls after it)."""
        if tokens > 0:
            self.items.append((technique, tokens, step, "carried"))

    def once(self, technique: str, tokens: int, step: int) -> None:
        """Tokens saved exactly once (e.g. a model call that never had to happen)."""
        if tokens > 0:
            self.items.append((technique, tokens, step, "once"))

    def report(self, total_calls: int, cached_tokens: int = 0) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for tech, tokens, step, mode in self.items:
            out[tech] += tokens if mode == "once" else tokens * max(0, total_calls - step)
        if cached_tokens:
            out["cache (90% discount on cached input)"] = int(cached_tokens * 0.9)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))
