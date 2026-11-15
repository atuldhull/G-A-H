"""Synthetic release bundles, never real benchmark outcomes or live checks."""

from copy import deepcopy
import hashlib
import json
import socket
import subprocess

import pytest

from bench import canonical, release
from bench.plan import build_plan
from bench.tests.test_canonical import inputs as _inputs, snapshot as _snapshot


def v2(config):
    config = deepcopy(config)
    config.update(schema_version=2, revision="gemini-54-v2", changes_from_v1=["Synthetic LF fixture"])
    config["known_limitations"] = [
        {"id": name, "accepted_by": "Atul", "comparability_gate": False,
         "description": "Synthetic test of explicitly accepted limitation"}
        for name in sorted(canonical.ACCEPTED_LIMITATIONS)]
    config["gateway"]["live_evidence"] = {
        "status": "reported-verified-on-Atul-machine", "independently_verified_here": False}
    for name in ("crocodile", "all-off-twin"):
        config["agents"][name]["sampling"] = "native-0.0-or-0.7"
    config["readiness"]["unresolved"] = [
        {"id": "mini-attempt-3a111322", "owner": "Person 4 / Atul artifacts",
         "reason": "Synthetic fixture: missing sanitized traceback"}]
    return config


@pytest.fixture
def bundle(tmp_path):
    config, data, _, canary = _inputs.__wrapped__(tmp_path, _snapshot.__wrapped__())
    config = v2(config)
    manifest = [config["datasets"]["tasks_sha256"], config["datasets"]["oracles_sha256"],
                *(item["commit"] for item in config["datasets"]["upstreams"].values())]
    manifest += [f"- {task} `{release._tree_hash(data / task)}`" for task in config["plan"]["task_order"]]
    (data / "MANIFEST.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    path = tmp_path / "synthetic-v2.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    settings = canonical.REPO_ROOT / "bench/configs/mini-settings.ubuntu.json"
    return config, path, data, tmp_path / "bundle", settings, canary


def test_v2_known_limitations_are_reported_separately_from_blockers(bundle):
    config, _, data, _, _, _ = bundle
    result = canonical.validate_config(config, data_root=data)
    assert result["static_valid"] and result["dataset_validated"]
    assert {g["id"] for g in result["unresolved"]} == {"mini-attempt-3a111322"}
    assert len(result["known_limitations"]) == 4
    assert not result["cross_shard_comparable"] and not result["paid_runs_authorized"]


@pytest.mark.parametrize("mutation", ["gate", "local-proof", "clear-mini", "sampling", "authorized"])
def test_v2_cannot_forge_readiness_or_erase_accepted_differences(bundle, mutation):
    config, *_ = bundle
    if mutation == "gate":
        config["known_limitations"][0]["comparability_gate"] = True
    elif mutation == "local-proof":
        config["gateway"]["live_evidence"]["independently_verified_here"] = True
    elif mutation == "clear-mini":
        config["readiness"]["unresolved"] = []
    elif mutation == "sampling":
        config["agents"]["crocodile"]["sampling"] = "omit"
    else:
        config["readiness"]["paid_runs_authorized"] = True
    with pytest.raises(ValueError):
        canonical.validate_config(config)


@pytest.mark.parametrize("include_smoke", [False, True])
def test_bundle_has_exact_coverage_oracles_settings_and_no_execution(bundle, monkeypatch, include_smoke):
    config, path, data, output, settings, canary = bundle

    def forbidden(*args, **kwargs):
        pytest.fail("Release preparation must not launch processes or network calls")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = release.prepare_release(path, data, output, settings, include_smoke=include_smoke)
    assert result["launch_blocked"] and not canary.exists()
    assert result["validation"]["manifests_validated"] == 5
    expected = [(54, 270), (14, 70), (14, 70), (13, 65), (13, 65)]
    assert [(a["tasks"], a["runs"]) for a in result["artifacts"].values()] == expected + ([(3, 15)] if include_smoke else [])
    full = canonical._json(output / "full.json")
    task_ids, run_ids = [], []
    originals = canonical._json(data / "oracles.json")
    for number in range(1, 5):
        label = f"shard-{number}"
        shard = canonical._json(output / f"{label}.json")
        subset = canonical._json(output / f"{label}-oracles.json")
        ids = [task["task_id"] for task in shard["tasks"]]
        assert subset == {task: originals[task] for task in ids}
        assert shard["full_plan"] == full["full_plan"]
        task_ids.extend(ids)
        run_ids.extend(row["run_id"] for row in shard["runs"])
        assert len(shard["runs"]) == 5 * len(ids)
        assert result["commands_not_executed"][label][-1] == "--execute"
    assert task_ids == config["plan"]["task_order"] and len(set(task_ids)) == 54
    assert run_ids == [row["run_id"] for row in full["runs"]] and len(set(run_ids)) == 270
    assert canonical._json(output / "mini-settings.json")["session_header_verified"] is False
    if include_smoke:
        smoke = canonical._json(output / "smoke.json")
        assert smoke["tasks"] == [{**task, "shard_number": 1} for task in full["tasks"][:3]]
        assert smoke["runs"] == [{**run, "shard_number": 1} for run in full["runs"][:15]]
        assert smoke["selection"]["limit"] == 3 and smoke["selection"]["shard"] == "1/4"
        assert canonical._json(output / "smoke-oracles.json") == {
            task["task_id"]: originals[task["task_id"]] for task in smoke["tasks"]}
    with pytest.raises(ValueError, match="fresh output"):
        release.prepare_release(path, data, output, settings)


def test_bad_builder_manifest_stops_before_writing(bundle):
    _, path, data, output, settings, _ = bundle
    with (data / "MANIFEST.md").open("a", encoding="utf-8") as stream:
        stream.write("- polyglot/extra `0000000000000000`\n")
    with pytest.raises(ValueError, match="54 tasks"):
        release.prepare_release(path, data, output, settings)
    assert not output.exists()


def test_v2_rejects_crlf_even_when_hashes_are_repinned(bundle):
    config, _, data, _, _, _ = bundle
    task = config["plan"]["task_order"][0]
    dataset, name = task.split("/")
    (data / dataset / f"{name}.txt").write_bytes(b"Synthetic\r\n")
    full = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs")
    config["plan"]["full_plan_id"] = full["full_plan"]["id"]
    config["datasets"]["tasks"][task]["task_text_sha256"] = full["tasks"][0]["task_text_sha256"]
    with pytest.raises(ValueError, match="LF-only"):
        canonical.validate_config(config, data_root=data)


def test_require_comparable_remains_blocked_for_valid_v2(bundle, capsys):
    _, path, data, _, _, _ = bundle
    assert canonical.main(["--config", str(path), "--data-root", str(data), "--require-comparable"]) == 1
    assert json.loads(capsys.readouterr().out)["unresolved"][0]["id"] == "mini-attempt-3a111322"


def test_published_v2_is_immutable_without_requiring_historical_runtime_to_be_current():
    config = canonical._json(canonical.V2_CONFIG)
    raw = canonical.V2_CONFIG.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == "4cdf9b9331d84981c624ecdf0ac3a8b9114f50f9374ad1ae89ad4021080e48f6"
    assert canonical.config_id(config) == "700089ad8472546868ea39edee3f8e43b5b9ff87204cfaabf9268a0d616a0494"
    result = canonical.validate_config(config, audit_current=True)
    # Current sources may evolve. Auditing never rewrites the historical pins;
    # strict execution validation still rejects any actual runtime drift.
    assert result["static_valid"] == result["runtime_matches_snapshot"] == (not result["runtime_drift"])
    if result["runtime_drift"]:
        with pytest.raises(ValueError, match="source snapshot differs"):
            canonical.validate_config(config)
    else:
        assert canonical.validate_config(config)["static_valid"]
    assert result["runtime_git_commit"] == "67fa99fc8b4a112221e3606c87a5d16413675158"
    assert not result["paid_runs_authorized"] and not result["cross_shard_comparable"]
    assert config["datasets"]["tasks_sha256"] == "3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18"
    assert config["datasets"]["oracles_sha256"] == "38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537"
    assert config["gateway"]["live_evidence"]["independently_verified_here"] is False


def test_actual_mutation_of_v2_is_detected():
    published = canonical._json(canonical.V2_CONFIG)
    mutated = deepcopy(published)
    mutated["provenance"]["runtime_files_sha256_lf"]["bench/mini.py"] = "0" * 64
    assert canonical.config_id(mutated) != canonical.config_id(published)
    assert canonical.config_id(mutated) != "700089ad8472546868ea39edee3f8e43b5b9ff87204cfaabf9268a0d616a0494"


def test_v3_requires_diagnostic_runtime_pins_and_keeps_unsupported_evidence_blocked(bundle):
    config, _, data, _, _, _ = bundle
    config.update(schema_version=3, revision="gemini-54-v3", changes_from_v2=["Synthetic diagnostic snapshot"])
    config.pop("changes_from_v1")
    name = "bench/failure_evidence.py"
    for relative in (name, "bench/canonical.py", "bench/attest.py"):
        config["provenance"]["runtime_files_sha256_lf"][relative] = hashlib.sha256(
            (canonical.REPO_ROOT / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    result = canonical.validate_config(config, data_root=data)
    assert result["static_valid"] and result["dataset_validated"]
    assert not result["cross_shard_comparable"] and not result["paid_runs_authorized"]
    assert len(result["known_limitations"]) == 4 and result["unresolved"]
    config["provenance"]["runtime_files_sha256_lf"].pop(name)
    with pytest.raises(ValueError, match="Missing v3 diagnostic/runtime pins"):
        canonical.validate_config(config)
