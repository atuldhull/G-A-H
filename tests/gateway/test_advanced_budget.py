"""Advanced budget tests covering architecture/06 requirements:
- test_tier_reserve_haiku_150k
- test_timeout_keeps_hold
- test_inflight_not_expired_by_peer
- test_clock_rollback
- test_budget_warn_80
"""

import time
from pathlib import Path
import pytest
from crocodile.gateway.budget import BudgetManager, Denied
from crocodile.gateway.prices import PriceTable


@pytest.fixture
def temp_db(tmp_path):
    return tmp_path / "adv_budget_test.db"


@pytest.fixture
def price_table():
    return PriceTable.from_yaml_file("prices.yaml")


def test_tier_reserve_haiku_150k(temp_db, price_table):
    """Verifies that prompts > 100k tokens are reserved at the higher tier ($0.50/$2.50)."""
    bm = BudgetManager(temp_db, price_table, limits={"user-tiered": 5.00})

    # 50k tokens (lower tier)
    res_low = bm.reserve(
        principal="user-tiered",
        chain=["anthropic/claude-haiku-5-5"],
        raw_token_count=50000,
        max_out_cap=1000,
    )
    # 150k tokens (higher tier: in = $0.50, cw = $0.625 per 1M, out = $2.50)
    res_high = bm.reserve(
        principal="user-tiered",
        chain=["anthropic/claude-haiku-5-5"],
        raw_token_count=150000,
        max_out_cap=1000,
    )

    rate_low = res_low.usd / (res_low.est_in + res_low.max_out)
    rate_high = res_high.usd / (res_high.est_in + res_high.max_out)

    assert rate_high > rate_low * 2, "Higher tier tokens must be priced significantly higher"


def test_timeout_keeps_hold(temp_db, price_table):
    """ADR-005: When a timeout occurs post-send, reservation stays held (cancel with sent=True)."""
    bm = BudgetManager(temp_db, price_table, limits={"user-timeout": 1.00})
    res = bm.reserve(
        principal="user-timeout",
        chain=["anthropic/claude-haiku-5-5"],
        raw_token_count=1000,
    )

    # Cancel with sent=True represents a timeout where bytes were sent to Bifrost
    bm.cancel(res, sent=True)
    spent, held = bm.get_window_spend("user-timeout")
    assert held == res.usd, "Sent-then-timeout reservation must remain held"

    # Cancel with sent=False releases immediately
    bm.cancel(res, sent=False)
    spent, held = bm.get_window_spend("user-timeout")
    assert held == 0.0, "Unsent cancelled reservation must be freed"


def test_inflight_not_expired_by_peer(temp_db, price_table):
    """Verifies that an active in-flight call (alive PID, fresh heartbeat) is never expired by a peer process."""
    bm = BudgetManager(temp_db, price_table, limits={"user-lease": 1.00})
    res = bm.reserve(
        principal="user-lease",
        chain=["anthropic/claude-haiku-5-5"],
        raw_token_count=1000,
    )

    conn = bm._get_connection()
    try:
        expired = bm.expire_dead_leases(conn)
        assert expired == 0, "Active lease should not be expired"
    finally:
        conn.close()

    spent, held = bm.get_window_spend("user-lease")
    assert held == res.usd


def test_clock_rollback(temp_db, price_table):
    """Verifies that if local clock is behind ledger window, reserve refuses (clock skew protection)."""
    bm = BudgetManager(temp_db, price_table, limits={"user-skew": 1.00})

    # First reserve on today's window
    res = bm.reserve(
        principal="user-skew",
        chain=["anthropic/claude-haiku-5-5"],
        window="2026-11-13",
    )
    assert res.id is not None

    # Try reserving with an older window (clock rollback)
    with pytest.raises(RuntimeError, match="Clock skew detected"):
        bm.reserve(
            principal="user-skew",
            chain=["anthropic/claude-haiku-5-5"],
            window="2026-11-10",
        )


def test_budget_warn_80(temp_db, price_table):
    """Verifies that is_warn_threshold_reached fires when spend+held >= 80%."""
    bm = BudgetManager(temp_db, price_table, limits={"user-warn": 1.00})
    assert bm.is_warn_threshold_reached("user-warn") is False

    # Reserve $0.85 (85% of $1.00)
    # Using sonnet-5-5 with high token count to reach >= $0.80
    res = bm.reserve(
        principal="user-warn",
        chain=["anthropic/claude-sonnet-5-5"],
        raw_token_count=100000,
        max_out_cap=60000,
    )
    assert bm.is_warn_threshold_reached("user-warn") is True
