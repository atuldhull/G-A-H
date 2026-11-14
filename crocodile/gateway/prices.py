"""Model pricing tables and tier evaluation.

Defines Pydantic models for prices.yaml and helper functions to compute
token costs across standard, cached, and tiered models.
Prices in prices.yaml are expressed in USD per 1,000,000 (1M) tokens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel, Field, model_validator


class PriceTier(BaseModel):
    """A pricing tier based on input token counts."""

    upto: int | None = None  # None indicates unbounded/highest tier
    in_: float = Field(..., alias="in")
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None
    cache_read: float = 0.0
    out: float = 0.0

    model_config = {"populate_by_name": True}


class ModelPricing(BaseModel):
    """Pricing configuration for a single model."""

    tiers: list[PriceTier]
    max_out: int = 4096

    @model_validator(mode="after")
    def validate_tiers(self) -> "ModelPricing":
        if not self.tiers:
            raise ValueError("Model must have at least one pricing tier")
        return self

    def tier_for(self, prompt_tokens: int | None) -> PriceTier:
        """Find the pricing tier matching prompt_tokens; unknown count defaults to highest tier."""
        if prompt_tokens is None:
            # Unknown count -> highest tier (last one or one with upto=None)
            for tier in reversed(self.tiers):
                if tier.upto is None:
                    return tier
            return self.tiers[-1]

        for tier in self.tiers:
            if tier.upto is None or prompt_tokens <= tier.upto:
                return tier
        return self.tiers[-1]


class PriceTable(BaseModel):
    """Global price table mapping model IDs to ModelPricing."""

    models: dict[str, ModelPricing]

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> "PriceTable":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Prices file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        
        parsed_models: dict[str, ModelPricing] = {}
        for model_id, model_data in raw.items():
            if isinstance(model_data, dict):
                parsed_models[model_id] = ModelPricing.model_validate(model_data)
        return cls(models=parsed_models)

    def get_model_pricing(self, model_id: str) -> ModelPricing:
        """Get model pricing, matching exact model name or glob like 'ollama/*'."""
        if model_id in self.models:
            return self.models[model_id]
        
        # Check wildcard matches like ollama/*
        for pattern, pricing in self.models.items():
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if model_id.startswith(prefix + "/") or model_id == prefix:
                    return pricing
            elif pattern == "*":
                return pricing

        raise KeyError(f"Model '{model_id}' is unpriced in prices.yaml")

    def worst_in_price(self, model_id: str, prompt_tokens: int | None) -> float:
        """Worst-case price per token for input (including cache write premium)."""
        pricing = self.get_model_pricing(model_id)
        tier = pricing.tier_for(prompt_tokens)
        cw = tier.cache_write_5m if tier.cache_write_5m is not None else tier.in_
        worst_per_million = max(tier.in_, cw)
        return worst_per_million / 1_000_000.0

    def out_price(self, model_id: str, prompt_tokens: int | None) -> float:
        """Price per token for output."""
        pricing = self.get_model_pricing(model_id)
        tier = pricing.tier_for(prompt_tokens)
        return tier.out / 1_000_000.0

    def calculate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_write_ttl: str = "5m",
    ) -> float:
        """Calculate exact USD cost for a completed model invocation."""
        pricing = self.get_model_pricing(model_id)
        tier = pricing.tier_for(prompt_tokens)

        # Uncached tokens: prompt_tokens includes cached reads and writes in Bifrost
        uncached_in = max(0, prompt_tokens - cache_read_tokens - cache_write_tokens)
        
        write_rate = tier.cache_write_1h if (cache_write_ttl == "1h" and tier.cache_write_1h is not None) else (
            tier.cache_write_5m if tier.cache_write_5m is not None else tier.in_
        )

        in_cost = (uncached_in * tier.in_) / 1_000_000.0
        read_cost = (cache_read_tokens * tier.cache_read) / 1_000_000.0
        write_cost = (cache_write_tokens * write_rate) / 1_000_000.0
        out_cost = (completion_tokens * tier.out) / 1_000_000.0

        return in_cost + read_cost + write_cost + out_cost
