"""Typed value inputs and pure, bounded formatting helpers for session displays."""

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Literal
import unicodedata

from .quote import Money, _decimal, _money


CheckState = Literal["passed", "failed", "not_run", "pending"]


@dataclass(frozen=True)
class VerificationState:
    syntax: CheckState | None = None
    lint: CheckState | None = None
    affected_passed: int | None = None
    affected_total: int | None = None
    failing_oracles: int | None = None


@dataclass(frozen=True)
class TokenUsage:
    """Input total includes disjoint uncached, cache-write, and cache-read input."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    estimated: bool = True


@dataclass(frozen=True)
class SessionMoney:
    session_usd: Money | None = None
    cost_estimated: bool = True
    quote_usd: Money | None = None
    today_spent_usd: Money | None = None
    today_limit_usd: Money | None = None
    budget_estimated: bool = True


@dataclass(frozen=True)
class SavingsEstimate:
    total_tokens: int | None = None
    spilled_tokens: int | None = None
    unchanged_tokens: int | None = None
    masked_tokens: int | None = None
    calls_avoided: int | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    model: str | None = None
    rung: Literal["cheap", "strong", "local"] | None = None
    turn: int | None = None
    phase: Literal["reproduce", "fix", "verify", "done"] | None = None
    mode: Literal["public", "confidential"] | None = None
    verification: VerificationState = field(default_factory=VerificationState)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    money: SessionMoney = field(default_factory=SessionMoney)
    savings: SavingsEstimate = field(default_factory=SavingsEstimate)
    task: str | None = None
    repository: str | None = None
    session_id: str | None = None
    escalations: int | None = None


@dataclass(frozen=True)
class TestOutcome:
    """A caller attestation from its trusted runner/grader, never an LLM proof."""

    source: Literal["test_runner", "grader", "controller", "model"] | None = None
    verified: bool | None = None
    scope: Literal["full", "partial", "agent"] | None = None
    tests_run: bool | None = None
    oracle_frozen: bool | None = None
    pytest_exit_code: int | None = None
    timed_out: bool | None = None
    error: str | None = None
    passed: int | None = None
    failed: int | None = None
    regressions: int | None = None
    oracle: str | None = None
    consent_granted: bool | None = None


# Prevent pytest from treating this public value type as a test class on import.
TestOutcome.__test__ = False


@dataclass(frozen=True)
class SessionReceipt:
    outcome: Literal["solved", "partial", "stopped", "tests_not_run"] = "stopped"
    session: SessionSnapshot = field(default_factory=SessionSnapshot)
    test_outcome: TestOutcome | None = None
    reason: str | None = None
    handoff: str | None = None


def _optional_text(value, label):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be plain string data or None")


def _count_value(value, label):
    if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
        raise ValueError(f"{label} must be a nonnegative 64-bit integer or None")


def _boolean(value, label, *, optional=False):
    if not (optional and value is None) and type(value) is not bool:
        raise ValueError(f"{label} must be a boolean" + (" or None" if optional else ""))


def _choice(value, choices, label):
    if value is not None and (not isinstance(value, str) or value not in choices):
        raise ValueError(f"Invalid {label}")


def _options(ascii_only, max_width):
    _boolean(ascii_only, "ascii_only")
    if type(max_width) is not int or not 80 <= max_width <= 1000:
        raise ValueError("max_width must be an integer from 80 to 1000 characters")


def _validate_session(session):
    if not isinstance(session, SessionSnapshot):
        raise ValueError("session must be SessionSnapshot")
    for name in ("model", "task", "repository", "session_id"):
        _optional_text(getattr(session, name), name)
    _choice(session.rung, {"cheap", "strong", "local"}, "rung")
    _choice(session.phase, {"reproduce", "fix", "verify", "done"}, "phase")
    _choice(session.mode, {"public", "confidential"}, "mode")
    for name in ("turn", "escalations"):
        _count_value(getattr(session, name), name)
    if not isinstance(session.verification, VerificationState):
        raise ValueError("verification must be VerificationState")
    verification = session.verification
    for name in ("syntax", "lint"):
        _choice(getattr(verification, name), {"passed", "failed", "not_run", "pending"}, name)
    for name in ("affected_passed", "affected_total", "failing_oracles"):
        _count_value(getattr(verification, name), name)
    if (verification.affected_passed is not None and verification.affected_total is not None
            and verification.affected_passed > verification.affected_total):
        raise ValueError("Affected passed count exceeds affected total")
    if not isinstance(session.tokens, TokenUsage) or not isinstance(session.money, SessionMoney):
        raise ValueError("tokens/money must be TokenUsage/SessionMoney")
    tokens = session.tokens
    _boolean(tokens.estimated, "tokens.estimated")
    for name in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
        _count_value(getattr(tokens, name), name)
    known_cache = sum(value for value in (tokens.cache_read_tokens, tokens.cache_write_tokens) if value is not None)
    if tokens.input_tokens is not None and known_cache > tokens.input_tokens:
        raise ValueError("Known cache input exceeds normalized input total")
    money = session.money
    for name in ("cost_estimated", "budget_estimated"):
        _boolean(getattr(money, name), name)
    for name in ("session_usd", "quote_usd", "today_spent_usd", "today_limit_usd"):
        _money(getattr(money, name), name)
    if not isinstance(session.savings, SavingsEstimate):
        raise ValueError("savings must be SavingsEstimate")
    for name in ("total_tokens", "spilled_tokens", "unchanged_tokens", "masked_tokens", "calls_avoided"):
        _count_value(getattr(session.savings, name), name)


def _validate_test(evidence):
    if evidence is None:
        return
    if not isinstance(evidence, TestOutcome):
        raise ValueError("test_outcome must be TestOutcome or None")
    _choice(evidence.source, {"test_runner", "grader", "controller", "model"}, "test source")
    _choice(evidence.scope, {"full", "partial", "agent"}, "test scope")
    for name in ("verified", "tests_run", "oracle_frozen", "timed_out", "consent_granted"):
        _boolean(getattr(evidence, name), name, optional=True)
    for name in ("passed", "failed", "regressions"):
        _count_value(getattr(evidence, name), name)
    if evidence.pytest_exit_code is not None and (
        type(evidence.pytest_exit_code) is not int or not -(2**63) <= evidence.pytest_exit_code < 2**63
    ):
        raise ValueError("pytest_exit_code must be a signed 64-bit integer or None")
    for name in ("error", "oracle"):
        _optional_text(getattr(evidence, name), name)


def _safe(value, *, ascii_only=False, limit=80):
    """Escape before truncation; never interpolate arbitrary objects or controls."""
    if value is None or not value.strip():
        return "unknown"
    marker = "..." if ascii_only else "\u2026"
    pieces, length = [], 0
    for char in value[:limit]:
        category = unicodedata.category(char)
        if category.startswith("C") or category in {"Zl", "Zp"} or char in "|[]":
            piece = f"\\u{ord(char):04x}"
        elif char == "\\":
            piece = "\\\\"
        else:
            piece = char.encode("ascii", "backslashreplace").decode() if ascii_only else char
        if length + len(piece) > limit - len(marker):
            return "".join(pieces) + marker
        pieces.append(piece)
        length += len(piece)
    result = "".join(pieces)
    return result + marker if len(value) > limit else result


def _clip(line, width, ascii_only):
    marker = "..." if ascii_only else "\u2026"
    return line if len(line) <= width else line[:width - len(marker)] + marker


def _count(value):
    if value is None:
        return "unknown"
    for scale, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1000, "K")):
        if value >= scale:
            return f"{value / scale:.3g}{suffix}"
    return str(value)


def _usd(value):
    amount = _money(value, "USD")
    return "unknown" if amount is None else "$" + format(Decimal(_decimal(amount)), ".6g")


def _mode(session):
    return "mode unknown" if session.mode is None else ("LOCKED confidential" if session.mode == "confidential" else "public")


def _verification(verification):
    labels = {None: "unknown", "passed": "ok", "failed": "FAIL", "not_run": "not run", "pending": "pending"}
    affected = ("unknown" if verification.affected_passed is None and verification.affected_total is None
                else f"{_count(verification.affected_passed)}/{_count(verification.affected_total)}")
    text = f"syntax {labels[verification.syntax]}, lint {labels[verification.lint]}, affected {affected}"
    if verification.failing_oracles is not None:
        text += f", failing oracle {_count(verification.failing_oracles)}"
    return text


def _tokens(tokens):
    prefix = "tokens est" if tokens.estimated else "tokens reported"
    cache = "unknown"
    if tokens.input_tokens is not None and tokens.input_tokens > 0 and tokens.cache_read_tokens is not None:
        cache = f"{100 * tokens.cache_read_tokens / tokens.input_tokens:.0f}% read"
    return f"{prefix} in {_count(tokens.input_tokens)} / out {_count(tokens.output_tokens)} (cache {cache})"


def _cost(money):
    text = "cost " + ("est " if money.cost_estimated else "reported ") + _usd(money.session_usd)
    if money.quote_usd is not None:
        text += " / quote est " + _usd(money.quote_usd)
    return text


def _budget(money):
    text = "today " + ("est " if money.budget_estimated else "reported ")
    text += _usd(money.today_spent_usd) + "/" + _usd(money.today_limit_usd)
    spent = _money(money.today_spent_usd, "spent")
    limit = _money(money.today_limit_usd, "limit")
    if spent is not None and limit is not None and limit > 0 and spent >= limit * Fraction(4, 5):
        text += " WARN >=80%"
    return text
