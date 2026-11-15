"""Static successor rules and historical-cohort exclusion; no work dispatched."""

from copy import deepcopy
import hashlib

import pytest

from bench import canonical
from bench.bifrost_export import NULL_MODEL_RULE, NULL_ROUTE_FIELDS, ZERO_ROUTE_FIELDS


@pytest.fixture
def v5():
    # Synthetic current-runtime snapshot; the separately published v5 is immutable.
    c = deepcopy(canonical._json(canonical.V4_CONFIG))
    c.update(schema_version=5, revision="gemini-54-v5", changes_from_v4=["Synthetic successor fixture"])
    del c["changes_from_v3"]
    for name in c["provenance"]["runtime_files_sha256_lf"]:
        c["provenance"]["runtime_files_sha256_lf"][name] = hashlib.sha256(
            (canonical.REPO_ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    c["evidence"]["null_served_model_rule"] = {
        "revision": NULL_MODEL_RULE, "required_null_columns": list(NULL_ROUTE_FIELDS),
        "required_integer_zero_columns": list(ZERO_ROUTE_FIELDS),
        "per_request_routing_join_required": True, "blanket_null_inference": False}
    c["evidence"]["reviewed_artifacts_sha256_lf"] = {
        name: hashlib.sha256((canonical.REPO_ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in ("bench/evidence/croc-native-pilot-v4-review.json", "bench/evidence/croc-native-routing-proof.json")}
    c["evidence"]["historical_pilot_report_eligible"] = False
    c["pooling"]["pre_v5_cohorts_report_eligible"] = False
    c["readiness"]["unresolved"] = [{"id": "post-restart-per-machine-cost-inventory",
                                    "owner": "Synthetic reviewer", "reason": "Synthetic incomplete evidence"}]
    return c


def test_v5_accepts_reviewed_resolution_and_keeps_comparability_blocked(v5, monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail("Static release validation attempted execution/network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = canonical.validate_config(v5)
    assert result["static_valid"] and not result["paid_runs_authorized"] and not result["cross_shard_comparable"]
    assert [g["id"] for g in result["unresolved"]] == ["post-restart-per-machine-cost-inventory"]


@pytest.mark.parametrize("mutation", ["blanket", "missing-null", "missing-join", "price", "evidence",
                                     "pool", "historical", "erase-gate", "authorize"])
def test_v5_rejects_unsupported_resolution_or_historical_promotion(v5, mutation):
    rule = v5["evidence"]["null_served_model_rule"]
    if mutation == "blanket":
        rule["blanket_null_inference"] = True
    elif mutation == "missing-null":
        rule["required_null_columns"].pop()
    elif mutation == "missing-join":
        rule["per_request_routing_join_required"] = False
    elif mutation == "price":
        v5["provenance"]["runtime_files_sha256_lf"]["prices.yaml"] = "a" * 64
    elif mutation == "evidence":
        name = next(iter(v5["evidence"]["reviewed_artifacts_sha256_lf"]))
        v5["evidence"]["reviewed_artifacts_sha256_lf"][name] = "b" * 64
    elif mutation == "pool":
        v5["pooling"]["pre_v5_cohorts_report_eligible"] = True
    elif mutation == "historical":
        v5["evidence"]["historical_pilot_report_eligible"] = True
    elif mutation == "erase-gate":
        v5["readiness"]["unresolved"] = []
    else:
        v5["readiness"]["paid_runs_authorized"] = True
    with pytest.raises(ValueError):
        canonical.validate_config(v5)


def test_published_v5_is_immutable_and_remains_blocked_without_mutating_v4():
    c = canonical._json(canonical.V5_CONFIG)
    assert canonical.config_id(c) == "93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83"
    assert hashlib.sha256(canonical.V5_CONFIG.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == (
        "0d338d3913ac855993aecf85f6127c2be36302789500dd13f77a0d0fcd808b4c")
    result = canonical.validate_config(c, audit_current=True)
    assert not result["cross_shard_comparable"] and not result["paid_runs_authorized"]
    assert result["runtime_git_commit"] == "e442377be017edf58638f24f2c4da2a1deac8556"
    assert canonical.config_id(canonical._json(canonical.V4_CONFIG)) == (
        "026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4")
