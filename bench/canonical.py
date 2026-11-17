"""Read-only validation of the frozen, non-executable Gemini benchmark snapshot."""

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from bench.plan import AGENTS, EVALUATION_POLICY, SHARD_RANGES, TEST_PREFIX, _object, _relative, build_plan
from bench.prepare import _inventory
from bench.run import _validate
from bench.bifrost_export import (
    COMPONENT_ULPS, COMPONENT_ABSOLUTE_CAP, COMPONENT_RELATIVE_CAP,
    NULL_MODEL_RULE, NULL_ROUTE_FIELDS, ZERO_ROUTE_FIELDS,
)


DEFAULT_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v1.json"
V2_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v2.json"
V3_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v3.json"
V4_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v4.json"
V5_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v5.json"
V6_CONFIG = Path(__file__).parent / "configs" / "gemini-benchmark-v6.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
ACCEPTED_LIMITATIONS = {"hard-stop-containment", "mini-output-cap", "cache-parity", "sampling-difference"}
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


def validate_config(config, *, repo_root=REPO_ROOT, data_root=None, manifests=(), audit_current=False):
    """Validate immutable release snapshots; static success is not authorization.

    Optional data_root is the assembled builder output, not a native checkout.
    Optional manifests must contain one full plan and all four shard plans.
    audit_current reports source drift without accepting it. No exercise imports,
    pytest, mini, gateway, credential or SQLite access occurs.
    """
    try:
        _need(isinstance(config, dict), "Invalid canonical config fields")
        revision = config.get("revision")
        versions = {"gemini-54-v1": 1, "gemini-54-v2": 2, "gemini-54-v3": 3, "gemini-54-v4": 4,
                    "gemini-54-v5": 5, "gemini-54-v6": 6}
        modern = revision in versions and versions[revision] >= 2
        change_field = f"changes_from_v{versions[revision] - 1}" if modern else "changes_from_v1"
        fields = TOP_FIELDS | {change_field, "known_limitations"} if modern else TOP_FIELDS
        _need(set(config) == fields, "Invalid canonical config fields")
        _need(type(config["schema_version"]) is int
              and config["schema_version"] == versions.get(revision)
              and config["kind"] == "canonical-gemini-benchmark"
              and revision in versions, "Unsupported canonical revision")
        _key_free(config)
        ready = config["readiness"]
        _need(ready["paid_runs_authorized"] is False and ready["cross_shard_comparable"] is False,
              "This blocked release snapshot cannot authorize execution or comparability")
        gaps = ready["unresolved"]
        _need(isinstance(gaps, list) and gaps, "Unresolved evidence cannot be erased from this release")
        _need(len({g["id"] for g in gaps}) == len(gaps)
              and all(all(isinstance(g[k], str) and g[k].strip() for k in ("id", "owner", "reason"))
                      for g in gaps), "Invalid unresolved evidence")
        if modern:
            limitations = config["known_limitations"]
            _need(isinstance(limitations, list) and len(limitations) == 4
                  and {item["id"] for item in limitations} == ACCEPTED_LIMITATIONS
                  and all(item["comparability_gate"] is False and item["accepted_by"] == "Atul"
                          and isinstance(item["description"], str) and item["description"].strip()
                          for item in limitations), "Accepted limitations must not become comparability gates")
            _need(not ACCEPTED_LIMITATIONS.intersection(g["id"] for g in gaps),
                  "Accepted limitation listed as a release blocker")
            _need(versions[revision] >= 5 or "mini-attempt-3a111322" in {g["id"] for g in gaps},
                  "Unresolved mini attempt cannot be cleared without a new reviewed release")
            _need(isinstance(config[change_field], list) and config[change_field],
                  "Release requires a change record")
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
        if modern:
            observed = gateway["live_evidence"]
            _need(observed["status"] == "reported-verified-on-Atul-machine"
                  and observed["independently_verified_here"] is False,
                  "Remote gateway evidence must not be promoted to local verification")
        model = EVALUATION_POLICY["model"]
        _need(set(agents) == set(AGENTS), "Agent variants differ")
        for name, agent in agents.items():
            _need(agent["wire_model"] == model and agent["fallbacks"] == []
                  and agent["measured_escalation"] is False
                  and agent["thinking"] == "provider-default"
                  and agent["sampling"] == ("native-0.0-or-0.7" if modern and name != "mini-swe-agent" else "omit"),
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
        if versions[revision] >= 3:
            _need({"bench/mini.py", "bench/prepare.py", "bench/failure_evidence.py",
                   "bench/canonical.py", "bench/attest.py"} <= sources.keys(),
                  f"Missing v{versions[revision]} diagnostic/runtime pins")
        if versions[revision] >= 4:
            policy = config["evidence"]["logged_component_precision"]
            _need(policy == {"binary64_ulps": COMPONENT_ULPS, "absolute_cap_usd": "1e-12",
                             "relative_cap": "1e-12", "zero_nonzero_match": False,
                             "raw_evidence_rewritten": False, "price_check": "separate-strictly-greater-than-1-percent"}
                  and Fraction(policy["absolute_cap_usd"]) == COMPONENT_ABSOLUTE_CAP
                  and Fraction(policy["relative_cap"]) == COMPONENT_RELATIVE_CAP,
                  "V4 component precision policy differs from exporter")
        if versions[revision] >= 5:
            evidence = config["evidence"]
            _need(evidence["null_served_model_rule"] == {
                "revision": NULL_MODEL_RULE, "required_null_columns": list(NULL_ROUTE_FIELDS),
                "required_integer_zero_columns": list(ZERO_ROUTE_FIELDS),
                "per_request_routing_join_required": True, "blanket_null_inference": False,
            }, "V5 null-model policy differs from exporter")
            _need(sources["prices.yaml"] == "8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e",
                  "V5 approved price snapshot differs")
            expected = {"bench/evidence/croc-native-pilot-v4-review.json", "bench/evidence/croc-native-routing-proof.json"}
            pins = evidence["reviewed_artifacts_sha256_lf"]
            _need(isinstance(pins, dict) and set(pins) == expected, "V5 evidence pins missing")
            for name, digest in pins.items():
                _need(_sha((root / name).read_bytes().replace(b"\r\n", b"\n")) == digest,
                      "V5 reviewed evidence changed")
            review = _json(root / "bench/evidence/croc-native-pilot-v4-review.json")
            _need(review["native_call_count"] == review["native_call_price_reconciliations"] == 4
                  and review["pilot"]["attempts"] == 18 and review["pilot"]["final_grades_solved"] == 15
                  and review["pilot"]["all_18_pilot_rows_incomplete"] is True
                  and review["pilot"]["pooled_report_eligible"] is False
                  and review["pilot"]["authoritative_cost_complete"] is False,
                  "V5 cannot promote historical pilot evidence")
            _need(config["pooling"]["pre_v5_cohorts_report_eligible"] is False
                  and evidence["historical_pilot_report_eligible"] is False,
                  "V5 historical pilot must stay nonreportable")
            _need({g["id"] for g in gaps} == {"post-restart-per-machine-cost-inventory"},
                  "V5 requires reviewed post-restart per-machine cost evidence")
        _need(config["evidence"]["canonical_native_prices_sha256"] == sources["prices.yaml"],
              "Canonical price snapshot differs")
        drift = []
        for relative, digest in sources.items():
            path = root / _relative(relative, "runtime source")
            _need(root in path.resolve().parents, "Runtime source escapes repository")
            actual = _sha(path.read_bytes().replace(b"\r\n", b"\n"))
            if actual != digest:
                drift.append({"path": relative, "frozen_sha256": digest, "current_sha256": actual})
        _need(audit_current or not drift, "Runtime source snapshot differs")
        result = {"revision": config["revision"], "config_id": config_id(config), "static_valid": not drift,
                  "contract_valid": True, "runtime_matches_snapshot": not drift, "runtime_drift": drift,
                  "runtime_git_commit": config["provenance"]["runtime_git_commit"],
                  "validator_sha256_lf": _sha(Path(__file__).read_bytes().replace(b"\r\n", b"\n")),
                  "dataset_validated": False, "manifests_validated": 0,
                  "paid_runs_authorized": False, "cross_shard_comparable": False, "unresolved": gaps,
                  "known_limitations": config.get("known_limitations", [])}
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
                _need(not modern or "\r" not in task["task_text"], "Release requires LF-only task text")
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
    parser.add_argument("--audit-current", action="store_true",
                        help="Report runtime drift as invalid evidence; never waive the frozen snapshot")
    args = parser.parse_args(argv)
    try:
        result = validate_config(_json(args.config), data_root=args.data_root, manifests=args.plans or (),
                                 audit_current=args.audit_current)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Canonical validation failed: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if args.require_comparable:
        return 0 if result["static_valid"] and result["cross_shard_comparable"] else 1
    return 0 if result["static_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
