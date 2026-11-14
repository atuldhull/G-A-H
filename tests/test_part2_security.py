"""Real seals/transactions, exact destination policy and independent diagnostic fixtures."""

import concurrent.futures
import hashlib
import json
import sqlite3
import sys

import httpx
import pytest

from crocodile.gateway.budget import BudgetManager
from crocodile.gateway.diagnostics import ProbeUnavailable, collect_evidence
from crocodile.gateway.egress import EgressClient, network_scope
from crocodile.gateway.network_policy import DestinationDenied, NetworkPolicy
from crocodile.gateway.prices import PriceTable
from crocodile.gateway.records import read_gateway_records
from crocodile.security.audit import audit_records
from crocodile.security.integrity import IntegrityViolation


def manager(state):
    return BudgetManager(state.path, PriceTable.from_yaml_file("prices.yaml"), state_integrity=state)


def test_no_integrity_opt_out_or_blind_enrollment(tmp_path):
    budget = BudgetManager(tmp_path / "fresh.db", PriceTable.from_yaml_file("prices.yaml"))
    with pytest.raises(IntegrityViolation):
        budget.reserve("fixture", ["ollama/qwen2.5-coder:7b"])
    with sqlite3.connect(budget.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 0
    client = EgressClient()
    with pytest.raises(PermissionError, match="budget manager"):
        client.chat([])
    client._http_client.close()


def test_parallel_writers_and_rollback_share_seal(app_security, monkeypatch):
    budget = manager(app_security)
    owners = [budget, manager(app_security), manager(app_security), manager(app_security)]

    def write(index):
        owner = owners[index % len(owners)]
        hold = owner.reserve("parallel", ["ollama/qwen2.5-coder:7b"], session=f"s{index}")
        owner.heartbeat(hold.id)
        owner.cancel(hold)
        return hold.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(write, range(16)))  # Exceptions must fail this test.
    assert len(set(ids)) == 16
    app_security.verify_state()
    before = budget.get_window_spend("parallel")
    original = app_security._seal

    def fail(_):
        raise RuntimeError("synthetic seal failure")

    monkeypatch.setattr(app_security, "_seal", fail)
    with pytest.raises(RuntimeError, match="seal failure"):
        budget.reserve("parallel", ["ollama/qwen2.5-coder:7b"])
    monkeypatch.setattr(app_security, "_seal", original)
    app_security.verify_state()
    assert budget.get_window_spend("parallel") == before
    connection = budget._get_connection()
    try:
        assert budget.expire_dead_leases(connection) == 0
        hold = budget.reserve("expiry", ["ollama/qwen2.5-coder:7b"])
        with budget._transaction(connection):
            connection.execute("UPDATE ledger SET owner_pid=2147483647,heartbeat=0 WHERE id=?", (hold.id,))
        assert budget.expire_dead_leases(connection) == 1
    finally:
        connection.close()
    app_security.verify_state()
    with sqlite3.connect(app_security.path) as db:
        db.execute("UPDATE ledger SET reserved_usd=999")
    for operation in (
        lambda: budget.heartbeat(ids[0]),
        lambda: budget.cancel(type("R", (), {"id": ids[0]})()),
    ):
        with pytest.raises(IntegrityViolation):
            operation()


@pytest.mark.parametrize(
    "destination",
    [
        "https://example.invalid",
        "http://127.0.0.1:9999",
        "http://127.0.0.1:8080@evil.invalid",
        "http://127.0.0.1:8080?redirect=x",
        "http://127.0.0.1:8080/remote",
    ],
)
def test_confidential_destination_denied_before_transport(app_security, destination):
    client = EgressClient(destination, budget_manager=manager(app_security))
    calls = []
    client._http_client = httpx.Client(
        transport=httpx.MockTransport(lambda req: calls.append(req) or httpx.Response(200))
    )
    with pytest.raises(DestinationDenied):
        client.chat([], session="s", mode="confidential", vk_alias="local", chain=["ollama/qwen2.5-coder:7b"])
    assert calls == []
    client._http_client.close()


def test_socket_guard_exact_pairs_and_modes():
    client = EgressClient()
    with network_scope(
        client.network_policy, "http://127.0.0.1:8080", mode="confidential", service="gateway"
    ):
        sys.audit("socket.connect", object(), ("127.0.0.1", 8080))
        for address in (("127.0.0.1", 8081), ("127.0.0.1", 11434), ("203.0.113.1", 443)):
            with pytest.raises(DestinationDenied):
                sys.audit("socket.connect", object(), address)
    with pytest.raises(DestinationDenied):
        with network_scope(
            client.network_policy, "https://api.tavily.com:443", mode="confidential", service="public"
        ):
            pytest.fail("public service entered confidential scope")
    with pytest.raises(DestinationDenied):
        sys.audit("socket.connect", object(), ("127.0.0.1", 9999))
    client._http_client.close()


def test_real_local_endpoint_and_wrong_port():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    origin = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = EgressClient(origin, network_policy=NetworkPolicy(gateways=(origin,)))
    try:
        assert client.probe(origin, "/health")[0] == 200
        with pytest.raises(DestinationDenied):
            client.probe(f"http://127.0.0.1:{server.server_port + 1}", "/health")
        assert calls == ["/health"]
    finally:
        client._http_client.close()
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_public_service_scope_pins_dns_and_port(monkeypatch):
    import crocodile.gateway.egress as module

    client = EgressClient()
    monkeypatch.setattr(
        module.socket, "getaddrinfo", lambda *_args, **_kw: [(2, 1, 6, "", ("203.0.113.8", 443))]
    )
    with network_scope(client.network_policy, "https://api.tavily.com:443", mode="public", service="public"):
        sys.audit("socket.connect", object(), ("203.0.113.8", 443))
        for pair in (("203.0.113.8", 80), ("203.0.113.9", 443)):
            with pytest.raises(DestinationDenied):
                sys.audit("socket.connect", object(), pair)
    client._http_client.close()


def test_sent_request_matches_independent_gateway_records(app_security, tmp_path):
    budget = manager(app_security)
    client = EgressClient(budget_manager=budget)
    records = []

    def gateway(request):
        body = json.loads(request.content)
        records.append(
            dict(
                request_id=request.headers["x-crocodile-request-id"],
                session=request.headers["x-bf-session-id"],
                gateway_request_id="gateway-fixture",
                provider="ollama",
                model="qwen2.5-coder:7b",
                model_requested=body["model"],
                fallbacks=body["fallbacks"],
                vk_alias="local",
                payload_sha256=hashlib.sha256(request.content).hexdigest(),
                payload_bytes=len(request.content),
            )
        )
        return httpx.Response(
            200,
            json={"model": "qwen2.5-coder:7b", "choices": [], "usage": {}},
            headers={"x-bifrost-provider": "ollama", "x-bifrost-request-id": "gateway-fixture"},
        )

    client._http_client = httpx.Client(transport=httpx.MockTransport(gateway))
    for _ in range(2):
        client.chat(
            [{"role": "user", "content": "synthetic"}],
            session="s",
            mode="confidential",
            vk_alias="local",
            chain=["ollama/qwen2.5-coder:7b"],
        )
    with sqlite3.connect(app_security.path) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("SELECT * FROM egress")]
    assert len({row["request_id"] for row in rows}) == 2

    def audit(logs):
        return audit_records(
            rows, allowlist=["qwen2.5-coder:7b"], gateway_logs=logs, session_modes={"s": "confidential"}
        )

    assert audit(records).status == "PASS"
    assert audit([]).status == "FAIL"
    rows[0]["evidence_version"] = 1
    incomplete = [dict(record) for record in records]
    del incomplete[0]["session"]
    assert audit(incomplete).status == "INCOMPLETE"
    for field, wrong in (
        ("provider", "openai"),
        ("session", "other"),
        ("payload_sha256", "0" * 64),
        ("payload_bytes", 0),
        ("model", "other"),
        ("gateway_request_id", "wrong"),
    ):
        changed = [dict(record) for record in records]
        changed[0][field] = wrong
        assert audit(changed).status == "FAIL", field
    export = tmp_path / "gateway.jsonl"
    export.write_text("\n".join(json.dumps({**r, "authorization": "must-not-retain"}) for r in records))
    assert all("authorization" not in r for r in read_gateway_records(export))
    client._http_client.close()


def test_response_breach_stays_sent_and_retry_revalidates(app_security):
    from crocodile.gateway.local import ConfidentialDeny

    client = EgressClient(budget_manager=manager(app_security))
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(
            200, json={"model": "openai/other", "choices": []}, headers={"x-bifrost-provider": "openai"}
        )

    client._http_client = httpx.Client(transport=httpx.MockTransport(response))
    for destination in ("http://127.0.0.1:8080", "https://example.invalid"):
        client.bifrost_base_url = destination
        with pytest.raises((ConfidentialDeny, DestinationDenied)):
            client.chat(
                [], session="s", mode="confidential", vk_alias="local", chain=["ollama/qwen2.5-coder:7b"]
            )
    assert len(calls) == 1
    with sqlite3.connect(app_security.path) as db:
        assert db.execute("SELECT verdict,provider_actual FROM egress").fetchall() == [("sent", "openai")]
    client._http_client.close()


def test_gateway_metadata_projection_keeps_actual_provider(tmp_path):
    from crocodile.gateway.records import main

    record = {
        "id": "gateway-id",
        "provider": "openai",
        "model": "actual-model",
        "authorization": "never-export",
        "metadata": {
            "crocodile-request-id": "client-id",
            "crocodile-session": "s",
            "crocodile-vk-alias": "local",
            "crocodile-model-requested": "ollama/qwen2.5-coder:7b",
            "crocodile-fallbacks": "[]",
            "crocodile-payload-sha256": "a" * 64,
            "crocodile-payload-bytes": "5",
        },
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps([record]))
    output = tmp_path / "safe.json"
    repo = tmp_path / "repo"
    repo.mkdir()
    assert main(["--input", str(source), "--output", str(output), "--repo", str(repo)]) == 0
    rows = json.loads(output.read_text())
    assert rows[0]["provider"] == "openai" and rows[0]["request_id"] == "client-id"
    assert "never-export" not in output.read_text()


def config():
    return {
        "bifrost": {"base_url": "http://127.0.0.1:8080"},
        "confidential": {"ollama_host": "http://127.0.0.1:11434"},
        "models": {"local": {"chain": ["ollama/qwen2.5-coder:7b"]}},
    }


@pytest.mark.parametrize(
    "failing",
    [
        None,
        "gateway reachability",
        "gateway authentication",
        "gateway probe",
        "Ollama availability",
        "Ollama probe",
        "limits permissions",
        "socket guard",
    ],
)
def test_live_probe_adapter_dependencies_independent(tmp_path, failing, monkeypatch, app_security):
    settings = config()
    log = tmp_path / "gateway.jsonl"
    client = EgressClient()
    secret = "vk-SYNTHETIC-NOT-A-CREDENTIAL"

    def handler(req):
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        if req.url.path == "/health":
            return httpx.Response(503 if failing == "gateway reachability" else 200, json={})
        if req.url.path == "/api/tags":
            return httpx.Response(
                503 if failing == "Ollama availability" else 200,
                json={"models": [{"name": "qwen2.5-coder:7b", "digest": "a" * 64, "size": 1}]},
            )
        if req.url.path == "/api/show":
            return httpx.Response(
                503 if failing == "Ollama probe" else 200, json={"model_info": {"architecture": "qwen2"}}
            )
        if "x-bf-vk" not in req.headers:
            return httpx.Response(200 if failing == "gateway authentication" else 401, json={})
        code = 200 if failing == "gateway probe" else 403
        log.write_text(
            json.dumps(
                [{"request_id": req.headers["x-crocodile-request-id"], "provider_calls": 0, "status": code}]
            )
        )
        return httpx.Response(code, json={})

    client._http_client = httpx.Client(transport=httpx.MockTransport(handler))
    if failing == "socket guard":
        monkeypatch.setattr(sys, "audit", lambda *_: None)
    evidence = collect_evidence(
        settings,
        client=client,
        local_key=secret,
        gateway_log=log,
        limits_path="fixture",
        acl_probe=lambda _: (True, failing == "limits permissions"),
    )
    for name, status in evidence["probe_status"].items():
        assert status == ("FAIL" if name == failing else "OK"), (name, status)
    assert secret not in json.dumps(evidence)
    from crocodile.security import ApprovalSession
    from crocodile.security.doctor import diagnose

    settings["models"].update(cheap={"chain": ["openai/test"]}, strong={"chain": ["openai/test"]})
    settings["models"]["local"]["ctx_window"] = 32768
    settings["confidential"]["local_model_allowlist"] = ["qwen2.5-coder:7b"]
    root = tmp_path / "repo"
    root.mkdir()
    sec = ApprovalSession(root, integrity=app_security)
    monkeypatch.setattr("crocodile.security.doctor.resolve_pinned", lambda *_: sys.executable)
    prices = {
        model: {"tiers": [{"upto": None, "in": 0, "cache_read": 0, "out": 0}]}
        for model in ("openai/test", "ollama/*")
    }
    report = diagnose(
        session=sec,
        config=settings,
        prices=prices,
        evidence=evidence,
        environment={"OLLAMA_CONTEXT_LENGTH": "32768", "OLLAMA_NO_CLOUD": "1"},
    )
    assert report.passed == (failing is None), report.render()
    assert secret not in report.render()
    if failing:
        assert any(check.name == failing and check.status == "FAIL" for check in report.checks)
    missing = collect_evidence(
        settings, client=client, acl_probe=lambda _: (_ for _ in ()).throw(ProbeUnavailable())
    )
    assert missing["probe_status"]["gateway probe"] == "INCOMPLETE"
    assert missing["probe_status"]["limits permissions"] == "INCOMPLETE"
    incomplete = diagnose(
        session=sec,
        config=settings,
        prices=prices,
        evidence=missing,
        environment={"OLLAMA_CONTEXT_LENGTH": "32768", "OLLAMA_NO_CLOUD": "1"},
    )
    assert not incomplete.passed and "INCOMPLETE gateway probe" in incomplete.render()
    client._http_client.close()
