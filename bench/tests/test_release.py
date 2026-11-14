"""Synthetic release bundles, never real benchmark outcomes or live checks."""

from copy import deepcopy
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


def test_bundle_has_exact_coverage_oracles_settings_and_no_execution(bundle, monkeypatch):
    config, path, data, output, settings, canary = bundle

    def forbidden(*args, **kwargs):
        pytest.fail("Release preparation must not launch processes or network calls")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = release.prepare_release(path, data, output, settings)
    assert result["launch_blocked"] and not canary.exists()
    assert result["validation"]["manifests_validated"] == 5
    assert [(a["tasks"], a["runs"]) for a in result["artifacts"].values()] == [
        (54, 270), (14, 70), (14, 70), (13, 65), (13, 65)]
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
