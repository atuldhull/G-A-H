"""Synthetic data and static config validation only; no benchmark execution."""

from copy import deepcopy
import hashlib
import json
import socket
import subprocess

import pytest

from bench import canonical
from bench.plan import build_plan, write_manifest


@pytest.fixture
def snapshot():
    # Synthetic configs pin the current test checkout; the published v1 file is
    # kept immutable and separately tested for visible historical source drift.
    config = canonical._json(canonical.DEFAULT_CONFIG)
    for name in config["provenance"]["runtime_files_sha256_lf"]:
        raw = (canonical.REPO_ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        config["provenance"]["runtime_files_sha256_lf"][name] = hashlib.sha256(raw).hexdigest()
    return config


@pytest.fixture
def inputs(tmp_path, snapshot):
    data = tmp_path / "data"
    entries, oracles = [], {}
    canary = tmp_path / "EXECUTED"
    poison = f"from pathlib import Path\nPath({str(canary)!r}).touch()\nraise RuntimeError('synthetic canary')\n"
    for task_id in snapshot["plan"]["task_order"]:
        dataset, local_id = task_id.split("/")
        root = data / dataset
        source = root / local_id
        source.mkdir(parents=True)
        for name in ("solution.py", "test_solution.py", "conftest.py"):
            (source / name).write_bytes(poison.encode())
        (root / f"{local_id}.txt").write_bytes(b"Synthetic validation fixture only.\n")
        entries.append({"dataset": dataset, "id": local_id, "source": local_id,
                        "task_file": f"{local_id}.txt", "test_command": ["python", "-m", "pytest", "-q"]})
        oracles[task_id] = ["test_solution.py"]
    (data / "tasks.json").write_bytes(json.dumps({"schema_version": 1, "tasks": entries}).encode())
    (data / "oracles.json").write_bytes(json.dumps(oracles).encode())
    full = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs")
    # Replace evidence with synthetic fixture hashes; never publish this fixture as real inputs.
    for filename, field in (("tasks.json", "tasks_sha256"), ("oracles.json", "oracles_sha256")):
        snapshot["datasets"][field] = hashlib.sha256((data / filename).read_bytes()).hexdigest()
    snapshot["plan"]["full_plan_id"] = full["full_plan"]["id"]
    snapshot["datasets"]["tasks"] = {
        t["task_id"]: {"task_text_sha256": t["task_text_sha256"],
                       "source_sha256": canonical.source_digest(t["source_path"])} for t in full["tasks"]
    }
    directory = tmp_path / "plans"
    directory.mkdir()
    manifests = [write_manifest(full, directory / "full.json")]
    for number in range(1, 5):
        plan = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs",
                          shard=f"{number}/4")
        manifests.append(write_manifest(plan, directory / f"shard-{number}.json"))
    return snapshot, data, manifests, canary


def test_published_config_stays_immutable_and_reports_current_drift(capsys):
    published = canonical._json(canonical.DEFAULT_CONFIG)
    assert canonical.config_id(published) == "07e9ded30d149ddff5bd3bdccc58e9f691a87b4143072321c84a3c075f6728fe"
    with pytest.raises(ValueError, match="source snapshot differs"):
        canonical.validate_config(published)
    report = canonical.validate_config(published, audit_current=True)
    assert report["contract_valid"] and not report["static_valid"] and report["runtime_drift"]
    assert not report["runtime_matches_snapshot"] and not report["cross_shard_comparable"]
    assert report["paid_runs_authorized"] is False
    assert canonical.main(["--audit-current", "--require-comparable"]) == 1
    assert json.loads(capsys.readouterr().out)["cross_shard_comparable"] is False


def test_all_five_dry_run_manifests_validate_without_execution(inputs, monkeypatch):
    config, data, plans, canary = inputs

    def forbidden(*args, **kwargs):
        pytest.fail("Canonical validation must not launch processes or network calls")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    report = canonical.validate_config(config, data_root=data, manifests=plans)
    assert report["dataset_validated"] and report["manifests_validated"] == 5
    assert not report["cross_shard_comparable"] and not canary.exists()


@pytest.mark.parametrize("change", [
    lambda c: c["readiness"].update(cross_shard_comparable=True),
    lambda c: c["readiness"].update(paid_runs_authorized=True),
    lambda c: c["readiness"].update(unresolved=[]),
    lambda c: c["gateway"].update(endpoint="http://127.0.0.1:8080"),
    lambda c: c["gateway"].update(physical_version_vk_and_cap_verified=True),
    lambda c: c["provenance"]["observed_environment_versions"].update(cross_machine_lock_verified=True),
    lambda c: c["agents"]["crocodile"].update(wire_model="gemini/gemini-3.5-flash"),
    lambda c: c["agents"]["mini-swe-agent"].update(fallbacks=["synthetic/other"]),
    lambda c: c["limits"].update(hard_deadline_enforced=True),
    lambda c: c["grading"].update(restore_original_tests=False),
    lambda c: c["plan"]["task_order"].reverse(),
    lambda c: c["plan"].update(shard_ranges=[[1, 15], [15, 28], [29, 41], [42, 54]]),
    lambda c: c["plan"]["run_order_per_task"].reverse(),
    lambda c: c["gateway"].update(api_key="SYNTHETIC-CREDENTIAL-MUST-BE-REJECTED"),
    lambda c: c["provenance"]["runtime_files_sha256_lf"].pop("bench/run.py"),
    lambda c: c["provenance"]["runtime_files_sha256_lf"].update({"bench/run.py": "0" * 64}),
    lambda c: c["evidence"].update(canonical_native_prices_sha256="0" * 64),
])
def test_incompatible_or_unverified_config_cannot_validate(snapshot, change):
    change(snapshot)
    with pytest.raises(ValueError):
        canonical.validate_config(snapshot)


def test_dataset_json_mismatch_is_not_silently_accepted(inputs):
    config, data, _, _ = inputs
    with (data / "oracles.json").open("ab") as stream:
        stream.write(b"\n")
    with pytest.raises(ValueError, match="JSON hash"):
        canonical.validate_config(config, data_root=data)


@pytest.mark.parametrize("which", ["solution.py", "test_solution.py", "prompt"])
def test_source_or_exact_prompt_mutation_is_incompatible(inputs, which):
    config, data, _, _ = inputs
    task = config["plan"]["task_order"][0]
    dataset, local_id = task.split("/")
    target = data / dataset / (f"{local_id}.txt" if which == "prompt" else f"{local_id}/{which}")
    with target.open("ab") as stream:
        stream.write(b"\r\n")
    with pytest.raises(ValueError, match="identity|digest"):
        canonical.validate_config(config, data_root=data)


def test_generated_bytecode_is_not_a_cross_machine_source_identity(inputs):
    config, data, plans, _ = inputs
    source = data / config["plan"]["task_order"][0]
    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "local.pyc").write_bytes(b"synthetic machine-local bytecode")
    assert canonical.validate_config(config, data_root=data, manifests=plans)["dataset_validated"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "truncated"])
def test_partial_or_overlapping_shards_do_not_validate(inputs, change):
    config, data, plans, _ = inputs
    if change == "missing":
        plans.pop()
    elif change == "duplicate":
        plans[-1] = plans[-2]
    else:
        doc = canonical._json(plans[-1])
        doc["runs"].pop()
        plans[-1].write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        canonical.validate_config(config, data_root=data, manifests=plans)


def test_duplicate_json_and_unknown_config_fields_are_rejected(snapshot, tmp_path):
    bad = tmp_path / "duplicate.json"
    bad.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        canonical._json(bad)
    extra = deepcopy(snapshot)
    extra["allow_execution"] = True
    with pytest.raises(ValueError, match="fields"):
        canonical.validate_config(extra)


def test_config_identity_is_independent_of_file_whitespace(snapshot):
    same = json.loads(json.dumps(snapshot, sort_keys=True, indent=4))
    assert canonical.config_id(same) == canonical.config_id(snapshot)
    same["revision"] = "different"
    assert canonical.config_id(same) != canonical.config_id(snapshot)
