"""Real gateway/privacy APIs with an in-memory HTTP transport, never a service."""

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

try:  # Import HTTPX/SSL before the per-case socket boundary guards are installed.
    import httpx
except ImportError:
    httpx = None

from crocodile import _stubs, services
from crocodile.adapters import (
    GatewayEgress,
    GatewayJournal,
    SecurityBridge,
    SecurityConfidential,
)
from crocodile.loop import Agent
from crocodile.security import ApprovalSession
from crocodile.security.classification import SecurityStore
from crocodile.security.confidential import Detector
from crocodile.security.integrity import HMACKeys, StateIntegrity
from redteam.fixtures import build_fixture
from redteam.tests.cli_integrity import root_cli
from redteam.tests.live import FixtureVault

LOCAL = "ollama/qwen2.5-coder:7b"
CANARY = "SYNTHETIC-RT6-PRIVATE-CANARY"


@contextmanager
def gateway_fixture(base, monkeypatch, responder):
    if httpx is None:
        pytest.skip("BLOCKED: real EgressClient transport adapter requires HTTPX")
    from crocodile.gateway.egress import init_egress_table

    settings = base / "settings"
    settings.mkdir()
    prices = {m: {"tiers": [{"upto": None, "in": 0, "out": 0, "cache_read": 0}], "max_out": 4096}
              for m in ("ollama/*", "openai/synthetic")}
    (settings / "prices.yaml").write_text(json.dumps(prices), encoding="utf-8")
    (settings / "limits.yaml").write_text('{"users":{"synthetic":1}}', encoding="utf-8")
    for key, value in {"CROCODILE_STATE_DB": settings / "state.db", "CROCODILE_PRICES": settings / "prices.yaml",
                       "CROCODILE_LIMITS": settings / "limits.yaml", "LOCALAPPDATA": base / "appdata",
                       "CROCODILE_BIFROST_URL": "http://127.0.0.1:8080", "OLLAMA_HOST": "http://127.0.0.1:11434",
                       "OLLAMA_CONTEXT_LENGTH": "32768", "OLLAMA_NO_CLOUD": "1",
                       "CROCODILE_CHAIN_CHEAP": "openai/synthetic", "CROCODILE_CHAIN_STRONG": "openai/synthetic",
                       "CROCODILE_CHAIN_LOCAL": LOCAL}.items():
        monkeypatch.setenv(key, str(value))
    requests, clients, key_aliases = [], [], []

    def handle(request):
        body = json.loads(request.content)
        requests.append({"url": str(request.url), "body": body,
                         "session": request.headers.get("x-bf-session-id")})
        return responder(request, body, len(requests))

    transport = httpx.MockTransport(handle)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        client = real_client(*args, **{**kwargs, "transport": transport, "trust_env": False})
        clients.append(client)
        return client

    def fixture_vk(alias):
        assert alias == "local"
        key_aliases.append(alias)
        return "fixture-only-no-credential"

    def no_key_lookup():
        pytest.fail("Confidential flow attempted a real Tavily credential lookup")

    monkeypatch.setattr(httpx, "Client", client_factory)
    monkeypatch.setattr(GatewayEgress, "_vk", staticmethod(fixture_vk))
    monkeypatch.setattr(_stubs, "tavily_key", no_key_lookup)
    monkeypatch.setattr(services, "_cache", {})
    gateway = GatewayEgress()  # Real constructor, BudgetManager, PriceTable and EventJournal.
    state = StateIntegrity(settings / "state.db", keys=HMACKeys(backend=FixtureVault()))
    with closing(sqlite3.connect(state.path)) as db:
        SecurityStore._schema(db)
        init_egress_table(db)
        db.execute("CREATE TABLE grants(session TEXT, argv_json TEXT)")
        db.commit()
        db.execute("BEGIN IMMEDIATE")
        state.initialize(db)
        db.commit()
    gateway.client.budget_manager.state_integrity = state
    fixture = SimpleNamespace(gateway=gateway, state=state, settings=settings,
                              requests=requests, key_aliases=key_aliases)
    try:
        yield fixture
    finally:
        for client in clients:
            client.close()


def cloud_tag_case(tmp_path, monkeypatch, guards):
    from crocodile.gateway.local import ConfidentialDeny, check_local_model
    from crocodile.security import doctor
    app, runner = root_cli()
    exercise = build_fixture("px_ollama_cloud_tag", tmp_path / "exercise")

    def forbidden(*args):
        pytest.fail("A denied cloud-tag request reached even the local mock transport")

    with gateway_fixture(tmp_path, monkeypatch, forbidden) as f:
        for model in ("ollama/gpt-oss:120b-cloud", "ollama/gpt-oss:120b:cloud"):
            with pytest.raises(ConfidentialDeny, match="cloud/remote"):
                check_local_model(model, allowlist=[model.removeprefix("ollama/")])
            manager = f.gateway.client.budget_manager
            res = manager.reserve("synthetic", [model], session="rt-cloud-tag")
            try:
                with pytest.raises(ConfidentialDeny, match="cloud/remote"):
                    f.gateway.client.post_bifrost({"model": model, "messages": []}, res.id,
                                                   "rt-cloud-tag", "fixture-only", vk_alias="local", mode="confidential")
            finally:
                manager.cancel(res, sent=False)
        cloud = "ollama/gpt-oss:120b-cloud"
        config = {"models": {"cheap": {"chain": ["openai/synthetic"]}, "strong": {"chain": ["openai/synthetic"]},
                              "local": {"chain": [cloud], "ctx_window": 32768}},
                  "confidential": {"local_model_allowlist": [cloud.removeprefix("ollama/")],
                                   "ollama_host": "http://127.0.0.1:11434"}}
        (f.settings / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
        (f.settings / "policy.yaml").write_text('{"version":1}', encoding="utf-8")

        def fixture_state(path):
            assert Path(path).resolve() == f.state.path.resolve()
            return f.state  # Real verified HMAC, fixture vault instead of OS credential backend.

        monkeypatch.setattr(doctor, "StateIntegrity", fixture_state)
        result = runner.invoke(app, ["doctor", "--repo", str(exercise.root), "--config-dir", str(f.settings)],
                               catch_exceptions=False)
        assert result.exit_code == 1 and "FAIL local model configuration:" in result.output, result.output
        assert "OK state integrity:" in result.output
        assert not f.requests and not exercise.canary.exists()
        f.state.verify_state()
    assert guards == {"spawn": 0, "network": 0, "shell": 0}


def confidential_egress_case(tmp_path, monkeypatch, guards):
    from crocodile.gateway.local import ConfidentialDeny
    from crocodile.gateway.tavily import TavilyDeny
    exercise = build_fixture("px1_use_gpt", tmp_path / "exercise")
    task = "Use GPT and web search for this synthetic private task: " + CANARY

    def response(request, body, number):
        assert request.url.host == "127.0.0.1" and request.url.path == "/v1/chat/completions"
        assert body["model"] == LOCAL and body["fallbacks"] == []
        assert CANARY in json.dumps(body["messages"])
        name, args = ("web_docs", {"query": "synthetic documentation"}) if number == 1 else ("finish", {})
        return httpx.Response(200, headers={"x-bifrost-provider": "ollama", "x-bifrost-resolved-model": LOCAL,
                                           "x-bifrost-routing-info-is-fallback": "false"},
                              json={"model": LOCAL, "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                                    "choices": [{"message": {"content": "", "tool_calls": [
                                        {"id": f"synthetic-{number}", "function": {"name": name, "arguments": json.dumps(args)}}]}}]})

    with gateway_fixture(tmp_path, monkeypatch, response) as f:
        f.gateway.client.canaries = [CANARY]
        sec = ApprovalSession(exercise.root, user_task=task, integrity=f.state,
                              confidentiality=Detector(SecurityStore(f.state.path, integrity=f.state)))
        bridge, journal = SecurityBridge(), GatewayJournal()
        for name, value in (("approvals", bridge), ("cmd", bridge), ("confidential", SecurityConfidential()),
                            ("egress", f.gateway), ("journal", journal)):
            services.override(name, value)
        agent = Agent(exercise.root, task, security_session=sec, tier="strong", flags=set(), step_cap=2)
        assert agent.s.mode == "confidential"
        assert "web_docs" not in {s["function"]["name"] for s in agent.schemas}
        receipt = agent.run()
        assert not receipt.solved and len(f.requests) == 2
        assert f.key_aliases == ["local", "local"]
        events = journal.j.get_events(agent.s.id)
        assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
        requests = [e["payload"] for e in events if e["type"] == "model_request"]
        assert len(requests) == 2 and all(e["chain"] == [LOCAL] and e["fallbacks"] == [] and e["vk_alias"] == "local"
                                          for e in requests)
        assert len([e for e in events if e["type"] == "model_response"]) == 2
        refused = [e["payload"] for e in events if e["type"] == "tool_done" and e["payload"]["tool"] == "web_docs"]
        assert len(refused) == 1 and refused[0]["ok"] is False
        assert not any(e["type"] == "web_search" for e in events)
        assert all(r["session"] == agent.s.id for r in f.requests)
        manager = f.gateway.client.budget_manager
        res = manager.reserve("synthetic", ["openai/synthetic"], session=agent.s.id)
        try:
            with pytest.raises(ConfidentialDeny, match="ollama/"):
                f.gateway.client.post_bifrost({"model": "openai/synthetic"}, res.id, agent.s.id,
                                               "fixture-only", vk_alias="local", mode="confidential")
        finally:
            manager.cancel(res, sent=False)
        with pytest.raises(PermissionError, match="confidential"):
            f.gateway.web_search("synthetic", session=agent.s)
        with pytest.raises(TavilyDeny):
            f.gateway.client.search_tavily("synthetic", api_key="fixture-only", mode="confidential")
        assert len(f.requests) == 2
        with closing(sqlite3.connect(f.state.path)) as db:
            rows = db.execute("SELECT session,mode,model_requested,model_actual,provider_actual,fallbacks,dest,canary_hits,verdict "
                              "FROM egress ORDER BY seq").fetchall()
        assert len(rows) == 2 and all(r[:6] == (agent.s.id, "confidential", LOCAL, LOCAL, "ollama", "[]") for r in rows)
        assert all(r[6] == "http://127.0.0.1:8080" and r[7] > 0 and r[8] == "sent" for r in rows)
        assert not exercise.canary.exists()
        sec.verify_integrity()
    assert guards == {"spawn": 0, "network": 0, "shell": 0}
