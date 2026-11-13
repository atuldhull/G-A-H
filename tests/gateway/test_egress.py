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
