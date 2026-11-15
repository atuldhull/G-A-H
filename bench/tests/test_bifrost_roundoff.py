"""Synthetic binary64 cost shapes; no measured charges or live database access."""

from decimal import Decimal
from fractions import Fraction
import math

import pytest

from bench.bifrost_export import _bytes, _compare, _json, _same_logged_cost
from bench.tests.test_bifrost_export import sample as _sample, insert, export


@pytest.fixture
def sample(tmp_path):
    return _sample.__wrapped__(tmp_path)


def rounded_row(sample, index):
    """Vary count/cache magnitudes and rounding direction across fourteen shapes."""
    row = sample["row"]
    usage = _json(row["token_usage"].encode())
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_read_tokens"):
        row[key] *= index
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        usage[key] *= index
    usage["prompt_tokens_details"]["cached_tokens"] *= index
    incoming = usage["cost"]["input_cost"] * index
    outgoing = usage["cost"]["output_cost"] * index
    exact = incoming + outgoing
    logged = Decimal(str(math.nextafter(float(exact), math.inf if index % 2 else -math.inf)))
    assert incoming + outgoing != logged
    usage["cost"] = {"input_cost": incoming, "output_cost": outgoing, "total_cost": logged}
    row.update(cost=str(logged), token_usage=_bytes(usage).decode())
    sample["receipt"]["cost_usd"] *= index
    return exact


@pytest.mark.parametrize("index", range(1, 15), ids=lambda i: f"synthetic-row-shape-{i:02d}")
def test_fourteen_roundoff_shapes_keep_raw_sqlite_and_exact_token_price(sample, index):
    exact = rounded_row(sample, index)
    insert(sample)
    original = sample["db"].read_bytes()
    raw_usage = sample["row"]["token_usage"]
    result = export(sample)
    assert result["complete"], result["issues"]
    assert result["computed_cost_usd"] == Fraction(exact)
    assert not result["receipt_comparison"]["above_one_percent"]
    assert sample["db"].read_bytes() == original and sample["row"]["token_usage"] == raw_usage
    assert result["session"]["requests"][0]["usage"] == {
        "uncached_input": 70 * index, "cache_read_input": 30 * index,
        "cache_write_input": 0, "output": 20 * index}


def test_scalar_and_json_rendering_difference_is_bounded_too(sample):
    rounded_row(sample, 1)
    sample["row"]["cost"] = str(math.nextafter(float(sample["row"]["cost"]), math.inf))
    insert(sample)
    assert export(sample)["complete"]


@pytest.mark.parametrize("field", ["component", "scalar"])
def test_material_component_mismatch_below_one_percent_still_fails(sample, field):
    row = sample["row"]
    usage = _json(row["token_usage"].encode())
    exact = Decimal(row["cost"])
    wrong = exact + Decimal("0.0000001")
    assert not _compare(wrong, Fraction(exact))["above_one_percent"]  # Separate price rule.
    if field == "component":
        usage["cost"]["input_cost"] += wrong - exact
        row["token_usage"] = _bytes(usage).decode()
    else:
        row["cost"] = str(wrong)
    insert(sample)
    result = export(sample)
    assert not result["complete"] and result["session"] is None and result["computed_cost_usd"] is None
    assert "inconsistent_logged_cost" in result["issues"]


def test_precision_bounds_have_no_absolute_floor_or_relative_growth_loophole():
    one = Fraction(1)
    ulp = Fraction.from_float(math.ulp(1.0))
    assert _same_logged_cost(one, one + 8 * ulp)
    assert not _same_logged_cost(one, one + 9 * ulp)
    big = Fraction(1_000_000)
    assert _same_logged_cost(big, big + Fraction(1, 10**12))
    assert not _same_logged_cost(big, big + Fraction(2, 10**12))
    assert not _same_logged_cost(Fraction(0), Fraction(1, 10**30))
    assert not _same_logged_cost(Fraction(1, 10**320), Fraction(1, 10**320) + Fraction(1, 10**324))
    assert not _same_logged_cost(Fraction(10**400), Fraction(10**400) + 1)


@pytest.mark.parametrize("case", ["missing-cache", "missing-served", "wrong-provider", "retry", "missing-scalar"])
def test_roundoff_acceptance_cannot_override_usage_or_routing_evidence(sample, case):
    rounded_row(sample, 1)
    row = sample["row"]
    if case == "missing-cache":
        usage = _json(row["token_usage"].encode())
        del usage["prompt_tokens_details"]["cache_write_tokens"]
        row["token_usage"] = _bytes(usage).decode()
    elif case == "missing-served":
        row["served_model"] = None
    elif case == "wrong-provider":
        row["served_model"] = "other/synthetic"
    elif case == "retry":
        row["parent_request_id"] = "synthetic-parent"
    else:
        row["cached_read_tokens"] = None
    insert(sample)
    result = export(sample)
    assert not result["complete"] and result["session"] is None and result["computed_cost_usd"] is None
