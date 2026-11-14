"""A fabricated or cancelled reservation must never reach the transport."""

import httpx
import pytest

from crocodile.gateway.budget import BudgetManager
from crocodile.gateway.egress import EgressClient
from crocodile.gateway.prices import PriceTable
from crocodile.security.integrity import IntegrityViolation


def test_forged_and_cancelled_holds_rejected_before_send(app_security):
    budget = BudgetManager(
        app_security.path, PriceTable.from_yaml_file("prices.yaml"), state_integrity=app_security
    )
    client = EgressClient(budget_manager=budget)
    calls = []
    client._http_client = httpx.Client(
        transport=httpx.MockTransport(lambda req: calls.append(req) or httpx.Response(200))
    )
    hold = budget.reserve("fixture", ["ollama/qwen2.5-coder:7b"])
    budget.cancel(hold)
    try:
        for reservation in ("forged", hold.id):
            with pytest.raises(IntegrityViolation, match="held reservation"):
                client.post_bifrost({"model": "ollama/qwen2.5-coder:7b"}, reservation, "s", "synthetic-key")
        assert calls == []
        app_security.verify_state()
    finally:
        client._http_client.close()
