"""Adapters to Part 2 (gateway) and Part 3 (security). Skipped when those parts are not merged."""

import sys
from unittest.mock import patch

import pytest

from crocodile.agent_types import Action, BudgetStop, Session


def _session(tmp_path, **kw):
    return Session(id="s1", repo=tmp_path, mode="public", **kw)


def test_gateway_egress_maps_result_and_budget(tmp_path, monkeypatch):
    pytest.importorskip("crocodile.gateway.egress")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    from crocodile.adapters import GatewayEgress  # noqa: I001  (gateway is first-party once merged)
    from crocodile.gateway.budget import Denied

    eg = GatewayEgress()
    body = {"model": "anthropic/claude-haiku-5-5",
            "choices": [{"message": {"content": "PLAN: x", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"path": "a.py"}'}}]}}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 30,
                      "prompt_tokens_details": {"cached_read_tokens": 1000}}}  # Part 2 field name
    monkeypatch.setattr(eg.client, "post_bifrost", lambda **kw: (200, body, {}))
    r = eg.chat([{"role": "user", "content": "hi"}], [], session=_session(tmp_path), tier="cheap")
    assert r.tool_calls[0].name == "read" and r.tool_calls[0].arguments == {"path": "a.py"}
    assert (r.usage.prompt_tokens, r.usage.completion_tokens, r.usage.cached_tokens) == (1200, 30, 1000)
    assert r.model_used == "anthropic/claude-haiku-5-5" and r.cost_usd is not None

    def deny(**kw):
        raise Denied(remaining=0.001, needed=0.05)
    monkeypatch.setattr(eg.client.budget_manager, "reserve", deny)
    with pytest.raises(BudgetStop):
        eg.chat([{"role": "user", "content": "hi"}], [], session=_session(tmp_path), tier="cheap")


def test_security_bridge_permit_flows_into_cmd(tmp_path):
    pytest.importorskip("crocodile.security.approvals")
    from crocodile.adapters import SecurityBridge
    from crocodile.security import approvals

    b = SecurityBridge()
    s = _session(tmp_path)
    argv = [sys.executable, "-c", "print('hello')"]
    with patch.object(approvals, "_console_answer", return_value="y"):
        d = b.ask(Action(kind="shell", summary="run", argv=argv), s)
    assert d.approved
    r = b.run(argv, tmp_path, timeout=30)            # consumes the single-use permit
    assert r.exit_code == 0 and "hello" in r.stdout
    with patch.object(approvals, "_console_answer", return_value="n"):
        d2 = b.ask(Action(kind="shell", summary="run", argv=argv), s)
    assert not d2.approved


def test_security_bridge_auto_mode_is_bench_only(tmp_path):
    pytest.importorskip("crocodile.security.approvals")
    from crocodile.adapters import SecurityBridge

    b = SecurityBridge()
    s = _session(tmp_path, approve_mode="auto")
    argv = [sys.executable, "-c", "print(1)"]
    assert b.ask(Action(kind="shell", summary="run", argv=argv), s).approved
    assert b.run(argv, tmp_path, timeout=30).exit_code == 0


def test_gateway_egress_passes_temperature(tmp_path, monkeypatch):
    pytest.importorskip("crocodile.gateway.egress")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    from crocodile.adapters import GatewayEgress

    eg = GatewayEgress()
    if not eg._takes_temperature:
        pytest.skip("gateway without temperature support")
    seen = {}

    def post(**kw):
        seen.update(kw["body"])
        return 200, {"model": "anthropic/claude-haiku-5-5", "choices": [{"message": {"content": "ok"}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 1}}, {}
    monkeypatch.setattr(eg.client, "post_bifrost", post)
    eg.chat([{"role": "user", "content": "hi"}], [], session=_session(tmp_path), tier="cheap", temperature=0.7)
    assert seen.get("temperature") == 0.7
