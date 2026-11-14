# Canonical Gemini team protocol — v1 is blocked

The single shared experiment definition is
[configs/gemini-benchmark-v1.json](configs/gemini-benchmark-v1.json), revision
`gemini-54-v1`. It freezes the 54 IDs in order, prompt/source hashes, dataset
commits, exact task/oracle JSON hashes, full-plan identity, profiles, grading,
evidence and pooling rules. **It does not authorize paid runs or comparability.**
The frozen runtime Git commit is `6bffe7c9745daca958bb3b410699cbee40ba0b25`;
82 runtime-file hashes allow checking that the config-publication commit changed
only review/validation material. Record the exact publication commit from
`git rev-parse HEAD` and the validator's `config_id` before any future request.
The config cannot embed its own containing Git commit without a circular hash.
Whitespace/CRLF in the JSON file does not change its canonical config ID; retain
raw file hashes too. Do not replace this snapshot in place to clear blockers:
publish a reviewed new revision after source/policy fixes, with regenerated plans.

## Prepare and validate, without execution

Verify the two exact dataset commits and `tasks.json`/`oracles.json` hashes listed
in the config. Use `scripts/build_bench_inputs.py` from the frozen source; its
QuixBugs subset is the fixed first-eligible-20 rule, not a newly drawn sample.
Preserve canonical source bytes (`core.autocrlf=false` for clones). The canonical
source digests ignore metadata/caches but do not normalize exercise bytes.
The builder's MANIFEST tree hashes include generated pytest bytecode and are
local evidence; they are not portable source identities. Keep the MANIFEST.

Set `$Python` to the project Windows Python 3.12 venv, `$Data` to the verified
assembled builder output, and `$Plans` to a new existing directory outside it.
Every output below must be new. From the repository root:

```powershell
& $Python -m bench.plan --set both --polyglot "$Data/polyglot" --quixbugs "$Data/quixbugs" --task-index "$Data/tasks.json" --runs 2 --output "$Plans/full.json" --dry-run
1..4 | ForEach-Object {
    & $Python -m bench.plan --set both --polyglot "$Data/polyglot" --quixbugs "$Data/quixbugs" --task-index "$Data/tasks.json" --runs 2 --shard "$_/4" --output "$Plans/shard-$_.json" --dry-run
    if ($LASTEXITCODE -ne 0) { throw "Shard planning failed" }
}
& $Python -m bench.canonical --data-root "$Data" --plans "$Plans/full.json" "$Plans/shard-1.json" "$Plans/shard-2.json" "$Plans/shard-3.json" "$Plans/shard-4.json"
& $Python -m bench.canonical --require-comparable
```

Static validation exits 0 when inputs agree, 2 on mismatch. The final command
exits **1** for this permanently non-comparable v1. No option bypasses its gate.
The validator only reads config/files/plans, never imports exercises, collects
tests, runs agents, reads credentials or opens SQLite. `bench.run` does **not**
load this canonical file or enforce its gate; do not invoke `--execute` under
this protocol. An exit 0 from static validation is not permission or readiness.

## Assignment and required policy

| Shard | Sorted full-plan positions | Tasks | Crocodile / mini / twin | Runs |
|---|---|---:|---|---:|
| 1/4 | 1–14 | 14 | 28 / 28 / 14 | 70 |
| 2/4 | 15–28 | 14 | 28 / 28 / 14 | 70 |
| 3/4 | 29–41 | 13 | 26 / 26 / 13 | 65 |
| 4/4 | 42–54 | 13 | 26 / 26 / 13 | 65 |

Run order per task is Crocodile 1, Crocodile 2, mini 1, mini 2, twin 1. No `--limit`,
variant batching or omitted mini slots in a pooled experiment. Native Crocodile
uses `flags=None`; the all-off twin uses `set()` and disables its cache lever.
Mini is 2.4.6 in Ubuntu WSL2, with its pinned default templates, independent venv
and `set_cache_control: default_end`. Both wire model IDs are
`gemini/gemini-3.5-flash-lite`; mini's LiteLLM argument additionally has `openai/`.
Native cheap/strong chains are single-model Flash-Lite. Fallbacks and measured
Flash escalation are disabled. Bifrost 2.5.1 is required at 127.0.0.1:18080,
mini base `/v1`, same logical `vk-bench` / `bench`, $15 shared cap. Store only
credential variable names. Thinking is provider-default, sampling overrides
omitted, semantic cache off. Actual binding/defaults/cache behavior need evidence.
Native requests `max_tokens=4096`; mini does not set that parameter. The provider's
effective mini output cap is unverified. This difference is frozen as unresolved,
not silently described as output-budget parity.

The policy is 30 steps and 600 seconds per agent, with independent grading timeout
180 seconds. Native's clock starts after preparation and is cooperative; mini's
worker watchdog cannot contain all descendants. Neither is a verified hard cap.
Grade in a fresh final-tree copy, restore original tests/configs/helpers/data plus
indexed `test_paths`, remove agent-added protected files and caches, then run
`python -m pytest -q`. Retain test-edit flags and claimed versus graded solved.

## Results, costs and accepting earlier shards

Keep immutable plan/oracle/config copies, actual Git/environment/dependency
snapshots, all events/results and attempts, session bindings, sanitized receipts,
original/final trees, commands, grading output and UTC windows. The logical run
ID is stable; attempts/sessions are unique. A missing mini adapter yields
`blocked` / `MissingMiniRunner` at each mini slot. Setup/auth/quota failures are
`incomplete` with specific reasons, not measured task failures. Completed graded
failures stay failures; do not rerun them. Explicit incomplete retries retain all
prior attempts and costs. Never repair locks or truncate logs automatically.

Use all Bifrost requests and the pinned price snapshot for costs, including
unsolved/failed/retried calls. Receipt cost is only a >1% cross-check. Save the
runtime Git blob `prices.yaml` **verbatim as bytes** for canonical native prices:
exporter/combiner require the same raw hash; a CRLF working copy has a different
hash. This freeze does not verify the rates are current. Require exact bench
VK/session IDs, independent complete request inventory, terminal/flush evidence,
actual model/status and explicit disjoint token categories. Missing usage is
incomplete, never zero. Preserve exporter bundles and incomplete diagnostics;
never modify a gateway DB, infer a TTL, discard retries or use a time window as
exact attribution. Qualify IDs by logical gateway; reject duplicate origins/IDs.

**Accept no earlier/current shard into a comparable pool under v1.** Quarantine
it. For a later unblocked revision, accept an earlier shard only if contemporaneous
artifacts prove every frozen input/code/environment/policy and all assigned
positions/runs, exact prompt/original source bytes, original-test grades, complete
request/cost evidence and no attribution overlap. A matching model name, edited
receipt, passing grade or retroactively supplied `verified: true` is insufficient.
No Haiku cohort, Flash escalation, missing mini slots, quota gaps or cheap-retry
selection can be relabeled as this experiment. The union must be 54 tasks/270
eligible runs; incomplete shards remain explicitly incomplete. Use the strict
offline reporter only after independent evidence joins, not raw attempt JSONL.

## Unresolved work before a new comparable revision

`6167883` is on person-2, **not main**; `5f09a22` is its fail-closed correction.
Neither was merged/cherry-picked. Coordinate review and integration through main;
the default runner here still lacks initialized integrity/confidentiality state.
Native bench VK/profile/sampling binding, hard-stop containment, cache/retry and
environment/price review, live gateway/header/schema/complete cost evidence and
config-ID attestation remain unresolved. All 54 real prompts contain CRLF while
mini's `read_text()` normalizes LF; exact task-text parity also needs a reviewed
Person 4 fix. See config `readiness.unresolved` for owners. No security assertion
or comparable benchmark claim is enabled by these static/synthetic checks.
