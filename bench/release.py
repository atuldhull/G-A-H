"""Prepare validated plans/oracle subsets and commands, without dispatching work."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys

from bench.canonical import REPO_ROOT, V2_CONFIG, _json, validate_config
from bench.mini import Settings
from bench.plan import build_plan, write_manifest


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tree_hash(root):
    # Builder-local evidence includes bytecode. Portable source hashes are
    # independently validated by canonical.source_digest; do not conflate them.
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:16]


def validate_builder_manifest(data, config):
    text = (data / "MANIFEST.md").read_text(encoding="utf-8")
    for expected in (config["datasets"]["tasks_sha256"], config["datasets"]["oracles_sha256"],
                     *(item["commit"] for item in config["datasets"]["upstreams"].values())):
        if expected not in text:
            raise ValueError("Builder MANIFEST is missing a pinned input hash/commit")
    rows = re.findall(r"^- ((?:polyglot|quixbugs)/[a-z0-9._-]+) `([0-9a-f]{16})`$", text, re.MULTILINE)
    if len(rows) != 54 or {name for name, _ in rows} != set(config["plan"]["task_order"]):
        raise ValueError("Builder MANIFEST must cover all 54 tasks exactly once")
    for name, digest in rows:
        if _tree_hash(data / name) != digest:
            raise ValueError(f"Builder MANIFEST local tree hash differs: {name}")


def _write(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def prepare_release(config_path, data_root, output, mini_settings):
    """New output only. Read local inputs; never invoke agents, tests or services.

    The returned commands are evidence, not execution authorization. If artifact
    writing fails, the partial directory must not be used; choose a new output.
    """
    config_path, data = Path(config_path).resolve(), Path(data_root).resolve()
    output = Path(output).resolve()
    if output.exists() or output == data or data in output.parents or output in data.parents:
        raise ValueError("Choose a fresh output outside the dataset")
    if output == REPO_ROOT or REPO_ROOT in output.parents:
        raise ValueError("Release artifacts belong outside the repository")
    config = _json(config_path)
    report = validate_config(config, data_root=data)
    validate_builder_manifest(data, config)
    settings = Settings(**_json(mini_settings))
    if (settings.api_base != config["gateway"]["mini_api_base"]
            or settings.credential_env != config["gateway"]["credential_env_name"]):
        raise ValueError("Mini transport differs from canonical profile")
    all_oracles = _json(data / "oracles.json")
    plans = [build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs",
                        shard=shard) for shard in (None, "1/4", "2/4", "3/4", "4/4")]
    output.mkdir()  # No overwrite/resume of a partly written release bundle.
    _write(output / "mini-settings.json", asdict(settings))
    manifests, artifacts, commands = [], {}, {}
    for label, plan in zip(("full", "shard-1", "shard-2", "shard-3", "shard-4"), plans):
        manifest = write_manifest(plan, output / f"{label}.json")
        manifests.append(manifest)
        subset = {task["task_id"]: all_oracles[task["task_id"]] for task in plan["tasks"]}
        oracle_path = output / f"{label}-oracles.json"
        _write(oracle_path, subset)
        artifacts[label] = {"tasks": plan["task_count"], "runs": plan["run_count"],
                            "plan_sha256": _sha(manifest), "oracles_sha256": _sha(oracle_path)}
        commands[label] = [sys.executable, "-m", "bench.run", "--plan", str(manifest),
                           "--oracles", str(oracle_path), "--output", str(output / f"{label}-results"),
                           "--mini-settings", str(output / "mini-settings.json"),
                           "--canonical-config", str(config_path), "--canonical-data-root", str(data),
                           "--execute"]
    verified = validate_config(config, data_root=data, manifests=manifests)
    result = {"kind": "benchmark-release-preparation", "schema_version": 1,
              "revision": config["revision"], "config_id": report["config_id"],
              "full_plan_id": config["plan"]["full_plan_id"], "artifacts": artifacts,
              "builder_manifest_sha256": _sha(data / "MANIFEST.md"),
              "mini_settings_sha256": _sha(output / "mini-settings.json"),
              "validation": verified, "commands_not_executed": commands,
              "launch_blocked": True}
    _write(output / "release-preparation.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=V2_CONFIG)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mini-settings", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_release(args.config, args.data_root, args.output, args.mini_settings)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Release preparation failed: {error}\n")
    for label, artifact in result["artifacts"].items():
        print(f"{label}: {artifact['tasks']} tasks / {artifact['runs']} slots")
    print(f"Config: {result['config_id']}; launch BLOCKED; no work dispatched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
