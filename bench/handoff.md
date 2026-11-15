# Team benchmark handoff — no live runs authorized here

Prepared 2026-11-14 from `person-4` runtime commit
`1a374a5b1dd1772f916d799d199778ed5613938b`. **Real execution is blocked.**
The actual 34 Polyglot + 20 QuixBugs sources, exact task text and oracle mapping
are absent; see the precise [dataset input checklist](dataset-inputs.md).
No real task index, benchmark result or cost claim accompanies this handoff.

Follow-up: dataset inputs have since been verified outside the checkout. The
current [Gemini/18080 policy and blocked readiness](gemini-readiness.md) supersede
the initial installation/model observations below. Regenerate manifests under
that policy; retain this handoff's fixed shard assignments and 2+2+1 ordering.

## Fixed protocol and ownership

Sort the full 54-task index lexically by `dataset/id`, then take these contiguous
positions **before** expanding variants/repeats:

| Team shard | Full-plan positions | Tasks | Crocodile / mini / twin | Total runs |
|---|---|---:|---|---:|
| 1/4 (Person 4's shard) | 1–14 | 14 | 28 / 28 / 14 | 70 |
| 2/4 | 15–28 | 14 | 28 / 28 / 14 | 70 |
| 3/4 | 29–41 | 13 | 26 / 26 / 13 | 65 |
| 4/4 | 42–54 | 13 | 26 / 26 / 13 | 65 |

Within each task the order is **Crocodile 1, Crocodile 2, mini-swe-agent 1,
mini-swe-agent 2, all-off twin 1**. One sequential runner per shard; four machines
may run their distinct shards concurrently only after coordinated authorization.
Use two independent runs, not model seeds. Never reorder to batch variants.
All manifests must share `full_plan.id`, dataset revisions and input hashes;
absolute dataset paths and shard-plan byte hashes may differ by machine.

## Commands from the repository root (PowerShell)

First supply actual reviewed paths in `$PolyglotRoot`, `$QuixBugsRoot`,
`$TaskIndex`, `$FullOracles`, and `$MiniSettings`. The latter is the key-free WSL
settings file described in [mini.md](mini.md), not a credentials file. Set
`$PlanDirectory` and `$RunDirectory` to existing writable parent directories
outside the datasets. These variables deliberately have no invented dataset
defaults. The output filenames below are new artifacts, not purported inputs.

These planning commands are safe and never execute exercises, tests or agents:

```powershell
python -m bench.plan --set both --polyglot "$PolyglotRoot" --quixbugs "$QuixBugsRoot" --task-index "$TaskIndex" --runs 2 --shard 1/4 --output "$PlanDirectory/shard-1.json" --dry-run
python -m bench.plan --set both --polyglot "$PolyglotRoot" --quixbugs "$QuixBugsRoot" --task-index "$TaskIndex" --runs 2 --shard 2/4 --output "$PlanDirectory/shard-2.json" --dry-run
python -m bench.plan --set both --polyglot "$PolyglotRoot" --quixbugs "$QuixBugsRoot" --task-index "$TaskIndex" --runs 2 --shard 3/4 --output "$PlanDirectory/shard-3.json" --dry-run
python -m bench.plan --set both --polyglot "$PolyglotRoot" --quixbugs "$QuixBugsRoot" --task-index "$TaskIndex" --runs 2 --shard 4/4 --output "$PlanDirectory/shard-4.json" --dry-run
```

No `--limit` for official shards. When used for development, it selects the first
N tasks **within an already assigned shard**; the remaining slice is incomplete.
Sharding rejects anything other than exactly 34 + 20 validated tasks. Manifest
outputs must not exist; all indexed tasks are checked even outside your slice.

Filter the reviewed full oracle map without guessing targets. This snippet only
reads metadata and writes four new JSON artifacts. It validates the common
runner contract, including rejecting unsupported pytest arguments. It does not
collect or execute tests, validate installed dependencies, or contact services.

```powershell
@'
import json, sys
from pathlib import Path
from bench.plan import _object
from bench.run import _validate
full_map, directory = Path(sys.argv[1]), Path(sys.argv[2])
load = lambda path: json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object)
oracles = load(full_map)
plans = [load(directory / f"shard-{n}.json") for n in range(1, 5)]
assert len({plan["full_plan"]["id"] for plan in plans}) == 1, "Different full plans"
assert isinstance(oracles, dict) and set(oracles) == set(plans[0]["full_plan"]["task_ids"]), "Oracle coverage mismatch"
subsets = [{task["task_id"]: oracles[task["task_id"]] for task in plan["tasks"]} for plan in plans]
for plan, subset in zip(plans, subsets):
    _validate(plan, subset)
for number, subset in enumerate(subsets, 1):
    with (directory / f"oracles-{number}.json").open("x", encoding="utf-8") as stream:
        json.dump(subset, stream, indent=2, sort_keys=True)
        stream.write("\n")
'@ | python - "$FullOracles" "$PlanDirectory"
```

**Future authorized live commands — do not run until blockers below are resolved.**
Each machine runs only its assigned line, with its own local roots/settings and
output directory. Include `--mini-settings` to keep all five slots interleaved:

```powershell
python -m bench.run --plan "$PlanDirectory/shard-1.json" --oracles "$PlanDirectory/oracles-1.json" --mini-settings "$MiniSettings" --output "$RunDirectory/shard-1" --execute
python -m bench.run --plan "$PlanDirectory/shard-2.json" --oracles "$PlanDirectory/oracles-2.json" --mini-settings "$MiniSettings" --output "$RunDirectory/shard-2" --execute
python -m bench.run --plan "$PlanDirectory/shard-3.json" --oracles "$PlanDirectory/oracles-3.json" --mini-settings "$MiniSettings" --output "$RunDirectory/shard-3" --execute
python -m bench.run --plan "$PlanDirectory/shard-4.json" --oracles "$PlanDirectory/oracles-4.json" --mini-settings "$MiniSettings" --output "$RunDirectory/shard-4" --execute
```

`bench.run` has **no `--dry-run`**. Omitting `--execute` exits 2 before loading
services/settings/oracles; this guard was checked, not a live execution. All four
planner lines and the oracle-filter snippet were exercised with temporary,
clearly synthetic 34/20 trees. See [validation evidence](handoff-validation.json).
Real dataset validation remains blocked. `bench.mini --help` documents a separate
mini-only command; it is not a substitute for the full interleaved protocol.

Resume using the identical live command and output directory. Completed runs,
including graded failures, are skipped. Incomplete/blocked/interrupted attempts
require operator review and explicit `--retry-incomplete`; keep every earlier
attempt and its cost. Never remove locks or truncate logs to force a restart.

## Readiness and remaining live blockers

| Area | Verified evidence / remaining gap |
|---|---|
| Mini adapter | Implemented separately in WSL; synthetic fake-process validation only. Pins mini 2.4.6 and upstream templates; no local installed mini/venv path has been supplied or checked. |
| Local WSL | Read-only metadata queries succeeded: default `Ubuntu`, WSL version 2; Ubuntu was stopped. `docker-desktop` also listed as WSL2. No Linux worker or distribution was started by this handoff. |
| Bifrost connectivity | Not contacted. Mirrored WSL loopback reachability, live gateway/version and shared bench VK/cap remain unverified. No credential was inspected. |
| Session header | End-to-end mini/LiteLLM/Bifrost forwarding unverified. Default `session_header_verified: false` records only a bounded time window and null session ID; cost remains incomplete. A window is not exact attribution. |
| Independent grading | Implemented and synthetically tested: fresh final-tree copy, original tests/config/helpers restored, pytest timeout 180 s, claimed/graded outcomes separate. Real oracles/dependencies missing. |
| Fairness | Same planned prompt/model/30 steps/600 s policy, but actual served model, adaptive/medium, caching, no sampling/fallback/escalation and mini's 30 s command timeout still need coordinated review with agent/gateway owners. |
| Hard caps | Native 30 steps enforced; native 600 s cooperative only. Mini 30 model steps and 600 s worker/group watchdog implemented, but escaped command descendants are not fully contained. Neither claims a hard wall-clock guarantee. |
| Cost/report | Read-only exporter supports reviewed simple/cache-read successes with explicit zero writes and flat prices. Current Haiku tiering, positive cache writes/TTL, retries/fallbacks and complete request inventories remain blockers; schema sample is not live DB verification. Receipt cost is not authoritative. |

The architecture's `bitcount --timeout=5` rule also needs a command adapter if that
program is selected. No budget upper-bound calculation or VK-cap CI enforcement
is provided by `bench.plan`. Resolve these gaps before the three-task live smoke,
and obtain separate authorization for any model calls. This handoff is not a
declaration that the benchmark is ready to launch.

## Artifacts every shard must hand back

- Immutable `plan.json`, `oracles.json`, `mini-settings.json` (key-free), full-plan
  identity, source revisions/assembly hashes, config/code version and price snapshot.
- Append-only `events.jsonl` and `results.jsonl`, retaining all attempts/retries,
  raw agent session IDs, attempt/run/task/shard IDs, UTC windows, model/usage/cap
  evidence and incomplete reasons. Do not relabel setup failures as task failures.
- Each `attempts/UUID/` original/final tree, sanitized agent receipt/security events,
  mini command/config/version evidence where available, and grading workspace,
  `result.json`, stdout/stderr and test-edit flag. Review artifacts for secrets
  before sharing; do not upload raw model payloads, credentials or gateway config.
- Independently reviewed request inventories, VK/origin binding, session-close/
  flush evidence and authorized quiescent Bifrost snapshot reference/hash. Transfer
  sanitized exports, not teammates' live databases. Never modify the source DB.
- Complete exporter bundles: `evidence.jsonl`, normalized `prices.yaml`,
  `costs.jsonl`, `diagnostics.json`, `manifest.json`; preserve incomplete diagnostics
  too. Flag receipt differences above 1%. Combine by logical gateway-qualified
  IDs using [bifrost-export.md](bifrost-export.md), rejecting overlap.

Runner attempt JSONL is not directly the strict [offline report format](report-format.md).
Join independent grading with complete log-derived costs; include failed runs and
all retries. Mini's first-attempt report join exists; retry aggregation and a full
native/cross-shard report assembly still need integration. Publish no report until
the complete 270-run grid and attribution/fairness requirements are satisfied.
