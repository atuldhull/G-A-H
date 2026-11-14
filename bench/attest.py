"""Create immutable, key-free plan attestations without dispatching any work."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from bench.canonical import DEFAULT_CONFIG, REPO_ROOT, _json, _key_free, validate_config
from bench.plan import build_plan
from bench.run import _validate


def encoded(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(repo, *args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", str(repo), *args], text=True).strip()


def attest_plan(config_path, data_root, plan_path, oracles, *, repo_root=REPO_ROOT, mini_identity=None):
    """Bind inputs and current source; drift is recorded, never authorized.

    Only local Git metadata, JSON, prompt/source bytes and file hashes are read.
    No keys, SQLite, exercise imports, agents, mini or test execution is used.
    """
    repo = Path(repo_root).resolve()
    config_path, plan_path = Path(config_path).resolve(), Path(plan_path).resolve()
    data = Path(data_root).resolve()
    config = _json(config_path)
    report = validate_config(config, repo_root=repo, data_root=data, audit_current=True)
    plan = _json(plan_path)
    _validate(plan, oracles)
    selection = plan["selection"]
    expected = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs",
                          dataset_set=selection["set"], limit=selection["limit"], shard=selection["shard"])
    if expected != plan or plan["full_plan"]["id"] != config["plan"]["full_plan_id"]:
        raise ValueError("Plan is not an exact selection from the frozen experiment")
    full_oracles = _json(data / "oracles.json")
    selected = {task["task_id"]: full_oracles[task["task_id"]] for task in plan["tasks"]}
    if oracles != selected:
        raise ValueError("Oracle subset differs from frozen originals")
    sources = dict(config["provenance"]["runtime_files_sha256_lf"])
    sources.update({"bench/attest.py": None, "bench/canonical.py": None})
    current = {name: _sha((repo / name).read_bytes().replace(b"\r\n", b"\n")) for name in sorted(sources)}
    mini_ready = False
    if mini_identity is not None:
        if not isinstance(mini_identity, dict) or set(mini_identity) != {"settings", "config", "bridge_sha256"}:
            raise ValueError("Unexpected mini identity fields")
        _key_free(mini_identity)
        from bench.mini import Settings
        settings = Settings(**mini_identity["settings"])
        if (settings.api_base != config["gateway"]["mini_api_base"]
                or settings.credential_env != config["gateway"]["credential_env_name"]
                or mini_identity["config"] != _json(repo / "bench/configs/mini-2.4.6.json")
                or mini_identity["bridge_sha256"] != _sha((repo / "bench/mini_bridge.py").read_bytes())):
            raise ValueError("Effective mini identity differs from canonical profile/transport")
        mini_ready = settings.session_header_verified
    clean = not _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    try:
        publication = _git(repo, "log", "-1", "--format=%H", "--", config_path.relative_to(repo).as_posix())
    except ValueError:  # Untracked external test config has no publication provenance.
        publication = ""
    complete_shard = selection["limit"] is None
    allowed = (report["static_valid"] and report["paid_runs_authorized"]
               and report["cross_shard_comparable"] and clean and bool(publication) and mini_ready)
    return {
        "schema_version": 1, "kind": "benchmark-config-attestation",
        "canonical_revision": report["revision"], "canonical_config_id": report["config_id"],
        "canonical_config_raw_sha256": _sha(config_path.read_bytes()),
        "canonical_publication_git_commit": publication or None,
        "frozen_runtime_git_commit": report["runtime_git_commit"],
        "runtime_git_commit": _git(repo, "rev-parse", "HEAD"), "worktree_clean": clean,
        "runtime_files_sha256_lf": current, "runtime_drift": report["runtime_drift"],
        "effective_mini_identity": mini_identity, "reviewed_mini_header_supplied": mini_ready,
        "plan_sha256": _sha(plan_path.read_bytes()), "full_plan_id": plan["full_plan"]["id"],
        "oracle_snapshot_sha256": _sha(encoded(oracles)),
        "task_index_sha256": config["datasets"]["tasks_sha256"],
        "full_oracle_index_sha256": config["datasets"]["oracles_sha256"],
        "selection": selection, "task_ids": [t["task_id"] for t in plan["tasks"]],
        "run_ids": [r["run_id"] for r in plan["runs"]], "task_count": plan["task_count"],
        "run_count": plan["run_count"],
        "scope": "full-or-shard" if complete_shard else "development-smoke",
        "canonical_comparability_ready": report["cross_shard_comparable"],
        "eligible_for_pooled_report": bool(allowed and complete_shard),
        "execution_authorized": bool(allowed), "unresolved": report["unresolved"],
        "historical_snapshot_notice": "Frozen release entries are historical; current audit does not rewrite them.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mini-settings", type=Path, help="Key-free effective mini transport settings")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        data = args.data_root.resolve()
        if output == data or data in output.parents:
            raise ValueError("Attestation output must stay outside the dataset")
        mini_identity = None
        if args.mini_settings is not None:
            from bench.mini import MiniAdapter, Settings
            mini_identity = MiniAdapter(Settings(**_json(args.mini_settings))).identity()
        result = attest_plan(args.config, data, args.plan, _json(args.oracles), mini_identity=mini_identity)
        with output.open("xb") as stream:
            stream.write(encoded(result))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Attestation failed ({type(error).__name__}); no work dispatched.\n")
    print(json.dumps({key: result[key] for key in (
        "canonical_config_id", "task_count", "run_count", "scope", "execution_authorized",
        "eligible_for_pooled_report")}, sort_keys=True))
    return 0  # Artifact creation only; never an execution/readiness signal.


if __name__ == "__main__":
    raise SystemExit(main())
