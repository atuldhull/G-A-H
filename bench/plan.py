"""Plan benchmark runs from an explicit task index without executing exercises."""

import argparse
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex

from bench.prepare import _inventory, _is_directory


DATASETS = ("polyglot", "quixbugs")
AGENTS = ("crocodile", "mini-swe-agent", "all-off-twin")
TEST_PREFIX = ["python", "-m", "pytest", "-q"]
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _relative(value: object, label: str, *, metadata: bool = False) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"{label} must be a portable relative path using forward slashes")
    parts = value.split("/")
    if (
        PurePosixPath(value).is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(character) < 32 for character in value)
        or (not metadata and any(part.casefold() == ".meta" for part in parts))
    ):
        raise ValueError(f"{label} must stay inside its root and outside .meta/: {value}")
    return Path(*parts)


def _inside(root: Path, relative: Path, *, directory: bool) -> Path:
    current = root
    for index, part in enumerate(relative.parts):
        current /= part
        is_directory = _is_directory(current)
        expected = directory if index == len(relative.parts) - 1 else True
        if is_directory != expected:
            kind = "directory" if expected else "regular file"
            raise ValueError(f"Expected {kind}: {current}")
    return current.resolve(strict=True)


def _entry(value: object) -> dict[str, object]:
    required = {"dataset", "id", "source", "task_file", "test_command"}
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Each task must contain {sorted(required)}")
    if value.keys() - (required | {"test_paths"}):
        raise ValueError(f"Unknown task fields: {sorted(value.keys() - required - {'test_paths'})}")
    dataset, local_id = value["dataset"], value["id"]
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset!r}")
    if not isinstance(local_id, str) or not ID_PATTERN.fullmatch(local_id):
        raise ValueError("Task id must use lowercase letters, digits, dots, underscores, or hyphens")
    command = value["test_command"]
    if (
        not isinstance(command, list) or command[:4] != TEST_PREFIX
        or any(not isinstance(arg, str) or not arg or any(c in arg for c in "\0\r\n")
               for arg in command)
    ):
        raise ValueError("test_command must be argv beginning with python -m pytest -q")
    if any(arg == "--runslow" or arg.startswith("--runslow=") for arg in command):
        raise ValueError("--runslow is excluded by the evaluation design")
    extras = value.get("test_paths", [])
    if not isinstance(extras, list):
        raise ValueError("test_paths must be a list of relative oracle paths")
    return {
        "task_id": f"{dataset}/{local_id}", "dataset": dataset,
        "source_relative": _relative(value["source"], "source"),
        "task_relative": _relative(value["task_file"], "task_file", metadata=True),
        "test_command": list(command),
        "test_paths": sorted({_relative(item, "test_paths") for item in extras}),
    }


def build_plan(
    task_index: str | os.PathLike[str], *,
    polyglot: str | os.PathLike[str] | None = None,
    quixbugs: str | os.PathLike[str] | None = None,
    dataset_set: str = "both", limit: int | None = None, runs: int = 2,
) -> dict[str, object]:
    """Validate selected indexed tasks and expand them into deterministic runs.

    All selected tasks are validated before the global task limit is applied.
    This function only reads JSON, prompt text, and filesystem metadata. It never
    imports an exercise, collects tests, prepares copies, or starts a process.
    """
    if dataset_set not in (*DATASETS, "both"):
        raise ValueError("set must be polyglot, quixbugs, or both")
    _positive(runs, "runs")
    if limit is not None:
        _positive(limit, "limit")
    selected = DATASETS if dataset_set == "both" else (dataset_set,)
    supplied = {"polyglot": polyglot, "quixbugs": quixbugs}
    roots = {}
    for dataset in selected:
        if supplied[dataset] is None:
            raise ValueError(f"An explicit --{dataset} dataset root is required")
        root = Path(supplied[dataset]).absolute()
        if not _is_directory(root):
            raise ValueError(f"Dataset root must be a directory: {root}")
        roots[dataset] = root.resolve(strict=True)

    index_path = Path(task_index)
    if _is_directory(index_path):
        raise ValueError(f"Task index must be a regular JSON file: {index_path}")
    document = json.loads(index_path.read_bytes().decode("utf-8"), object_pairs_hook=_object)
    if (
        not isinstance(document, dict) or set(document) != {"schema_version", "tasks"}
        or type(document["schema_version"]) is not int or document["schema_version"] != 1
        or not isinstance(document["tasks"], list)
    ):
        raise ValueError("Task index must contain schema_version: 1 and a tasks list")
    entries = [_entry(item) for item in document["tasks"]]
    ids = set()
    for entry in entries:
        if entry["task_id"] in ids:
            raise ValueError(f"Duplicate task ID: {entry['task_id']}")
        ids.add(entry["task_id"])

    tasks = []
    for entry in sorted(entries, key=lambda item: item["task_id"]):
        dataset = entry["dataset"]
        if dataset not in selected:
            continue
        root = roots[dataset]
        source = _inside(root, entry["source_relative"], directory=True)
        inventory = list(_inventory(source))
        if not any(not is_directory for _, is_directory in inventory):
            raise ValueError(f"Exercise has no ordinary files outside .meta/: {source}")
        for previous in tasks:
            other = Path(previous["source_path"])
            if source == other or source in other.parents or other in source.parents:
                raise ValueError(
                    f"Ambiguous overlapping sources: {previous['task_id']} and {entry['task_id']}"
                )
        prompt_path = _inside(root, entry["task_relative"], directory=False)
        prompt = prompt_path.read_bytes().decode("utf-8")
        if not prompt.strip():
            raise ValueError(f"Task prompt is empty: {prompt_path}")
        for path in entry["test_paths"]:
            current = source
            for part in path.parts:
                current /= part
                _is_directory(current)
        command = entry["test_command"]
        task_text = prompt + "\n\nTest command: " + shlex.join(command) + "\n"
        tasks.append({
            "task_id": entry["task_id"], "dataset": dataset,
            "source_path": str(source),
            "source_relative": entry["source_relative"].as_posix(),
            "task_file": str(prompt_path), "task_text": task_text,
            "task_text_sha256": hashlib.sha256(task_text.encode("utf-8")).hexdigest(),
            "test_command": command,
            "test_paths": [path.as_posix() for path in entry["test_paths"]],
        })
    for dataset in selected:
        if not any(task["dataset"] == dataset for task in tasks):
            raise ValueError(f"No indexed tasks found for selected dataset: {dataset}")

    indexed_count = len(tasks)
    tasks = tasks[:limit] if limit is not None else tasks
    repeats = {"crocodile": runs, "mini-swe-agent": runs, "all-off-twin": 1}
    planned = [
        {
            **task,
            "run_id": f"{task['task_id']}/{agent}/run-{number}",
            "agent_variant": agent, "run_number": number,
            "step_cap": 30, "wall_clock_cap_seconds": 600,
        }
        for task in tasks for agent in AGENTS for number in range(1, repeats[agent] + 1)
    ]
    return {
        "schema_version": 1, "kind": "benchmark-run-plan", "execution_enabled": False,
        "selection": {"set": dataset_set, "limit": limit},
        "dataset_roots": {dataset: str(roots[dataset]) for dataset in selected},
        "evaluation_policy": {
            "model": "anthropic/claude-haiku-5-5", "thinking": "adaptive", "effort": "medium",
            "gateway": "Bifrost", "semantic_cache": False, "prompt_caching": True,
            "mini_swe_agent_version": "2.4.6", "parallel_runs": 4,
            "grading_timeout_seconds": 180,
        },
        "indexed_task_count": indexed_count, "task_count": len(tasks),
        "run_count": len(planned), "runs_per_task": repeats,
        "tasks_by_dataset": {
            dataset: sum(task["dataset"] == dataset for task in tasks) for dataset in selected
        },
        "runs_by_agent": {agent: len(tasks) * repeats[agent] for agent in AGENTS},
        "tasks": tasks, "runs": planned,
    }


def write_manifest(plan: dict[str, object], output: str | os.PathLike[str]) -> Path:
    """Write a new manifest only; refuse to modify a dataset or existing output."""
    destination = Path(output).absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"Output manifest already exists: {destination}")
    destination = destination.resolve(strict=False)
    for value in plan["dataset_roots"].values():
        root = Path(value)
        if destination == root or root in destination.parents:
            raise ValueError("Output manifest must be outside the selected dataset roots")
    # Serialize before opening; exclusive creation also protects a racing writer.
    contents = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    stream = destination.open("x", encoding="utf-8", newline="\n")
    try:
        with stream:
            stream.write(contents)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", choices=(*DATASETS, "both"), default="both")
    parser.add_argument("--polyglot", type=Path)
    parser.add_argument("--quixbugs", type=Path)
    parser.add_argument("--task-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Explicit planning-only mode; this command never executes runs",
    )
    args = parser.parse_args(argv)
    try:
        plan = build_plan(
            args.task_index, polyglot=args.polyglot, quixbugs=args.quixbugs,
            dataset_set=args.set, limit=args.limit, runs=args.runs,
        )
        destination = write_manifest(plan, args.output)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Planning failed: {error}\n")
    label = "Dry run" if args.dry_run else "Plan"
    print(f"{label}: {plan['task_count']} tasks / {plan['indexed_task_count']} indexed; "
          f"{plan['run_count']} runs")
    print("Tasks by dataset: " + json.dumps(plan["tasks_by_dataset"], sort_keys=True))
    print("Runs by agent: " + json.dumps(plan["runs_by_agent"], sort_keys=True))
    print(f"Manifest: {destination}")
    print("No agents or tests executed; costs are not estimated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
