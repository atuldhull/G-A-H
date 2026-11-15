"""Explicit non-comparative 3-task pilot. Never authorize a benchmark/shard."""

import argparse
import hashlib
from pathlib import Path

from bench.attest import attest_plan, encoded
from bench.canonical import REPO_ROOT, V4_CONFIG, _json
from bench.run import _append, _rows, _save, run_plan


V4_ID = "026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4"
TASKS = ["polyglot/affine-cipher", "polyglot/beer-song", "polyglot/book-store"]
REVIEW = Path(__file__).with_name("evidence") / "atul-20261115-closed-binding-review.json"
INCOMPLETE = ["native-Crocodile-policy-binding-unverified", "served-model-resolver-unreviewed",
              "per-machine-complete-cost-evidence-pending", "historical-cohort-review-pending"]


def _scope(proof):
    if (proof["canonical_config_id"] != V4_ID or proof["runtime_drift"]
            or not proof["worktree_clean"] or not proof["canonical_publication_git_commit"]
            or proof["task_ids"] != TASKS or proof["task_count"] != 3 or proof["run_count"] != 15
            or proof["selection"].get("shard") != "1/4" or proof["selection"].get("limit") != 3
            or proof["scope"] != "development-smoke"
            or proof["execution_authorized"] or proof["canonical_comparability_ready"]
            or len(set(proof["run_ids"])) != 15 or proof["effective_mini_identity"] is None):
        raise ValueError("Pilot requires clean unchanged v4, exact first three tasks/15 slots and explicit mini settings")
    # attest_plan has already rebuilt the exact task/variant/repeat order and
    # validated every oracle and source against the immutable full plan.
    reviewed = _json(REVIEW)
    if not reviewed["internal_checks_passed"] or reviewed["native_crocodile_binding_verified"]:
        raise ValueError("This incomplete-only pilot requires the unchanged reviewed evidence disposition")
    return {"schema_version": 1, "kind": "limited-noncomparative-pilot-attestation",
            "canonical_attestation": proof, "pilot_wrapper_sha256_lf": hashlib.sha256(
                Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "review_sha256_lf": hashlib.sha256(REVIEW.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "Atul_source_evidence_sha256": reviewed["sources_sha256"],
            "pilot_scope": "only-reviewed-first-three-tasks", "report_eligible": False,
            "canonical_comparability_ready": False, "incomplete_reasons": INCOMPLETE}


def _collect(raw_path, output, proof_hash):
    existing = _rows(output)
    known = {r["attempt_id"] for r in existing}
    if len(known) != len(existing) or any(
        r.get("pilot_attestation_sha256") != proof_hash or r.get("status") != "incomplete"
        for r in existing
    ):
        raise ValueError("Conflicting pilot evidence; preserve files for manual review")
    for raw in _rows(raw_path):
        if raw["attempt_id"] in known:
            continue
        row = dict(raw)
        row.update(status="incomplete", solved=None, observed_execution_status=raw["status"],
                   observed_graded_solved=raw.get("solved"), report_eligible=False,
                   eligible_for_pooled_report=False, complete=False,
                   canonical_config_id=V4_ID, pilot_attestation_sha256=proof_hash,
                   scope="noncomparative-limited-pilot", incomplete_reasons=INCOMPLETE,
                   authoritative_cost_complete=False)
        _append(output, row)
        known.add(raw["attempt_id"])
    return _rows(output)


def run_pilot(plan, output, *, oracles, config, data_root, mini_adapter, retry_incomplete=False):
    """Retain raw execution evidence and append incomplete-only pilot records.

    No global ready flag is overridden. This separate, explicitly opted-in
    development scope cannot accept a full plan/shard or a changed oracle.
    Raw executor records describe execution/grades only; the outer pilot ledger
    is always incomplete and never reporter input. No cost is calculated here.
    """
    proof = _scope(attest_plan(config, data_root, plan, oracles, mini_identity=mini_adapter.identity()))
    destination = Path(output).absolute()
    if (destination.is_symlink() or any(p.is_symlink() or p.is_junction() for p in destination.parents)
            or destination.is_junction()):
        raise ValueError("Pilot output must not traverse links")
    destination = destination.resolve()
    if any(root == destination or root in destination.parents
           for root in (Path(data_root).resolve(), REPO_ROOT.resolve())):
        raise ValueError("Pilot output must be external to inputs and repository")
    destination.mkdir(exist_ok=True)
    lock = destination / ".pilot.lock"
    with lock.open("x", encoding="ascii") as stream:
        stream.write("explicit noncomparative pilot\n")
    try:
        binding = destination / "pilot-attestation.json"
        if binding.exists():
            if binding.read_bytes() != encoded(proof):
                raise ValueError("Pilot resume requires the identical attestation/runtime/settings")
        elif any(p != lock for p in destination.iterdir()):
            raise ValueError("Cannot attach pilot evidence to an existing output")
        else:
            _save(binding, proof)
        digest = hashlib.sha256(encoded(proof)).hexdigest()
        # The enclosing immutable attestation records the blocked canonical
        # config; do not ask the comparable runner to waive its unchanged gate.
        # This raw execution subtree is explicitly non-comparative evidence.
        try:
            run_plan(plan, destination / "raw-execution", oracles=oracles,
                     mini_adapter=mini_adapter, retry_incomplete=retry_incomplete)
        finally:
            _collect(destination / "raw-execution/results.jsonl", destination / "pilot-results.jsonl", digest)
        return _rows(destination / "pilot-results.jsonl")
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--canonical-config", type=Path, default=V4_CONFIG)
    parser.add_argument("--canonical-data-root", type=Path, required=True)
    parser.add_argument("--mini-settings", type=Path, required=True)
    parser.add_argument("--retry-incomplete", action="store_true")
    parser.add_argument("--accept-incomplete", action="store_true", help="Acknowledge no comparable result/cost")
    parser.add_argument("--execute", action="store_true", help="Explicit operator authorization for this pilot only")
    args = parser.parse_args(argv)
    if not args.execute or not args.accept_incomplete:
        parser.error("Pilot requires both --execute and --accept-incomplete; no work dispatched")
    try:
        from bench.mini import MiniAdapter, Settings
        adapter = MiniAdapter(Settings(**_json(args.mini_settings)))
        rows = run_pilot(args.plan, args.output, oracles=_json(args.oracles), config=args.canonical_config,
                         data_root=args.canonical_data_root, mini_adapter=adapter,
                         retry_incomplete=args.retry_incomplete)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Pilot stopped ({type(error).__name__}); preserve evidence; no comparable result.\n")
    print(f"{len(rows)} pilot attempt records; all INCOMPLETE, not pooled/report eligible; costs unverified.")
    return 1  # Never a comparative benchmark success.


if __name__ == "__main__":
    raise SystemExit(main())
