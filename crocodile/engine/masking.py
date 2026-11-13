"""Batched masking (architecture/08 §5): replace old tool outputs with stubs, in batches only.

Masking rewrites history, which breaks the prompt cache once, so it only fires when the saving is
worth it (>= MIN_GAIN tokens at once).
"""

from __future__ import annotations

from .gate import est_tokens

AGE = 10          # turns before a tool output may be masked
MIN_GAIN = 6000   # tokens saved per batch before we break the cache
STUB_TOKENS = 30


def maybe_mask(history: list[dict], meta: list[dict], turn: int, masked: set[int], *,
               age: int = AGE, min_gain: int = MIN_GAIN) -> int:
    """history[i] is an OpenAI message; meta[i] has {'turn','tool','spill','exit'} for tool messages.

    Returns the number of tokens saved (0 if nothing was masked)."""
    old = [i for i, m in enumerate(history)
           if m.get("role") == "tool" and i not in masked and meta[i]
           and turn - meta[i].get("turn", turn) > age]
    gain = sum(est_tokens(history[i]["content"]) for i in old) - STUB_TOKENS * len(old)
    if gain < min_gain:
        return 0
    for i in old:
        md = meta[i]
        where = f"; full: {md['spill']}" if md.get("spill") else ""
        history[i]["content"] = (f"[{md.get('tool', 'tool')} output masked (turn {md.get('turn')})"
                                 f"{'; exit ' + str(md['exit']) if md.get('exit') is not None else ''}"
                                 f"{where}; re-run or re-read if needed]")
        masked.add(i)
    return gain
