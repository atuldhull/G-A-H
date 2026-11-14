"""Read-only validation of the frozen, non-executable Gemini benchmark snapshot."""

import argparse
import hashlib
import json
from pathlib import Path

from bench.plan import AGENTS, EVALUATION_POLICY, SHARD_RANGES, TEST_PREFIX, _object, _relative, build_plan
from bench.prepare import _inventory
from bench.run import _validate


DEFAULT_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v1.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
TOP_FIELDS = {
    "schema_version", "kind", "revision", "provenance", "datasets", "plan", "gateway",
    "agents", "limits", "grading", "evidence", "outcomes", "pooling", "readiness",
}


def _fail(message):
    raise ValueError(message)


def _need(condition, message):
    if not condition:
        _fail(message)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_object,
                      parse_constant=lambda _: _fail("Non-finite JSON value"))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def config_id(config):
    """Portable ID: sorted compact ASCII JSON; independent of checkout CRLF."""
    return _sha(json.dumps(config, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii"))


def source_digest(root):
    """Hash exact ordinary input bytes; exclude metadata and generated caches.

    The builder's MANIFEST tree hashes include pytest bytecode/absolute paths.
    This separate cross-machine digest neither hashes bytecode nor normalizes
    exercise line endings. Inventory rejects links/junctions without executing code.
    """
    root = Path(root)
    files = []
    for relative, directory in _inventory(root):
        if (directory or any(p.casefold() in {"__pycache__", ".pytest_cache"} for p in relative.parts)
                or relative.suffix.casefold() in {".pyc", ".pyo"}):
            continue
        files.append([relative.as_posix(), _sha((root / relative).read_bytes())])
    return _sha(json.dumps(sorted(files), separators=(",", ":"), ensure_ascii=True).encode("ascii"))


def _key_free(value):
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "authorization", "secret", "vk_value", "credential_value"}
        _need(not forbidden.intersection(k.casefold() for k in value), "Credential-value field forbidden")
        for child in value.values():
            _key_free(child)
    elif isinstance(value, list):
        for child in value:
            _key_free(child)


def validate_config(config, *, repo_root=REPO_ROOT, data_root=None, manifests=()):
    """Validate static consistency; v1 can never authorize runs or pooled claims.

    Optional data_root is the assembled builder output, not a native checkout.
    Optional manifests must contain one full plan and all four shard plans.
    No exercise imports, pytest, mini, gateway, credential or SQLite access occurs.
    """
    try:
        _need(isinstance(config, dict) and set(config) == TOP_FIELDS, "Invalid canonical config fields")
        _need(type(config["schema_version"]) is int and config["schema_version"] == 1
              and config["kind"] == "canonical-gemini-benchmark"
              and config["revision"] == "gemini-54-v1", "Unsupported canonical revision")
        _key_free(config)
        ready = config["readiness"]
        _need(ready["paid_runs_authorized"] is False and ready["cross_shard_comparable"] is False,
              "This v1 snapshot cannot authorize execution or comparability")
        gaps = ready["unresolved"]
        _need(isinstance(gaps, list) and gaps, "Unresolved evidence cannot be erased from v1")
        _need(len({g["id"] for g in gaps}) == len(gaps)
              and all(all(isinstance(g[k], str) and g[k].strip() for k in ("id", "owner", "reason"))
                      for g in gaps), "Invalid unresolved evidence")
        plan = config["plan"]
        _need(plan["evaluation_policy"] == EVALUATION_POLICY, "Planner policy differs from canonical config")
        _need(plan["shard_ranges"] == [list(r) for r in SHARD_RANGES], "Shard ranges differ")
        order = plan["task_order"]
        _need(len(order) == len(set(order)) == 54 and order == sorted(order)
              and sum(t.startswith("polyglot/") for t in order) == 34
              and sum(t.startswith("quixbugs/") for t in order) == 20, "Invalid full task order")
        expected_order = [[a, n] for a in AGENTS for n in range(1, 2 if a == "all-off-twin" else 3)]
        _need(plan["run_order_per_task"] == expected_order and plan["total_runs"] == 270,
              "Run order/count differs from 2+2+1")
        _need(plan["shard_task_counts"] == [14, 14, 13, 13]
              and plan["shard_run_counts"] == [70, 70, 65, 65], "Shard counts differ")
        gateway, agents = config["gateway"], config["agents"]
        _need(gateway["version"] == "2.5.1" and gateway["endpoint"] == EVALUATION_POLICY["gateway_url"]
              and gateway["virtual_key_id"] == EVALUATION_POLICY["virtual_key_id"]
              and gateway["virtual_key_name"] == EVALUATION_POLICY["virtual_key_name"], "Gateway/VK mismatch")
        _need(gateway["physical_version_vk_and_cap_verified"] is False
              and config["provenance"]["observed_environment_versions"]["cross_machine_lock_verified"] is False,
              "Live/environment verification cannot be asserted by this snapshot")
        model = EVALUATION_POLICY["model"]
        _need(set(agents) == set(AGENTS), "Agent variants differ")
        for name, agent in agents.items():
            _need(agent["wire_model"] == model and agent["fallbacks"] == []
                  and agent["measured_escalation"] is False
                  and agent["thinking"] == "provider-default" and agent["sampling"] == "omit",
                  "Agent model/override policy mismatch")
        _need(agents["crocodile"]["flags"] is None and agents["all-off-twin"]["flags"] == [],
              "Crocodile/twin flags differ")
        _need(agents["crocodile"]["requested_max_output_tokens"] == 4096
              and agents["all-off-twin"]["requested_max_output_tokens"] == 4096
              and agents["mini-swe-agent"]["requested_max_output_tokens"] is None,
              "Observed output-cap difference must remain explicit")
        mini = _json(Path(repo_root) / "bench/configs/mini-2.4.6.json")
        native = _json(Path(repo_root) / "bench/configs/crocodile-gemini-bench.json")
        _need(agents["mini-swe-agent"]["model_argument"] == mini["model"]["model_name"] == "openai/" + model
              and agents["mini-swe-agent"]["version"] == mini["mini_version"] == "2.4.6",
              "Mini version/model mismatch")
        _need(mini["model"]["model_kwargs"] == {"drop_params": True, "extra_body": {"fallbacks": []}}
              and mini["model"]["set_cache_control"] == "default_end"
              and mini["thinking_policy"]["thinking"] == mini["thinking_policy"]["effort"] == "provider-default"
              and agents["mini-swe-agent"]["template_git_blob"] == mini["default_template_git_blob"]
              and agents["mini-swe-agent"]["cost_tracking"] == mini["model"]["cost_tracking"] == "ignore_errors",
              "Mini kwargs/cache mismatch")
        for name in ("crocodile", "all-off-twin"):
            _need(agents[name]["chains"] == native["models"]
                  and native["bifrost_url"] == gateway["endpoint"], "Native profile mismatch")
        limits, grading = config["limits"], config["grading"]
        _need(limits["steps"] == 30 and limits["wall_seconds"] == 600
              and limits["hard_deadline_enforced"] is False, "Unsupported cap claim")
        _need(mini["agent"] == {"step_limit": 30, "wall_time_limit_seconds": 600, "cost_limit": 0},
              "Mini caps differ")
        _need(grading["command"] == TEST_PREFIX and grading["timeout_seconds"] == 180
              and grading["fresh_copy"] is True and grading["restore_original_tests"] is True,
              "Independent grading policy differs")
        root = Path(repo_root).resolve()
        sources = config["provenance"]["runtime_files_sha256_lf"]
        _need({"bench/run.py", "bench/mini_bridge.py", "bench/grade.py", "bench/bifrost_export.py",
               "crocodile/adapters.py", "prices.yaml"} <= sources.keys(), "Missing required runtime pins")
        _need(config["evidence"]["canonical_native_prices_sha256"] == sources["prices.yaml"],
              "Canonical price snapshot differs")
        for relative, digest in sources.items():
            path = root / _relative(relative, "runtime source")
            _need(root in path.resolve().parents, "Runtime source escapes repository")
            _need(_sha(path.read_bytes().replace(b"\r\n", b"\n")) == digest, "Runtime source snapshot differs")
        result = {"revision": config["revision"], "config_id": config_id(config), "static_valid": True,
                  "runtime_git_commit": config["provenance"]["runtime_git_commit"],
                  "validator_sha256_lf": _sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
                  "dataset_validated": False, "manifests_validated": 0,
                  "paid_runs_authorized": False, "cross_shard_comparable": False, "unresolved": gaps}
        if data_root is not None:
            data = Path(data_root).resolve()
            for filename, field in (("tasks.json", "tasks_sha256"), ("oracles.json", "oracles_sha256")):
                _need(_sha((data / filename).read_bytes()) == config["datasets"][field], "Dataset JSON hash mismatch")
            full = build_plan(data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs")
            _need(full["full_plan"]["id"] == plan["full_plan_id"]
                  and full["full_plan"]["task_ids"] == order, "Full-plan identity/order mismatch")
            oracles = _json(data / "oracles.json")
            _validate(full, oracles)
            _need(set(config["datasets"]["tasks"]) == set(order), "Task evidence coverage mismatch")
            for task in full["tasks"]:
                frozen = config["datasets"]["tasks"][task["task_id"]]
                source = Path(task["source_path"])
                _need(task["task_text_sha256"] == frozen["task_text_sha256"]
                      and source_digest(source) == frozen["source_sha256"], "Task text/source digest mismatch")
                for target in oracles[task["task_id"]]:
                    original = source / _relative(target.split("::")[0], "oracle")
                    _need(original.exists() and source in original.resolve().parents, "Missing/escaping oracle")
            result["dataset_validated"] = True
            selected = set()
            for filename in manifests:
                actual = _json(filename)
                shard = actual["selection"]["shard"]
                _need(shard in (None, "1/4", "2/4", "3/4", "4/4") and shard not in selected,
                      "Unknown/duplicate manifest shard")
                expected = full if shard is None else build_plan(
                    data / "tasks.json", polyglot=data / "polyglot", quixbugs=data / "quixbugs", shard=shard)
                _need(actual == expected, "Dry-run manifest differs from frozen input/policy")
                selected.add(shard)
            _need(not manifests or selected == {None, "1/4", "2/4", "3/4", "4/4"},
                  "Provide the full plan and all four shards")
            result["manifests_validated"] = len(selected)
        else:
            _need(not manifests, "Manifest validation requires the assembled data root")
        return result
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError("Missing or invalid canonical configuration/evidence") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--plans", type=Path, nargs="*")
    parser.add_argument("--require-comparable", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate_config(_json(args.config), data_root=args.data_root, manifests=args.plans or ())
    except (OSError, ValueError) as error:
        parser.exit(2, f"Canonical validation failed: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 1 if args.require_comparable else 0  # v1 is permanently gated, not an execution switch.


if __name__ == "__main__":
    raise SystemExit(main())
