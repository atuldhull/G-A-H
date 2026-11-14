"""Unit tests for BudgetManager and atomic reservations."""

import time
from pathlib import Path
import pytest
from crocodile.gateway.budget import BudgetManager, Denied, Ladder
from crocodile.gateway.prices import PriceTable


@pytest.fixture
def temp_db(tmp_path):
    return tmp_path / "test_state.db"


@pytest.fixture
def price_table():
    return PriceTable.from_yaml_file("prices.yaml")


def test_budget_reservation_and_reconcile(temp_db, price_table):
    bm = BudgetManager(temp_db, price_table, limits={"alice": 1.00})
    res = bm.reserve(
        principal="alice",
        chain=["anthropic/claude-haiku-5-5"],
        prompt_text="Solve this bug in Python",
        max_out_cap=2048,
    )
    assert res.id.startswith("res_")
    assert res.usd > 0
    assert res.principal == "alice"

    spent, held = bm.get_window_spend("alice")
    assert held == res.usd
    assert spent == 0.0

    # Reconcile actual
    actual = bm.reconcile(
        res=res,
        actual_model="anthropic/claude-haiku-5-5",
        prompt_tokens=100,
        completion_tokens=50,
    )
    assert actual > 0
    spent, held = bm.get_window_spend("alice")
    assert held == 0.0
    assert pytest.approx(spent, 1e-9) == actual


def test_budget_exhaustion_raises_denied(temp_db, price_table):
    bm = BudgetManager(temp_db, price_table, limits={"bob": 0.0001})  # Tiny limit
    with pytest.raises(Denied) as exc_info:
        bm.reserve(
            principal="bob",
            chain=["anthropic/claude-sonnet-5-5"],  # Expensive model
            prompt_text="Large prompt " * 500,
            max_out_cap=4096,
        )
    assert exc_info.value.remaining < exc_info.value.needed


def test_ladder_degradation():
    lad = Ladder(current="strong")
    assert lad.step_down() == "cheap"
    assert lad.step_down() == "local"
    assert lad.step_down() == "pause"

    # In confidential mode
    lad_conf = Ladder(is_confidential=True)
    assert lad_conf.current == "local"
    assert lad_conf.step_down() == "pause"
