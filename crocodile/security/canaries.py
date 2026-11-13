"""Send-time canary check for Part 2; no network calls or gateway logging."""

import hashlib
import json
import re
from dataclasses import dataclass

from .classification import ClassificationError, SecurityStore

TOKEN = re.compile(r"CANARY-[0-9a-f]{32}$")


@dataclass(frozen=True)
class CanaryCheck:
    hits: int
    token_hashes: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return self.hits > 0


def check(payload, *, store: SecurityStore | None = None) -> CanaryCheck:
    """Call immediately before sending any public/Tavily payload.

    ASCII wire matches and decoded JSON strings are checked, so JSON Unicode
    escaping is not a bypass. Findings expose hashes, never canary tokens.
    Registry/read/shape errors must refuse the send, not be treated as no hits.
    """
    store = store if store is not None else SecurityStore()
    tokens = store.canaries()
    if any(
        not isinstance(token, str) or not TOKEN.fullmatch(token) for token in tokens
    ):
        raise ClassificationError("invalid token in canary registry")
    texts = []
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ClassificationError(
                "canary scan requires UTF-8 or structured JSON payloads"
            ) from error
        if "\0" in payload:
            raise ClassificationError(
                "NUL-bearing wire payload requires normalized JSON before scanning"
            )
    if isinstance(payload, str):
        texts.append(payload)
        try:
            structured = json.loads(payload)
        except (ValueError, RecursionError):
            structured = None
    else:
        structured = payload
    pending = [structured]
    visited, count = set(), 0
    decoded = []
    while pending:
        value = pending.pop()
        count += 1
        if count > 50_000:
            raise ClassificationError("canary payload scan exceeded entry cap")
        if isinstance(value, str):
            decoded.append(value)
        elif isinstance(value, (list, tuple, dict)):
            if id(value) in visited:
                raise ClassificationError(
                    "cyclic/shared payload requires serialization before scanning"
                )
            visited.add(id(value))
            pending.extend(value.keys() if isinstance(value, dict) else value)
            if isinstance(value, dict):
                pending.extend(value.values())
        elif value is not None and not isinstance(value, (int, float, bool)):
            raise ClassificationError("unsupported payload type for canary scan")
    hits, hashes = 0, []
    for token in tokens:
        occurrences = max(
            sum(text.count(token) for text in texts),
            sum(text.count(token) for text in decoded),
        )
        if occurrences:
            hits += occurrences
            hashes.append(hashlib.sha256(token.encode()).hexdigest()[:8])
    return CanaryCheck(hits, tuple(hashes))
