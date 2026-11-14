"""One-line status rendering from a caller snapshot, without I/O or aggregation."""

from .session import (
    SessionSnapshot, _budget, _clip, _cost, _count, _mode, _options, _safe,
    _tokens, _validate_session, _verification,
)


def render_status(session: SessionSnapshot, *, ascii_only: bool = False, max_width: int = 240) -> str:
    """Return one bounded literal line. The mode is pinned before truncation."""
    _options(ascii_only, max_width)
    _validate_session(session)
    model = _safe(session.model, ascii_only=ascii_only, limit=40)
    parts = [
        _mode(session), f"{model} ({session.rung or 'unknown'})",
        f"turn {_count(session.turn)} {session.phase or 'phase unknown'}",
        "verify " + _verification(session.verification),
        _tokens(session.tokens), _cost(session.money), _budget(session.money),
    ]
    if session.savings.total_tokens is not None:
        parts.append(f"avoided est {_count(session.savings.total_tokens)} tok (first-order)")
    return _clip(" | ".join(parts), max_width, ascii_only)
