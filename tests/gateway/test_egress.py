"""Tests for EgressClient safety, canary scanning, and chat pipeline."""

from pathlib import Path
import pytest
from crocodile.gateway.budget import BudgetManager
from crocodile.gateway.egress import EgressClient, SecurityError
from crocodile.gateway.journal import EventJournal
from crocodile.gateway.local import ConfidentialDeny
from crocodile.gateway.prices import PriceTable
from crocodile.gateway.tavily import TavilyDeny


@pytest.fixture
def test_setup(tmp_path):
    db_path = tmp_path / "egress_test.db"
    pt = PriceTable.from_yaml_file("prices.yaml")
    bm = BudgetManager(db_path, pt, limits={"user1": 2.0})
    j = EventJournal(db_path)
    client = EgressClient(
        bifrost_base_url="http://127.0.0.1:8080",
        budget_manager=bm,
        journal=j,
        price_table=pt,
        canaries=["CANARY-TOP-SECRET-001"],
    )
    return client, bm, j, db_path


def test_egress_unprefixed_model_rejected(test_setup):
    client, bm, j, db_path = test_setup
    with pytest.raises(ValueError, match="provider-prefixed"):
        client.post_bifrost(
            body={"model": "gpt-4o"},
            reservation_id="res_test",
            session="s1",
            vk="vk-1",
        )


def test_egress_requires_reservation_id(test_setup):
    client, bm, j, db_path = test_setup
    with pytest.raises(PermissionError, match="requires a held reservation_id"):
        client.post_bifrost(
            body={"model": "anthropic/claude-haiku-5-5"},
            reservation_id="",  # Empty reservation
            session="s1",
            vk="vk-1",
        )


def test_egress_canary_blocks_public_send(test_setup):
    client, bm, j, db_path = test_setup
    res = bm.reserve("user1", ["anthropic/claude-haiku-5-5"], prompt_text="dummy")
    with pytest.raises(SecurityError, match="canary token"):
        client.post_bifrost(
            body={"model": "anthropic/claude-haiku-5-5", "text": "Leaking CANARY-TOP-SECRET-001 here"},
            reservation_id=res.id,
            session="s1",
            vk="vk-1",
            mode="public",
        )


def test_egress_confidential_denies_public_vk(test_setup):
    client, bm, j, db_path = test_setup
    res = bm.reserve("user1", ["ollama/qwen2.5-coder:7b"], prompt_text="dummy")
    with pytest.raises(ConfidentialDeny, match="must be 'local'"):
        client.post_bifrost(
            body={"model": "ollama/qwen2.5-coder:7b"},
            reservation_id=res.id,
            session="s1",
            vk="vk-public",
            vk_alias="public",  # Must be 'local'
            mode="confidential",
        )


def test_tavily_denied_in_confidential_mode(test_setup):
    client, bm, j, db_path = test_setup
    with pytest.raises(TavilyDeny, match="strictly forbidden in confidential mode"):
        client.search_tavily("query", api_key="tvly-mock", mode="confidential")


def test_chat_pipeline_with_mock_response(test_setup):
    client, bm, j, db_path = test_setup
    mock_resp = {
        "model": "anthropic/claude-haiku-5-5",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello! I fixed your code.",
                    "tool_calls": [],
                }
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 15,
            "total_tokens": 65,
        },
    }

    result = client.chat(
        messages=[{"role": "user", "content": "Fix code"}],
        session="s_chat",
        principal="user1",
        chain=["anthropic/claude-haiku-5-5"],
        mock_response=mock_resp,
    )

    assert result.text == "Hello! I fixed your code."
    assert result.usage.input_tokens == 50
    assert result.usage.output_tokens == 15
    assert result.cost_usd > 0


def test_chat_openai_cached_tokens(test_setup):
    """Bifrost / OpenAI returns cached tokens under prompt_tokens_details.cached_tokens."""
    client, bm, j, db_path = test_setup
    mock_resp = {
        "model": "anthropic/claude-haiku-5-5",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Cached output",
                    "tool_calls": [],
                }
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_tokens_details": {
                "cached_tokens": 80,
            },
        },
    }

    result = client.chat(
        messages=[{"role": "user", "content": "Cache test"}],
        session="s_cache",
        principal="user1",
        chain=["anthropic/claude-haiku-5-5"],
        mock_response=mock_resp,
    )

    assert result.usage.input_tokens == 100
    assert result.usage.cache_read_tokens == 80
    assert result.usage.output_tokens == 10
    # Cost with 80 cache read tokens should be strictly less than 100 uncached tokens
    uncached_100_cost = (100 * 1.0 + 10 * 5.0) / 1_000_000.0
    assert result.cost_usd < uncached_100_cost


def test_chat_temperature_and_default_chains(test_setup):
    """Temperature parameter is recorded and default tier chains are picked when chain is None."""
    client, bm, j, db_path = test_setup
    mock_resp = {
        "model": "anthropic/claude-haiku-5-5",
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    result = client.chat(
        messages=[{"role": "user", "content": "temp test"}],
        session="s_temp",
        principal="user1",
        tier="cheap",
        temperature=0.85,
        mock_response=mock_resp,
    )

    assert result.text == "ok"
    events = j.get_events("s_temp")
    req_event = [e for e in events if e.get("type") == "model_request"][0]
    assert req_event["payload"]["temperature"] == 0.85
    assert req_event["payload"]["chain"] == ["anthropic/claude-haiku-5-5", "openai/gpt-5-mini"]


def test_chat_error_response_sets_empty_model_and_error_class(test_setup):
    """When Bifrost returns an error and no choices, chat sets model_used='' and classifies error."""
    client, bm, j, db_path = test_setup
    mock_resp = {
        "error": {
            "message": "Rate limit exceeded (429)",
            "type": "requests",
        }
    }

    result = client.chat(
        messages=[{"role": "user", "content": "failing test"}],
        session="s_err",
        principal="user1",
        chain=["anthropic/claude-haiku-5-5"],
        mock_response=mock_resp,
    )

    assert result.model_used == ""
    assert result.text is None
    assert result.tool_calls == []
    assert result.error_class == "rate-limit"
    assert result.cost_usd == 0.0
