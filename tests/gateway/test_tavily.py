"""Tests for Tavily search helper and safety gating."""

import pytest
from crocodile.gateway.tavily import (
    TavilyDeny,
    build_tavily_request,
    parse_tavily_response,
    sanitize_query,
)


def test_tavily_query_sanitization():
    raw = "How to parse json in python? CANARY-12345678"
    clean = sanitize_query(raw, canaries=["CANARY-12345678"])
    assert "[CANARY_REDACTED]" in clean
    assert "CANARY-12345678" not in clean


def test_build_tavily_request():
    url, headers, payload = build_tavily_request(
        query="fastapi lifespan example",
        api_key="tvly-mock-key",
        domains=["fastapi.tiangolo.com"],
    )
    assert url == "https://api.tavily.com/search"
    assert headers["Authorization"] == "Bearer tvly-mock-key"
    assert payload["search_depth"] == "basic"
    assert payload["max_results"] == 3
    assert payload["include_domains"] == ["fastapi.tiangolo.com"]
    assert payload["include_domains_mode"] == "restrict"


def test_parse_tavily_response():
    data = {
        "query": "fastapi",
        "results": [
            {"title": "Doc 1", "url": "https://fastapi.com", "content": "Useful info"},
            {"title": "Doc 2", "url": "https://fastapi.com/2", "content": "More info"},
        ],
        "usage": {"credits": 1},
    }
    result = parse_tavily_response(data)
    assert len(result.results) == 2
    assert result.credits_used == 1
