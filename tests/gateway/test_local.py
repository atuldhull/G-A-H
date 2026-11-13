"""Tests for local routing and Ollama model safety checks."""

import pytest
from crocodile.gateway.local import (
    ConfidentialDeny,
    check_local_model,
    fit_context_or_refuse,
    is_loopback_host,
    sanitize_local_request_body,
)


def test_allowed_local_model():
    # Should not raise
    check_local_model("ollama/qwen2.5-coder:7b")
    check_local_model("ollama/qwen3-coder:30b")


def test_rejected_cloud_models():
    with pytest.raises(ConfidentialDeny, match="forbidden cloud/remote"):
        check_local_model("ollama/gpt-oss:120b-cloud")

    with pytest.raises(ConfidentialDeny, match="forbidden cloud/remote"):
        check_local_model("ollama/qwen3-coder:30b-cloud")

    with pytest.raises(ConfidentialDeny, match="forbidden cloud/remote"):
        check_local_model("ollama/custom/model")

    with pytest.raises(ConfidentialDeny, match="forbidden cloud/remote"):
        check_local_model("ollama/model@remote")


def test_unlisted_model_rejected():
    with pytest.raises(ConfidentialDeny, match="not in local allowlist"):
        check_local_model("ollama/unknown-model:latest")


def test_loopback_host_detection():
    assert is_loopback_host("http://127.0.0.1:11434") is True
    assert is_loopback_host("localhost:11434") is True
    assert is_loopback_host("http://[::1]:11434") is True
    assert is_loopback_host("http://192.168.1.50:11434") is False
    assert is_loopback_host("https://api.openai.com") is False


def test_context_window_fit():
    # Fits within 70% of 32768 (22937 tokens)
    fit_context_or_refuse(10000, ctx_window=32768, fit_frac=0.7)

    # Exceeds limit
    with pytest.raises(ConfidentialDeny, match="exceeds safe local context limit"):
        fit_context_or_refuse(25000, ctx_window=32768, fit_frac=0.7)


def test_sanitize_local_request_body():
    body = {
        "model": "ollama/qwen2.5-coder:7b",
        "fallbacks": ["openai/gpt-5-mini"],
        "messages": [
            {"role": "system", "content": "hello", "cache_control": {"type": "ephemeral"}},
            {"role": "user", "content": "test"},
        ],
    }
    sanitized = sanitize_local_request_body(body)
    assert sanitized["fallbacks"] == []
    assert "cache_control" not in sanitized["messages"][0]
