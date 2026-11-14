"""Unit tests for prices.py and price calculations."""

from pathlib import Path
import pytest
from crocodile.gateway.prices import PriceTable, ModelPricing, PriceTier


def test_prices_yaml_loading():
    pt = PriceTable.from_yaml_file("prices.yaml")
    assert "anthropic/claude-haiku-5-5" in pt.models
    assert "openai/gpt-5-mini" in pt.models
    assert "ollama/*" in pt.models


def test_haiku_tiered_pricing():
    pt = PriceTable.from_yaml_file("prices.yaml")
    # <= 100k
    cost_low = pt.worst_in_price("anthropic/claude-haiku-5-5", 50000)
    assert pytest.approx(cost_low, 1e-9) == 0.125 / 1e6

    # > 100k
    cost_high = pt.worst_in_price("anthropic/claude-haiku-5-5", 150000)
    assert pytest.approx(cost_high, 1e-9) == 0.625 / 1e6


def test_ollama_zero_cost():
    pt = PriceTable.from_yaml_file("prices.yaml")
    cost = pt.calculate_cost(
        model_id="ollama/qwen2.5-coder:7b",
        prompt_tokens=10000,
        completion_tokens=5000,
    )
    assert cost == 0.0


def test_unpriced_model_raises():
    pt = PriceTable.from_yaml_file("prices.yaml")
    with pytest.raises(KeyError):
        pt.get_model_pricing("nonexistent/unpriced-model")
