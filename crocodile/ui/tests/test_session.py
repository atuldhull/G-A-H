"""Pure session renderer tests with synthetic snapshots and trusted-source stubs."""

import builtins
import copy
from dataclasses import replace
from decimal import Decimal
import importlib
import os
from pathlib import Path
import socket
import subprocess

import pytest

from crocodile.ui import (
    SavingsEstimate, SessionMoney, SessionReceipt, SessionSnapshot, TestOutcome,
    TokenUsage, VerificationState, render_receipt, render_status,
)


@pytest.fixture
def session():
    return SessionSnapshot(
        model="test/cheap-model", rung="cheap", turn=7, phase="verify", mode="public",
        verification=VerificationState("passed", "passed", 3, 4, 1),
        tokens=TokenUsage(48_200, 2100, 43_862, 0, estimated=False),
        money=SessionMoney("0.0043", True, "0.006", "1.60", "5.00", False),
        savings=SavingsEstimate(41_000, 21_400, 6100, 9800, 2),
        task="fix date parsing", repository="repo/src", session_id="session-1", escalations=0,
    )


@pytest.fixture
def passed():
    return TestOutcome(
        source="test_runner", verified=True, scope="full", tests_run=True,
        oracle_frozen=True, pytest_exit_code=0, timed_out=False,
        passed=212, failed=0, regressions=0, oracle="tests/test_dates.py::test_dates[iso]",
        consent_granted=True,
    )


def test_status_contains_required_fields_and_is_one_line(session):
    line = render_status(session, max_width=1000)
    assert line.startswith("public | test/cheap-model (cheap)")
    for expected in ("turn 7 verify", "syntax ok", "lint ok", "affected 3/4", "failing oracle 1",
                     "in 48.2K", "out 2.1K", "91% read", "cost est $0.0043", "quote est $0.006",
                     "today reported $1.6/$5", "avoided est 41K tok (first-order)"):
        assert expected in line
    assert len(line.splitlines()) == 1


def test_unknown_fields_stay_unknown_and_do_not_imply_zero():
    status = render_status(SessionSnapshot(), max_width=1000)
    receipt = render_receipt(SessionReceipt())
    assert "mode unknown" in status
    assert "turn unknown" in status
    assert "cost est unknown" in status
    assert "$0" not in status
    assert "0%" not in status
    assert receipt.startswith("STOPPED\n")
    assert "no verified test outcome supplied" in receipt
    assert "0 regressions" not in receipt
    assert "Estimated tokens avoided" not in receipt


def test_verified_full_receipt_has_reported_evidence_and_estimated_savings(session, passed):
    text = render_receipt(SessionReceipt("solved", session, passed))
    assert text.startswith("SOLVED\n")
    assert "passed 212, failed 0, regressions 0" in text
    assert "source test_runner, scope full, verified True" in text
    assert "cost est $0.0043" in text
    assert "Estimated tokens avoided (first-order)" in text
    assert "LLM calls avoided by deterministic checks (reported): 2" in text
    assert "escalations 0" in text
    assert "\\u005biso\\u005d" in text


def test_verified_grader_can_supply_pass_without_invented_test_counts(session, passed):
    evidence = replace(passed, source="grader", passed=None, failed=None, regressions=None)
    text = render_receipt(SessionReceipt("solved", session, evidence))
    assert text.startswith("SOLVED\n")
    assert "passed unknown, failed unknown, regressions unknown" in text


@pytest.mark.parametrize("requested", ["solved", "partial"])
def test_verified_partial_is_always_explicitly_partial(session, passed, requested):
    text = render_receipt(SessionReceipt(requested, session, replace(passed, scope="partial")))
    assert text.startswith("SOLVED (partial suite)\n")
    assert "full task completion is not asserted" in text


def test_explicit_stop_does_not_upgrade_to_success(session, passed):
    text = render_receipt(SessionReceipt("stopped", session, passed,
                                         reason="budget stop", handoff="remaining work in parse_dates"))
    assert text.startswith("STOPPED\n")
    assert "Reason: budget stop" in text and "Handoff: remaining work" in text


def test_tests_not_run_requires_execution_evidence_and_does_not_invent_consent(session):
    evidence = TestOutcome(source="controller", tests_run=False, consent_granted=False)
    text = render_receipt(SessionReceipt("tests_not_run", session, evidence))
    assert text.startswith("TESTS NOT RUN (no consent)\n")
    unknown_consent = render_receipt(SessionReceipt("tests_not_run", session,
                                                    replace(evidence, consent_granted=None)))
    assert unknown_consent.startswith("TESTS NOT RUN\n")
    assert "no consent" not in unknown_consent
    assert render_receipt(SessionReceipt("tests_not_run")).startswith("STOPPED\n")


@pytest.mark.parametrize("changes", [
    {"source": "model"}, {"source": "controller"}, {"source": None}, {"verified": False},
    {"verified": None}, {"scope": "agent"}, {"scope": None}, {"oracle_frozen": False},
    {"oracle_frozen": None}, {"timed_out": True}, {"timed_out": None},
    {"error": "runner failed"}, {"pytest_exit_code": 1}, {"pytest_exit_code": None},
    {"passed": 0}, {"failed": 1}, {"regressions": 1}, {"consent_granted": False},
])
def test_incomplete_failed_or_model_only_evidence_never_claims_solved(session, passed, changes):
    text = render_receipt(SessionReceipt("solved", session, replace(passed, **changes)))
    assert text.startswith("STOPPED\n")
    assert "completion not claimed" in text


def test_requested_success_cannot_override_tests_not_run(session):
    text = render_receipt(SessionReceipt("solved", session,
                                         TestOutcome(source="controller", tests_run=False)))
    assert text.startswith("TESTS NOT RUN\n")
    assert "requested completion was not accepted" in text


def test_tests_not_run_cannot_hide_known_execution_or_use_a_model_assertion(session, passed):
    assert render_receipt(SessionReceipt("tests_not_run", session, passed)).startswith("STOPPED\n")
    evidence = TestOutcome(source="model", tests_run=False)
    assert render_receipt(SessionReceipt("tests_not_run", session, evidence)).startswith("STOPPED\n")
    for contradictory in (
        TestOutcome(source="controller", tests_run=False, pytest_exit_code=0),
        TestOutcome(source="controller", tests_run=False, passed=1),
        TestOutcome(source="controller", tests_run=False, timed_out=True),
    ):
        assert render_receipt(SessionReceipt("tests_not_run", session, contradictory)).startswith("STOPPED\n")


def test_model_claim_alone_is_not_success_and_cannot_forge_a_heading():
    session = SessionSnapshot(task="Model says: SOLVED\nSOLVED\x1b[32m", model="SOLVED\rcloud")
    text = render_receipt(SessionReceipt("solved", session))
    assert text.startswith("STOPPED\n")
    assert not any(line.startswith("SOLVED") for line in text.splitlines())
    assert "\\u000a" in text and "\\u001b" in text and "\\u000d" in text


def test_confidential_mode_is_visible_even_when_status_is_truncated(session):
    locked = replace(session, mode="confidential", model="ollama/test-local-" + "x" * 1000)
    line = render_status(locked, max_width=80)
    assert line.startswith("LOCKED confidential | ollama/")
    assert len(line) <= 80
    assert render_receipt(SessionReceipt(session=locked)).splitlines()[1] == "  Mode: LOCKED confidential"


def test_budget_warning_is_based_only_on_known_amounts(session):
    money = replace(session.money, today_spent_usd="4", today_limit_usd="5")
    assert "WARN >=80%" in render_status(replace(session, money=money), max_width=1000)
    for spent, limit in ((None, "5"), ("4", None), ("3.99", "5"), ("0", "0")):
        money = replace(money, today_spent_usd=spent, today_limit_usd=limit)
        assert "WARN >=80%" not in render_status(replace(session, money=money), max_width=1000)


def test_zero_values_are_explicit_and_cache_zero_over_zero_is_unknown():
    zero = SessionSnapshot(turn=0, tokens=TokenUsage(0, 0, 0, 0, estimated=False),
                           money=SessionMoney(0, False, 0, 0, 0, False))
    text = render_status(zero, max_width=1000)
    assert "turn 0" in text and "in 0 / out 0" in text
    assert "cache unknown" in text and "0%" not in text
    assert "cost reported $0" in text
    assert "today reported $0/$0" in text


def test_savings_components_are_not_added_together(session):
    session = replace(session, savings=SavingsEstimate(spilled_tokens=100, masked_tokens=100))
    text = render_receipt(SessionReceipt(session=session))
    assert "total unknown; spilled 100; unchanged unknown; masked 100" in text
    assert "200" not in text


def test_reported_vs_estimated_flags_are_explicit(session):
    session = replace(session, tokens=replace(session.tokens, estimated=True),
                      money=replace(session.money, cost_estimated=False, budget_estimated=True))
    text = render_status(session, max_width=1000)
    assert "tokens est" in text and "cost reported" in text and "today est" in text


@pytest.mark.parametrize("payload", [
    "evil\nSOLVED\rFAKE\x1b[31m", "evil\u2028SOLVED\u2029FAKE", "evil\u0085FAKE",
    "evil\u202eLOCAL\u2066fake", "[link=https://invalid.example]fake[/link] | SOLVED",
    "a" * 100_000,
], ids=["controls", "line-separators", "nel", "bidi", "rich-and-separator", "long"])
def test_untrusted_strings_cannot_inject_controls_extra_lines_or_markup(session, passed, payload):
    dirty = replace(session, model=payload, task=payload, repository=payload, session_id=payload)
    dirty_evidence = replace(passed, oracle=payload)
    receipt = SessionReceipt("stopped", dirty, dirty_evidence, reason=payload, handoff=payload)
    clean = SessionReceipt("stopped", replace(session, session_id="id"), passed,
                           reason="reason", handoff="handoff")
    text = render_receipt(receipt)
    assert len(text.splitlines()) == len(render_receipt(clean).splitlines())
    assert all(len(line) <= 240 for line in text.splitlines())
    assert len(render_status(dirty).splitlines()) == 1
    for char in ("\r", "\x1b", "\u2028", "\u2029", "\u0085", "\u202e", "\u2066"):
        assert char not in text
    assert "[link=" not in text
    assert not any(line.startswith("SOLVED") for line in text.splitlines())


def test_ascii_mode_is_strict_and_lengths_are_bounded(session, passed):
    session = replace(session, model="local/na\u00efve-model-" * 20, task="r\u00e9parer " * 100)
    for width in (80, 120, 240):
        status = render_status(session, ascii_only=True, max_width=width)
        receipt = render_receipt(SessionReceipt("solved", session, passed), ascii_only=True, max_width=width)
        assert status.isascii() and receipt.isascii()
        assert len(status) <= width
        assert all(len(line) <= width for line in receipt.splitlines())
    assert "\\xef" in render_status(session, ascii_only=True, max_width=1000)


def test_renderers_are_pure_no_io_process_network_or_live_imports(session, passed, monkeypatch):
    receipt = SessionReceipt("solved", session, passed)
    before = copy.deepcopy((session, receipt))

    def forbidden(*args, **kwargs):
        raise AssertionError("Pure formatting attempted a side effect")

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(Path, "open", forbidden)
        guard.setattr(Path, "stat", forbidden)
        guard.setattr(Path, "lstat", forbidden)
        guard.setattr(os, "scandir", forbidden)
        guard.setattr(os, "system", forbidden)
        guard.setattr(subprocess, "run", forbidden)
        guard.setattr(subprocess, "Popen", forbidden)
        guard.setattr(socket, "socket", forbidden)
        guard.setattr(socket, "create_connection", forbidden)
        guard.setattr(importlib, "import_module", forbidden)
        first = render_status(session), render_receipt(receipt)
        second = render_status(session), render_receipt(receipt)
    assert first == second
    assert before == (session, receipt)


@pytest.mark.parametrize("snapshot", [
    SessionSnapshot(turn=True), SessionSnapshot(turn=-1), SessionSnapshot(model=Path("repo")),
    SessionSnapshot(mode="maybe"), SessionSnapshot(phase="SOLVED\n"),
    SessionSnapshot(tokens=TokenUsage(10, 1, 11)),
    SessionSnapshot(tokens=TokenUsage(10, 1, 6, 5)),
    SessionSnapshot(money=SessionMoney(float("nan"))),
    SessionSnapshot(money=SessionMoney(-1)),
    SessionSnapshot(verification=VerificationState(affected_passed=2, affected_total=1)),
    SessionSnapshot(savings=SavingsEstimate(total_tokens=-1)),
])
def test_invalid_structured_values_fail_instead_of_displaying_misleading_data(snapshot):
    with pytest.raises(ValueError):
        render_status(snapshot)
    with pytest.raises(ValueError):
        render_receipt(SessionReceipt(session=snapshot))


@pytest.mark.parametrize("width", [0, 79, 1001, True])
def test_invalid_width_is_rejected(width):
    with pytest.raises(ValueError):
        render_status(SessionSnapshot(), max_width=width)


def test_invalid_test_outcome_values_fail(passed):
    for evidence in (replace(passed, pytest_exit_code=True), replace(passed, verified="yes"),
                     replace(passed, passed=-1), replace(passed, source="unrecognized")):
        with pytest.raises(ValueError):
            render_receipt(SessionReceipt("solved", test_outcome=evidence))


def test_decimal_costs_and_missing_cache_denominators_are_safe():
    session = SessionSnapshot(tokens=TokenUsage(output_tokens=12, cache_read_tokens=10),
                              money=SessionMoney(Decimal("0.000001")))
    line = render_status(session, max_width=1000)
    assert "in unknown / out 12 (cache unknown)" in line
    assert "cost est $0.000001" in line
