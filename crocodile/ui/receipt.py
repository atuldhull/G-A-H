"""Evidence-gated receipt rendering from caller values; no code or journal I/O."""

from .session import (
    SessionReceipt, _budget, _clip, _cost, _count, _mode, _options, _safe,
    _tokens, _validate_session, _validate_test, _verification,
)


def _verified_pass(evidence):
    return (
        evidence is not None and evidence.source in {"test_runner", "grader"}
        and evidence.verified is True and evidence.tests_run is True
        and evidence.oracle_frozen is True and evidence.scope in {"full", "partial"}
        and evidence.pytest_exit_code == 0 and evidence.timed_out is False and evidence.error is None
        and evidence.consent_granted is not False
        and evidence.failed in (None, 0) and evidence.regressions in (None, 0)
        and (evidence.passed is None or evidence.passed > 0)
    )


def _heading(receipt):
    evidence = receipt.test_outcome
    known_not_run = (evidence is not None and evidence.tests_run is False
                     and evidence.source in {"controller", "test_runner", "grader"}
                     and evidence.pytest_exit_code is None and evidence.timed_out is not True
                     and all(value in (None, 0) for value in
                             (evidence.passed, evidence.failed, evidence.regressions)))
    if receipt.outcome == "stopped":
        return "STOPPED", None
    if receipt.outcome == "tests_not_run":
        if known_not_run:
            suffix = " (no consent)" if evidence.consent_granted is False else ""
            return "TESTS NOT RUN" + suffix, None
        return "STOPPED", "Tests-not-run request lacks consistent test execution evidence"
    if _verified_pass(evidence):
        if evidence.scope == "full" and receipt.outcome == "solved":
            return "SOLVED", None
        return "SOLVED (partial suite)", "Only the stated verified scope is claimed; full task completion is not asserted"
    if known_not_run:
        return "TESTS NOT RUN", "No verified oracle pass; requested completion was not accepted"
    return "STOPPED", "Verified frozen-oracle test/grading evidence unavailable or unsuccessful; completion not claimed"


def render_receipt(receipt: SessionReceipt, *, ascii_only: bool = False, max_width: int = 240) -> str:
    """Return a bounded multiline receipt, with only formatter-created newlines."""
    _options(ascii_only, max_width)
    if (not isinstance(receipt, SessionReceipt) or not isinstance(receipt.outcome, str)
            or receipt.outcome not in {"solved", "partial", "stopped", "tests_not_run"}):
        raise ValueError("receipt must have a recognized SessionReceipt outcome")
    session, evidence = receipt.session, receipt.test_outcome
    _validate_session(session)
    _validate_test(evidence)
    for value in (receipt.reason, receipt.handoff):
        if value is not None and not isinstance(value, str):
            raise ValueError("Receipt reason/handoff must be plain strings or None")
    heading, explanation = _heading(receipt)
    lines = [heading, f"  Mode: {_mode(session)}"]
    if session.session_id is not None:
        lines.append("  Session: " + _safe(session.session_id, ascii_only=ascii_only, limit=64))
    if session.task is not None:
        lines.append("  Task: " + _safe(session.task, ascii_only=ascii_only, limit=160))
    if session.repository is not None:
        lines.append("  Repository: " + _safe(session.repository, ascii_only=ascii_only, limit=120))
    lines.append(f"  Turns {_count(session.turn)} | {_safe(session.model, ascii_only=ascii_only, limit=48)} "
                 f"({session.rung or 'unknown'}) | escalations {_count(session.escalations)}")
    lines += ["  " + _tokens(session.tokens), "  " + _cost(session.money) + " | " + _budget(session.money),
              "  Verification checkpoints: " + _verification(session.verification)]
    if evidence is None:
        lines.append("  Oracle outcome: unknown; no verified test outcome supplied")
    else:
        lines.append(f"  Oracle outcome: source {evidence.source or 'unknown'}, scope {evidence.scope or 'unknown'}, "
                     f"verified {evidence.verified if evidence.verified is not None else 'unknown'}, "
                     f"tests run {evidence.tests_run if evidence.tests_run is not None else 'unknown'}, "
                     f"exit {evidence.pytest_exit_code if evidence.pytest_exit_code is not None else 'unknown'}")
        lines.append(f"  Oracle counts: passed {_count(evidence.passed)}, failed {_count(evidence.failed)}, "
                     f"regressions {_count(evidence.regressions)}")
        lines.append(f"  Oracle integrity: frozen {evidence.oracle_frozen if evidence.oracle_frozen is not None else 'unknown'}; "
                     f"test consent {evidence.consent_granted if evidence.consent_granted is not None else 'unknown'}")
        if evidence.oracle is not None:
            lines.append("  Oracle: " + _safe(evidence.oracle, ascii_only=ascii_only, limit=96))
        if evidence.timed_out is not None:
            lines.append(f"  Test timeout: {evidence.timed_out}")
        if evidence.error is not None:
            lines.append("  Test error: " + _safe(evidence.error, ascii_only=ascii_only, limit=120))
    savings = session.savings
    if any(value is not None for value in (savings.total_tokens, savings.spilled_tokens, savings.unchanged_tokens, savings.masked_tokens)):
        lines.append(f"  Estimated tokens avoided (first-order): total {_count(savings.total_tokens)}; "
                     f"spilled {_count(savings.spilled_tokens)}; unchanged {_count(savings.unchanged_tokens)}; masked {_count(savings.masked_tokens)}")
    if savings.calls_avoided is not None:
        lines.append(f"  LLM calls avoided by deterministic checks (reported): {_count(savings.calls_avoided)}")
    if explanation:
        lines.append("  Outcome note: " + explanation)
    if receipt.reason is not None:
        lines.append("  Reason: " + _safe(receipt.reason, ascii_only=ascii_only, limit=128))
    if receipt.handoff is not None:
        lines.append("  Handoff: " + _safe(receipt.handoff, ascii_only=ascii_only, limit=160))
    lines.append("  Caller snapshots only; estimated savings are not measured savings and no budget is reserved here.")
    return "\n".join(_clip(line, max_width, ascii_only) for line in lines)
