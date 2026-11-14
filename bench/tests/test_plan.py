"""Planning tests with declared synthetic layouts, never downloaded datasets."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from bench.plan import build_plan, main, write_manifest


def save_index(data):
    data["index"].write_text(
        json.dumps({"schema_version": 1, "tasks": data["entries"]}), encoding="utf-8"
    )


def add_task(data, dataset, local_id):
    root = data[dataset]
    source = root / "exercises" / local_id
    source.mkdir(parents=True)
    (source / "solution.py").write_text(
        "raise RuntimeError('exercise code must never execute during planning')\n",
        encoding="utf-8",
    )
    (source / "test_solution.py").write_text(
        "raise RuntimeError('tests must never execute during planning')\n", encoding="utf-8"
    )
    prompt = root / "prompts" / f"{local_id}.txt"
    prompt.parent.mkdir(exist_ok=True)
    prompt.write_text(f"Synthetic task {dataset}/{local_id}: fix the exercise.\n", encoding="utf-8")
    entry = {
        "dataset": dataset, "id": local_id, "source": f"exercises/{local_id}",
        "task_file": f"prompts/{local_id}.txt",
        "test_command": ["python", "-m", "pytest", "-q"],
    }
    data["entries"].append(entry)
    return entry


@pytest.fixture
def datasets(tmp_path):
    data = {
        "polyglot": tmp_path / "polyglot", "quixbugs": tmp_path / "quixbugs",
        "index": tmp_path / "task-index.json", "entries": [],
    }
    # Deliberately scrambled order: creation/index order must not determine runs.
    for dataset, local_id in (
        ("quixbugs", "zeta"), ("polyglot", "beta"),
        ("quixbugs", "alpha"), ("polyglot", "alpha"),
    ):
        add_task(data, dataset, local_id)
    save_index(data)
    return data


def plan(data, **kwargs):
    return build_plan(
        data["index"], polyglot=data["polyglot"], quixbugs=data["quixbugs"], **kwargs
    )


def test_default_counts_order_caps_and_fairness(datasets):
    result = plan(datasets)

    assert [task["task_id"] for task in result["tasks"]] == [
        "polyglot/alpha", "polyglot/beta", "quixbugs/alpha", "quixbugs/zeta",
    ]
    assert result["task_count"] == result["indexed_task_count"] == 4
    assert result["run_count"] == 20
    assert result["runs_by_agent"] == {
        "crocodile": 8, "mini-swe-agent": 8, "all-off-twin": 4,
    }
    assert result["tasks_by_dataset"] == {"polyglot": 2, "quixbugs": 2}
    assert result["execution_enabled"] is False
    assert result["evaluation_policy"]["grading_timeout_seconds"] == 180
    assert [run["run_id"] for run in result["runs"][:5]] == [
        "polyglot/alpha/crocodile/run-1", "polyglot/alpha/crocodile/run-2",
        "polyglot/alpha/mini-swe-agent/run-1", "polyglot/alpha/mini-swe-agent/run-2",
        "polyglot/alpha/all-off-twin/run-1",
    ]
    assert len({run["run_id"] for run in result["runs"]}) == 20
    for task in result["tasks"]:
        task_runs = [run for run in result["runs"] if run["task_id"] == task["task_id"]]
        for key in ("task_text", "task_text_sha256", "source_path", "test_command"):
            assert all(run[key] == task[key] for run in task_runs)
        assert task["task_text"].endswith("Test command: python -m pytest -q\n")
        assert all(run["step_cap"] == 30 for run in task_runs)
        assert all(run["wall_clock_cap_seconds"] == 600 for run in task_runs)
        assert all(Path(run["source_path"]).is_absolute() for run in task_runs)
    assert not {"cost", "solved", "score", "seed"} & result.keys()


def test_index_reordering_and_output_location_do_not_change_manifest(datasets, tmp_path):
    first = plan(datasets)
    datasets["entries"].reverse()
    save_index(datasets)
    second = plan(datasets)
    assert first == second
    first_file = write_manifest(first, tmp_path / "first.json")
    second_file = write_manifest(second, tmp_path / "second.json")
    assert first_file.read_bytes() == second_file.read_bytes()
    assert json.loads(first_file.read_text()) == first


@pytest.mark.parametrize("selection", ["polyglot", "quixbugs"])
def test_single_set_needs_only_its_selected_root(datasets, selection):
    result = build_plan(
        datasets["index"], dataset_set=selection, **{selection: datasets[selection]}
    )
    assert result["task_count"] == 2
    assert result["run_count"] == 10
    assert set(result["dataset_roots"]) == {selection}
    assert all(run["dataset"] == selection for run in result["runs"])


def test_limit_is_global_before_expansion_and_runs_do_not_repeat_twin(datasets):
    result = plan(datasets, limit=3, runs=3)
    assert result["task_count"] == 3
    assert result["indexed_task_count"] == 4
    assert result["run_count"] == 21
    assert result["tasks_by_dataset"] == {"polyglot": 2, "quixbugs": 1}
    assert result["runs_by_agent"] == {
        "crocodile": 9, "mini-swe-agent": 9, "all-off-twin": 3,
    }
    assert max(run["run_number"] for run in result["runs"] if
               run["agent_variant"] == "all-off-twin") == 1
    assert plan(datasets, limit=100)["run_count"] == 20


@pytest.mark.parametrize("runs, count", [(1, 12), (2, 20), (4, 36)])
def test_run_count_formula(datasets, runs, count):
    assert plan(datasets, runs=runs)["run_count"] == count


def test_duplicate_ids_are_rejected_even_beyond_limit(datasets):
    datasets["entries"].append(dict(datasets["entries"][0]))
    save_index(datasets)
    with pytest.raises(ValueError, match="Duplicate task ID: quixbugs/zeta"):
        plan(datasets, limit=1)


@pytest.mark.parametrize("nested", [False, True])
def test_ambiguous_sources_are_rejected(datasets, nested):
    entry = next(item for item in datasets["entries"] if item["id"] == "beta")
    entry["source"] = "exercises/alpha"
    if nested:
        entry["source"] += "/nested"
        source = datasets["polyglot"] / entry["source"]
        source.mkdir()
        (source / "file.txt").write_text("synthetic nested source", encoding="utf-8")
    save_index(datasets)
    with pytest.raises(ValueError, match="Ambiguous overlapping sources"):
        plan(datasets)


@pytest.mark.parametrize("field", ["source", "task_file"])
@pytest.mark.parametrize("bad_path", ["missing", "../escape", "/absolute", "C:/drive", "a\\b"])
def test_invalid_or_missing_declared_paths_fail(datasets, field, bad_path):
    datasets["entries"][0][field] = bad_path
    save_index(datasets)
    with pytest.raises((ValueError, OSError)):
        plan(datasets)


def test_missing_task_beyond_limit_is_not_silently_ignored(datasets):
    datasets["entries"][0]["source"] = "missing-source"
    save_index(datasets)
    with pytest.raises(FileNotFoundError):
        plan(datasets, limit=1)


def test_empty_prompt_is_rejected(datasets):
    entry = datasets["entries"][0]
    (datasets[entry["dataset"]] / entry["task_file"]).write_text(" \n", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt is empty"):
        plan(datasets)


def test_extra_oracle_paths_and_custom_argv_are_retained(datasets):
    entry = datasets["entries"][0]
    source = datasets[entry["dataset"]] / entry["source"]
    (source / "oracle").mkdir()
    (source / "oracle/expected.txt").write_text("expected fixture", encoding="utf-8")
    entry["test_paths"] = ["oracle", "test_solution.py"]
    entry["test_command"] += ["--timeout=5"]
    save_index(datasets)
    result = plan(datasets)
    task = next(item for item in result["tasks"] if item["task_id"] == "quixbugs/zeta")
    assert task["test_paths"] == ["oracle", "test_solution.py"]
    assert task["test_command"][-1] == "--timeout=5"
    assert task["task_text"].endswith("--timeout=5\n")


@pytest.mark.parametrize("field, value", [
    ("id", "UPPER"), ("dataset", "unknown"), ("unexpected", True),
    ("test_command", "python -m pytest -q"), ("test_command", ["echo", "fake"]),
    ("test_command", ["python", "-m", "pytest", "-q", "--runslow"]),
    ("test_paths", "tests"), ("test_paths", ["../escape"]),
    ("test_paths", ["missing-oracle"]),
])
def test_invalid_task_metadata_is_rejected(datasets, field, value):
    datasets["entries"][0][field] = value
    save_index(datasets)
    with pytest.raises((ValueError, OSError)):
        plan(datasets)


@pytest.mark.parametrize("option, value", [
    ("runs", 0), ("runs", -1), ("runs", True), ("runs", 1.5),
    ("limit", 0), ("limit", -1), ("limit", False),
    ("dataset_set", "unknown"),
])
def test_invalid_options_are_rejected(datasets, option, value):
    with pytest.raises(ValueError):
        plan(datasets, **{option: value})


def test_selected_root_is_required_and_must_be_directory(datasets, tmp_path):
    with pytest.raises(ValueError, match="explicit --polyglot"):
        build_plan(datasets["index"], quixbugs=datasets["quixbugs"])
    with pytest.raises(FileNotFoundError):
        build_plan(datasets["index"], polyglot=tmp_path / "missing", dataset_set="polyglot")
    with pytest.raises(ValueError, match="Dataset root must be a directory"):
        build_plan(datasets["index"], polyglot=datasets["index"], dataset_set="polyglot")


def test_missing_index_and_directory_index_are_rejected(datasets, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_plan(tmp_path / "missing.json", polyglot=datasets["polyglot"],
                   dataset_set="polyglot")
    with pytest.raises(ValueError, match="regular JSON file"):
        build_plan(datasets["polyglot"], polyglot=datasets["polyglot"],
                   dataset_set="polyglot")


@pytest.mark.parametrize("contents", [
    "not JSON", '{"schema_version": 2, "tasks": []}',
    '{"schema_version": true, "tasks": []}',
    '{"schema_version": 1, "tasks": [], "tasks": []}',
    '{"schema_version": 1, "tasks": [], "unknown": 1}',
    '{"schema_version": 1, "tasks": {}}',
    '{"schema_version": 1, "tasks": [{}]}',
])
def test_malformed_or_ambiguous_indexes_fail(datasets, contents):
    datasets["index"].write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        plan(datasets)


def test_selected_dataset_must_have_indexed_tasks(datasets):
    datasets["entries"] = [item for item in datasets["entries"] if
                           item["dataset"] == "polyglot"]
    save_index(datasets)
    with pytest.raises(ValueError, match="No indexed tasks.*quixbugs"):
        plan(datasets)


def test_unselected_task_files_are_not_required(datasets):
    datasets["entries"][0]["source"] = "not-installed"
    save_index(datasets)
    result = build_plan(datasets["index"], polyglot=datasets["polyglot"],
                        dataset_set="polyglot")
    assert result["task_count"] == 2


def test_empty_exercise_is_rejected(datasets):
    entry = datasets["entries"][0]
    source = datasets[entry["dataset"]] / "empty"
    source.mkdir()
    entry["source"] = "empty"
    save_index(datasets)
    with pytest.raises(ValueError, match="no ordinary files"):
        plan(datasets)


def test_existing_manifest_and_dataset_files_are_preserved(datasets, tmp_path):
    result = plan(datasets)
    destination = tmp_path / "existing.json"
    destination.write_text("keep existing manifest", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_manifest(result, destination)
    assert destination.read_text() == "keep existing manifest"
    with pytest.raises(ValueError, match="outside the selected dataset roots"):
        write_manifest(result, datasets["polyglot"] / "manifest.json")
    assert not (datasets["polyglot"] / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        write_manifest(result, tmp_path / "missing-parent" / "manifest.json")
    assert not (tmp_path / "missing-parent").exists()


def test_dry_run_writes_counts_and_manifest_without_execution(datasets, tmp_path, monkeypatch, capsys):
    from bench import grade as grader
    from bench import prepare
    import socket

    canary = tmp_path / "executed.txt"
    payload = f"from pathlib import Path\nPath({str(canary)!r}).write_text('executed')\n"
    for entry in datasets["entries"]:
        source = datasets[entry["dataset"]] / entry["source"]
        for name in ("conftest.py", "__init__.py", "setup.py", "sitecustomize.py"):
            (source / name).write_text(payload, encoding="utf-8")
    before = {
        str(path): path.read_bytes()
        for dataset in ("polyglot", "quixbugs")
        for path in datasets[dataset].rglob("*") if path.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("Dry run attempted execution or a network call")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(prepare, "prepare_workspace", forbidden)
    monkeypatch.setattr(grader, "grade_exercise", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    output = tmp_path / "dry-run.json"
    assert main([
        "--set", "both", "--polyglot", str(datasets["polyglot"]),
        "--quixbugs", str(datasets["quixbugs"]), "--task-index", str(datasets["index"]),
        "--limit", "3", "--runs", "2", "--dry-run", "--output", str(output),
    ]) == 0
    printed = capsys.readouterr().out
    assert "Dry run: 3 tasks / 4 indexed; 15 runs" in printed
    assert json.loads(output.read_text())["run_count"] == 15
    assert not canary.exists()
    after = {str(path): path.read_bytes() for dataset in ("polyglot", "quixbugs")
             for path in datasets[dataset].rglob("*") if path.is_file()}
    assert before == after


def test_cli_is_still_planning_only_without_dry_run(datasets, tmp_path, capsys):
    output = tmp_path / "plan.json"
    assert main([
        "--set", "quixbugs", "--quixbugs", str(datasets["quixbugs"]),
        "--task-index", str(datasets["index"]), "--output", str(output),
    ]) == 0
    assert "Plan: 2 tasks / 2 indexed; 10 runs" in capsys.readouterr().out
    assert json.loads(output.read_text())["execution_enabled"] is False


def test_cli_failure_creates_no_manifest(datasets, tmp_path, capsys):
    output = tmp_path / "no-plan.json"
    with pytest.raises(SystemExit) as error:
        main([
            "--polyglot", str(datasets["polyglot"]), "--quixbugs", str(datasets["quixbugs"]),
            "--task-index", str(datasets["index"]), "--output", str(output), "--limit", "0",
        ])
    assert error.value.code == 2
    assert "Planning failed" in capsys.readouterr().err
    assert not output.exists()


def test_module_cli(datasets, tmp_path):
    output = tmp_path / "module-plan.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "bench.plan", "--set", "polyglot",
            "--polyglot", str(datasets["polyglot"]), "--task-index", str(datasets["index"]),
            "--limit", "1", "--dry-run", "--output", str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Dry run: 1 tasks / 2 indexed; 5 runs" in result.stdout
    assert json.loads(output.read_text())["tasks"][0]["task_id"] == "polyglot/alpha"


@pytest.fixture
def full_datasets(tmp_path):
    """54 synthetic tasks, not a mapping or claim about the real dataset IDs."""
    base = tmp_path / "full"
    base.mkdir()
    data = {"polyglot": base / "polyglot", "quixbugs": base / "quixbugs",
            "index": base / "task-index.json", "entries": []}
    for dataset, count in (("quixbugs", 20), ("polyglot", 34)):
        for number in range(count, 0, -1):
            add_task(data, dataset, f"task-{number:02d}")
    save_index(data)
    return data


def test_four_shards_cover_full_plan_once_keep_order_and_all_five_runs(full_datasets):
    full = plan(full_datasets)
    task_ids, run_ids, positions = [], [], []
    seen = set()
    for number, (start, end) in enumerate(((1, 14), (15, 28), (29, 41), (42, 54)), 1):
        shard = plan(full_datasets, shard=f"{number}/4")
        ids = [task["task_id"] for task in shard["tasks"]]
        assert not set(ids) & seen
        seen.update(ids)
        assert ids == [task["task_id"] for task in full["tasks"][start - 1:end]]
        assert shard["task_count"] == end - start + 1
        assert shard["indexed_task_count"] == 54
        assert shard["run_count"] == (end - start + 1) * 5
        assert shard["full_plan"] == full["full_plan"]
        assert shard["shard"] == {"number": number, "of": 4, "full_plan_start": start,
                                  "full_plan_end": end, "task_count_before_limit": end - start + 1}
        for task in shard["tasks"]:
            assert task["shard_number"] == number
            assert task["full_plan_id"] == full["full_plan"]["id"]
            runs = [run for run in shard["runs"] if run["task_id"] == task["task_id"]]
            assert [(run["agent_variant"], run["run_number"]) for run in runs] == [
                ("crocodile", 1), ("crocodile", 2), ("mini-swe-agent", 1),
                ("mini-swe-agent", 2), ("all-off-twin", 1),
            ]
            for run in runs:
                assert run["full_plan_id"] == task["full_plan_id"]
                assert run["full_plan_position"] == task["full_plan_position"]
                assert run["shard_number"] == number
        task_ids += ids
        run_ids += [run["run_id"] for run in shard["runs"]]
        positions += [task["full_plan_position"] for task in shard["tasks"]]
    assert task_ids == [task["task_id"] for task in full["tasks"]]
    assert run_ids == [run["run_id"] for run in full["runs"]]
    assert positions == list(range(1, 55))
    assert full["runs_per_task"] == {"crocodile": 2, "mini-swe-agent": 2, "all-off-twin": 1}


def test_shard_is_deterministic_and_limit_is_local_after_assignment(full_datasets):
    first = plan(full_datasets, shard="2/4")
    full_datasets["entries"].reverse()
    save_index(full_datasets)
    assert plan(full_datasets, shard="2/4") == first
    limited = plan(full_datasets, shard="2/4", limit=2)
    assert [task["full_plan_position"] for task in limited["tasks"]] == [15, 16]
    assert limited["tasks"] == first["tasks"][:2]
    assert limited["runs"] == first["runs"][:10]
    assert limited["full_plan"] == first["full_plan"]
    assert limited["shard"] == first["shard"]
    assert plan(full_datasets, shard="4/4", limit=99)["task_count"] == 13


@pytest.mark.parametrize("size", [53, 55])
def test_shard_rejects_non_54_task_plans_before_limit(full_datasets, size):
    if size == 53:
        full_datasets["entries"].pop()
    else:
        add_task(full_datasets, "quixbugs", "extra-task")
    save_index(full_datasets)
    with pytest.raises(ValueError, match="exactly 54 tasks"):
        plan(full_datasets, shard="1/4", limit=1)


def test_shard_rejects_wrong_dataset_mix_even_when_total_is_54(full_datasets):
    full_datasets["entries"].pop()  # 33 Polyglot, then add a 21st QuixBugs task.
    add_task(full_datasets, "quixbugs", "extra-task")
    save_index(full_datasets)
    with pytest.raises(ValueError, match="34 polyglot and 20 quixbugs"):
        plan(full_datasets, shard="1/4")


def test_shard_rejects_small_and_single_dataset_plans(datasets, full_datasets):
    with pytest.raises(ValueError, match="exactly 54 tasks"):
        plan(datasets, shard="1/4")
    with pytest.raises(ValueError, match="--set both"):
        plan(full_datasets, shard="1/4", dataset_set="polyglot")


@pytest.mark.parametrize("shard", ["0/4", "5/4", "1/3", "01/4", "1", "1 /4", "", 1, True])
def test_invalid_shard_spelling_is_rejected(datasets, shard):
    with pytest.raises(ValueError, match="shard must be exactly"):
        plan(datasets, shard=shard)


def test_invalid_task_outside_chosen_shard_is_still_validated(full_datasets):
    full_datasets["entries"][0]["source"] = "missing-last-quixbugs-task"
    save_index(full_datasets)
    with pytest.raises(FileNotFoundError):
        plan(full_datasets, shard="1/4", limit=1)


def test_full_plan_identity_is_portable_and_detects_definition_or_repeat_changes(full_datasets, tmp_path):
    import shutil

    before = plan(full_datasets)
    relocated = {**full_datasets}
    for dataset in ("polyglot", "quixbugs"):
        relocated[dataset] = tmp_path / "relocated" / dataset
        shutil.copytree(full_datasets[dataset], relocated[dataset])
    assert plan(relocated)["full_plan"] == before["full_plan"]
    assert plan(full_datasets, runs=3)["full_plan"]["id"] != before["full_plan"]["id"]
    entry = full_datasets["entries"][0]
    prompt = full_datasets[entry["dataset"]] / entry["task_file"]
    prompt.write_text("Changed synthetic instructions\n", encoding="utf-8")
    assert plan(full_datasets, shard="1/4")["full_plan"]["id"] != before["full_plan"]["id"]


def test_shard_cli_is_planning_only_and_records_partial_selection(full_datasets, tmp_path, monkeypatch, capsys):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Sharding must not execute anything or access a service")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    output = tmp_path / "shard.json"
    assert main([
        "--set", "both", "--polyglot", str(full_datasets["polyglot"]),
        "--quixbugs", str(full_datasets["quixbugs"]), "--task-index", str(full_datasets["index"]),
        "--shard", "1/4", "--limit", "2", "--dry-run", "--output", str(output),
    ]) == 0
    printed = capsys.readouterr().out
    assert "2 tasks / 54 indexed; 10 runs" in printed
    assert "Shard 1/4: full-plan tasks 1-14" in printed
    assert "Partial shard: not a complete comparable benchmark shard" in printed
    assert "Full-plan identity:" in printed
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["selection"]["shard"] == "1/4"
    assert result["execution_enabled"] is False


def test_shard_cli_failure_leaves_no_manifest(datasets, tmp_path, capsys):
    output = tmp_path / "invalid-shard.json"
    with pytest.raises(SystemExit) as error:
        main(["--polyglot", str(datasets["polyglot"]), "--quixbugs", str(datasets["quixbugs"]),
              "--task-index", str(datasets["index"]), "--shard", "1/4", "--output", str(output)])
    assert error.value.code == 2
    assert "exactly 54 tasks" in capsys.readouterr().err
    assert not output.exists()
