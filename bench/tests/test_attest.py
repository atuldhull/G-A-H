"""Synthetic pre-dispatch attestation and immutable resume evidence."""

import hashlib
import json

import pytest

from bench import attest, run as runner
from bench.plan import build_plan, write_manifest
from bench.tests.test_canonical import inputs as _canonical_inputs, snapshot as _snapshot
from bench.tests.test_run import harness as _harness


@pytest.fixture
def smoke(tmp_path):
    config, data, _, _ = _canonical_inputs.__wrapped__(tmp_path, _snapshot.__wrapped__())
    config_path = tmp_path / "synthetic-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    plan = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs",
                      shard="1/4", limit=3)
    plan_path = write_manifest(plan, tmp_path / "smoke.json")
    full = json.loads((data / "oracles.json").read_text())
    subset = {task["task_id"]: full[task["task_id"]] for task in plan["tasks"]}
    return config_path, data, plan_path, subset


def test_v1_smoke_attestation_is_exactly_fifteen_slots_and_not_authorization(smoke):
    config, data, plan, subset = smoke
    result = attest.attest_plan(config, data, plan, subset)
    assert result["scope"] == "development-smoke"
    assert result["task_count"] == 3 and result["run_count"] == len(set(result["run_ids"])) == 15
    assert result["plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert result["oracle_snapshot_sha256"] == hashlib.sha256(attest.encoded(subset)).hexdigest()
    assert not result["execution_authorized"] and not result["eligible_for_pooled_report"]
    assert not result["canonical_comparability_ready"]


def test_oracle_swap_cannot_be_attested_even_if_other_file_exists(smoke):
    config, data, plan, subset = smoke
    subset[next(iter(subset))] = ["conftest.py"]
    with pytest.raises(ValueError, match="Oracle subset differs"):
        attest.attest_plan(config, data, plan, subset)


def test_canonical_gate_prevents_any_session_or_agent_dispatch(smoke, tmp_path):
    config, data, plan, subset = smoke

    def forbidden(*args, **kwargs):
        pytest.fail("Blocked canonical config must not dispatch work")

    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="comparability is blocked"):
        runner.run_plan(plan, output, oracles=subset, canonical_config=config, canonical_data_root=data,
                        agent_factory=forbidden, session_factory=forbidden)
    assert not output.exists()


def test_attestation_is_written_before_fake_dispatch_and_bound_on_resume(tmp_path, monkeypatch):
    h = _harness.__wrapped__(tmp_path, monkeypatch)
    config = tmp_path / "synthetic-ready-config.json"
    config.write_text('{"synthetic":true}', encoding="utf-8")
    # Mock only the readiness boundary. No real canonical v1 can authorize this;
    # the execution path below uses both injected fake factories, never live APIs.
    proof = {"canonical_config_id": "synthetic-test-only", "execution_authorized": True,
             "canonical_comparability_ready": True}
    monkeypatch.setattr(attest, "attest_plan", lambda *args, **kwargs: dict(proof))
    original = h.options["agent_factory"]

    def checked_agent(*args, **kwargs):
        assert (h.output / "config-attestation.json").is_file()
        assert (h.output / "canonical-config.json").read_bytes() == config.read_bytes()
        return original(*args, **kwargs)

    h.options["agent_factory"] = checked_agent
    options = dict(h.options, canonical_config=config, canonical_data_root=tmp_path)
    rows = runner.run_plan(h.path, h.output, **options)
    digest = hashlib.sha256((h.output / "config-attestation.json").read_bytes()).hexdigest()
    assert all(r["canonical_config_id"] == proof["canonical_config_id"]
               and r["config_attestation_sha256"] == digest for r in rows)
    assert runner.run_plan(h.path, h.output, **options) == rows
    with pytest.raises(ValueError, match="requires the original canonical"):
        runner.run_plan(h.path, h.output, **h.options)
    config.write_text('{"synthetic":false}', encoding="utf-8")
    with pytest.raises(ValueError, match="immutable canonical"):
        runner.run_plan(h.path, h.output, **options)


def test_cannot_add_attestation_to_an_existing_unattested_run(tmp_path, monkeypatch):
    h = _harness.__wrapped__(tmp_path, monkeypatch)
    runner.run_plan(h.path, h.output, **h.options)
    config = tmp_path / "synthetic.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(attest, "attest_plan", lambda *args, **kwargs: {
        "canonical_config_id": "synthetic", "execution_authorized": True,
        "canonical_comparability_ready": True})
    with pytest.raises(ValueError, match="retroactively"):
        runner.run_plan(h.path, h.output, **h.options, canonical_config=config, canonical_data_root=tmp_path)


def test_effective_mini_identity_cannot_use_a_different_endpoint(smoke):
    from bench.mini import MiniAdapter, Settings
    config, data, plan, subset = smoke
    identity = MiniAdapter(Settings("Synthetic-Ubuntu", "/fake/python")).identity()
    result = attest.attest_plan(config, data, plan, subset, mini_identity=identity)
    assert result["effective_mini_identity"] == identity and not result["reviewed_mini_header_supplied"]
    with pytest.raises(ValueError, match="identity fields"):
        attest.attest_plan(config, data, plan, subset, mini_identity=dict(identity, api_key="SYNTHETIC"))
    identity["settings"]["api_base"] = "http://127.0.0.1:8080/v1"
    with pytest.raises(ValueError, match="Effective mini identity differs"):
        attest.attest_plan(config, data, plan, subset, mini_identity=identity)
