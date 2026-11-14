"""The optional owner-approved guard covers every budget transaction without changing arithmetic."""

import sqlite3

import pytest

from crocodile.gateway.budget import BudgetManager, Denied
from crocodile.gateway.prices import PriceTable
from crocodile.security.integrity import IntegrityViolation


def test_transactional_guard_preserves_seal(app_security):
    manager = BudgetManager(
        app_security.path,
        PriceTable.from_yaml_file("prices.yaml"),
        limits={"fixture": 1},
        state_integrity=app_security,
    )

    def reserve():
        return manager.reserve("fixture", ["anthropic/claude-haiku-5-5"], prompt_text="fixture")

    first = reserve()
    app_security.verify_state()
    manager.heartbeat(first.id)
    app_security.verify_state()
    actual = manager.reconcile(first, "anthropic/claude-haiku-5-5", prompt_tokens=100, completion_tokens=10)
    assert actual > 0
    app_security.verify_state()
    second = reserve()
    manager.cancel(second)
    app_security.verify_state()
    spent, held = manager.get_window_spend("fixture")
    assert spent == pytest.approx(actual) and held == 0
    manager.limits["fixture"] = 0
    with pytest.raises(Denied):
        reserve()
    app_security.verify_state()
    with sqlite3.connect(app_security.path) as db:
        db.execute("UPDATE ledger SET reserved_usd=999")
    with pytest.raises(IntegrityViolation):
        reserve()


def test_failed_guard_rolls_back_entire_owner_write(app_security):
    manager = BudgetManager(
        app_security.path, PriceTable.from_yaml_file("prices.yaml"), state_integrity=app_security
    )
    db = manager._get_connection()
    try:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            with manager._transaction(db):
                db.execute("INSERT INTO grants VALUES ('fixture','[]')")
                raise RuntimeError("synthetic failure")
        assert db.execute("SELECT COUNT(*) FROM grants").fetchone()[0] == 0
        app_security.verify_state()
    finally:
        db.close()
