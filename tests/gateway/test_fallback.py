"""Tests for failover detection, error classification, and takeover banner."""

from crocodile.gateway.fallback import (
    classify_error,
    parse_routing_info,
    render_takeover_banner,
)


def test_classify_error():
    assert classify_error(401, "key rejected") == "auth"
    assert classify_error(429, "rate limit exceeded") == "rate-limit"
    assert classify_error(402, "policy_budget_exceeded") == "quota"
    assert classify_error(504, "gateway timed out") == "timeout"
    assert classify_error(503, "service unavailable") == "transient"
    assert classify_error(400, "bad request") == "caller-fault"


def test_parse_routing_info_success():
    headers = {
        "x-bifrost-resolved-model": "anthropic/claude-sonnet-5-5",
        "x-bifrost-provider": "anthropic",
        "x-bifrost-routing-info-is-fallback": "false",
    }
    routing = parse_routing_info(headers, requested_model="anthropic/claude-sonnet-5-5")
    assert routing.model_used == "anthropic/claude-sonnet-5-5"
    assert routing.is_fallback is False


def test_parse_routing_info_fallback_and_banner():
    headers = {
        "x-bifrost-resolved-model": "anthropic/claude-haiku-5-5",
        "x-bifrost-provider": "anthropic",
        "x-bifrost-routing-info-is-fallback": "true",
        "x-bifrost-routing-info-primary-model": "anthropic/claude-sonnet-5-5",
        "x-bifrost-fallback-reason": "auth 401 key rejected",
    }
    routing = parse_routing_info(headers, requested_model="anthropic/claude-sonnet-5-5")
    assert routing.is_fallback is True
    assert routing.model_used == "anthropic/claude-haiku-5-5"
    assert routing.primary_model == "anthropic/claude-sonnet-5-5"
    assert routing.error_class == "auth"

    banner = render_takeover_banner(routing, journal_seq=42, cost_delta=-0.003)
    assert "MODEL TAKEOVER" in banner
    assert "anthropic/claude-sonnet-5-5 failed: auth" in banner
    assert "anthropic/claude-haiku-5-5 answered" in banner
    assert "journal seq 42" in banner
