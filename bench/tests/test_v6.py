"""Published v6: pins the a366329 agent runtime, keeps v5/v4 immutable and stays blocked."""

import hashlib

import pytest

from bench import canonical

V6_ID = "098247dad4c155113ad574621d088918de212bd7019d8a48816ae3c4716caf1b"
V6_LF_SHA = "ba95d195946049c9ce200ae029f13d1bbf8d242ecff972d50e84ebc40bd6b396"


def _lf_sha(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_published_v6_is_immutable_and_matches_current_runtime():
    c = canonical._json(canonical.V6_CONFIG)
    assert canonical.config_id(c) == V6_ID and _lf_sha(canonical.V6_CONFIG) == V6_LF_SHA
    result = canonical.validate_config(c)
    assert result["static_valid"] and result["runtime_matches_snapshot"]
    assert not result["paid_runs_authorized"] and not result["cross_shard_comparable"]
    assert [g["id"] for g in result["unresolved"]] == ["post-restart-per-machine-cost-inventory"]


def test_v6_chains_from_unchanged_v5():
    c = canonical._json(canonical.V6_CONFIG)
    v5 = canonical._json(canonical.V5_CONFIG)
    assert c["provenance"]["previous_config_id"] == canonical.config_id(v5) == (
        "93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83")
    assert c["provenance"]["previous_config_sha256_lf"] == _lf_sha(canonical.V5_CONFIG)
    for key in ("datasets", "plan", "gateway", "agents", "limits", "grading", "known_limitations"):
        assert c[key] == v5[key], key


@pytest.mark.parametrize("mutation", ["authorize", "comparable", "erase-gate", "price"])
def test_v6_cannot_be_promoted(mutation):
    c = canonical._json(canonical.V6_CONFIG)
    if mutation == "authorize":
        c["readiness"]["paid_runs_authorized"] = True
    elif mutation == "comparable":
        c["readiness"]["cross_shard_comparable"] = True
    elif mutation == "erase-gate":
        c["readiness"]["unresolved"] = []
    else:
        c["provenance"]["runtime_files_sha256_lf"]["prices.yaml"] = "a" * 64
    with pytest.raises(ValueError):
        canonical.validate_config(c)
