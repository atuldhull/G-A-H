# Gemini 54 v2 release — shard launch blocked

This release freezes [configs/gemini-benchmark-v2.json](configs/gemini-benchmark-v2.json).
V1 remains historical and immutable. V2 uses main's LF-only builder, the same
pinned 34 Polyglot / 20 QuixBugs tasks, and the current fail-closed runner with
exact prompt-byte checks and pre-request configuration attestation. The JSON
contains the complete v1-to-v2 change record, runtime file hashes, dataset commits,
prompt/source hashes, task order, full-plan ID, and accepted limitations.

**Do not start shards.** Atul's `3a111322…` kheapsort attempt reported 26 steps,
`Submitted`, return code 0, then a host `ValueError` in `mini-setup-or-grading`.
Its sanitized attempt row, traceback, and grading result/stdout/stderr have not
been supplied. Cause and ownership within that phase are unresolved. Neither a
grading-rule change, guessed regression test, nor a claim of measured task failure
is justified. Retain it as incomplete. A demonstrated Person 4 fix must get a
synthetic regression test; alternatively, evidence must establish a setup-only
limitation. Review release authorization afterwards; this immutable blocked
snapshot cannot be unlocked by editing booleans or dropping its canonical flags.

## Policy and limitations

- Bifrost **2.5.1**, `http://127.0.0.1:18080` (mini `/v1`), logical bench VK
  `vk-bench` / `bench`; no credential values in artifacts. Secure provisioning is
  per machine. Crocodile's current egress still selects the `public` key alias;
  prove that its actual requests use the intended bench identity. The profile
  JSON alone is not loaded or bound automatically by the runner.
- Both wire models: `gemini/gemini-3.5-flash-lite`; mini LiteLLM argument:
  `openai/gemini/gemini-3.5-flash-lite`. Cheap and strong chains each contain only
  Flash Lite. No measured-model fallback or Flash escalation. Internal native rung
  changes remain possible but must not change the billed model.
- Provider-default thinking. Native requests temperature 0.0, or 0.7 after a
  rung switch/rewind; mini omits sampling overrides. Native output cap is 4096;
  mini omits the output-cap parameter. Native uses its cache flag, mini
  `default_end`, and the all-off twin disables its cache lever; semantic cache off.
- 30 steps, 600 seconds. Native deadline checks are cooperative. Mini has a
  worker/process-group watchdog, 650-second host wait plus cancellation, with
  escaped-descendant containment unverified. These are not proven hard stops.
- **Atul accepts hard-stop containment, mini output cap, cache parity, and the
  sampling difference as known limitations, not comparability gates.** They stay
  visible in every pooled interpretation; this release adds no stronger claim.
- Gateway connectivity, mini header forwarding and log-row evidence are
  **reported verified on Atul's machine**, not independently verified here.
  No sample artifact, local gateway, credential provisioning, authorized database
  path or flush procedure was supplied for independent local verification.

## Rebuild and prepare (no agents)

Verified locally on 2026-11-15: main `b92ae4d` was integrated without conflicts
by `31f9cef9e463768e2a5c349988aed564cb242dbd`; the frozen runtime checkpoint is
`67fa99fc8b4a112221e3606c87a5d16413675158` (86 LF-normalized runtime file hashes).
The containing publication commit is recorded by Git/each run attestation,
avoiding a self-referential config hash. Frozen identities:

```text
tasks.json     3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18
oracles.json   38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537
v2 config ID   700089ad8472546868ea39edee3f8e43b5b9ff87204cfaabf9268a0d616a0494
full-plan ID   da56c686fe979620275686e46042696330d6d91a37c20c9409063111561188f6
```

Both dataset checkouts were clean at the exact pinned commits with
`core.autocrlf=false`. All 54 portable source digests equal v1; the LF task-text
digests and full-plan ID differ. All five bundle manifests matched independent
`bench.plan --dry-run` CLI output byte-for-byte. Plan file hashes themselves are
machine-path-dependent; the config/full-plan IDs and portable task evidence are
the cross-machine identities. `release-preparation.json` retains the local plan,
oracle subset, settings and MANIFEST hashes.

Use the exact dataset revisions in the config, cloned with `core.autocrlf=false`.
Do not run the builder as an import: it executes its argument-handling body.
It runs buggy QuixBugs pytest selection checks in copies, never agents or models.
Use a new empty output outside the repository. This machine's verified inputs:

```powershell
$Python = 'C:\Users\gunda\venvs\crocodile\Scripts\python.exe'
$Base = 'C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132'
$Data = "$Base\generated-lf-v2-20261115-31f9cef"
$Bundle = "$Base\release-gemini-54-v2-20261115"
$Config = (Resolve-Path 'bench/configs/gemini-benchmark-v2.json').Path
$MiniSettings = (Resolve-Path 'bench/configs/mini-settings.ubuntu.json').Path
# Already rebuilt once; to rebuild, replace $Data with a NEW empty output:
# & $Python scripts/build_bench_inputs.py "$Base\polyglot-benchmark" "$Base\QuixBugs" $Data $Python
& $Python -m bench.release --config $Config --data-root $Data --output $Bundle --mini-settings $MiniSettings
if ($LASTEXITCODE -ne 0) { throw 'Release preparation failed' }
& $Python -m bench.canonical --config $Config --data-root $Data --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $Data --require-comparable
```

The last command deliberately exits **1**: unresolved launch blockers. Static
validation exits **0** when all frozen inputs/runtime and plans match. Mismatch
exits **2**; stop. `bench.release` checks the builder MANIFEST's 54 local tree
hashes, the exact task/oracle JSON hashes, every original oracle and test-data
path, and portable source/prompt hashes. It writes the full plan, four shard
plans, five exact oracle subsets, key-free mini settings, and
`release-preparation.json` (hashes, gate result and command arrays). Existing
outputs are rejected. Preserve the builder's MANIFEST: its bytecode-inclusive
tree hashes are local evidence, not portable source identities.

The mini settings copy identifies Ubuntu and
`/home/gunda/venvs/crocodile-mini/bin/python`, pinned mini **2.4.6**. This local
template truthfully leaves session-header verification false. Each teammate
must supply their actual reviewed interpreter/distro and a key-free settings
file with their own session evidence. Atul's evidence must not automatically
set this machine's header flag. Do not edit a frozen bundle during resume.

To verify the underlying plan CLI independently, use a new existing `$Check`
directory outside the dataset/repository:

```powershell
& $Python -m bench.plan --set both --polyglot "$Data/polyglot" --quixbugs "$Data/quixbugs" --task-index "$Data/tasks.json" --runs 2 --output "$Check/full.json" --dry-run
1..4 | ForEach-Object {
    & $Python -m bench.plan --set both --polyglot "$Data/polyglot" --quixbugs "$Data/quixbugs" --task-index "$Data/tasks.json" --runs 2 --shard "$_/4" --output "$Check/shard-$_.json" --dry-run
    if ($LASTEXITCODE -ne 0) { throw 'Shard dry run failed' }
}
```

## Assignment and eventual commands — blocked, not executed

| Shard | Full-plan positions | Tasks | Slots |
|---|---|---:|---:|
| 1/4 | 1–14 | 14 | 70 |
| 2/4 | 15–28 | 14 | 70 |
| 3/4 | 29–41 | 13 | 65 |
| 4/4 | 42–54 | 13 | 65 |

Task IDs and order are unchanged; LF prompt bytes give a new full-plan identity.
Each task stays together in this order: **Crocodile 1, Crocodile 2, mini 1, mini 2,
all-off twin 1**. No `--limit` or variant batching in comparable full shards.
`--limit` applies after the shard and creates development-only partial coverage.
All 270 slots must remain identifiable; no native substitution for mini.

After the mini diagnosis and a reviewed authorization revision, these are the
current CLI shapes. **Do not execute them under this blocked release.** The
command arrays in the prepared bundle retain exact absolute local paths. Each
operator first binds the key-free native chain/endpoint environment below and
securely verifies actual bench VK use; never copy or print a VK value:

```powershell
$env:CROCODILE_CHAIN_CHEAP = 'gemini/gemini-3.5-flash-lite'
$env:CROCODILE_CHAIN_STRONG = 'gemini/gemini-3.5-flash-lite'
$env:CROCODILE_BIFROST_URL = 'http://127.0.0.1:18080'
$MiniSettings = "$Bundle/mini-settings.json"
# BLOCKED — command reference only, NOT a launch instruction:
& $Python -m bench.run --plan "$Bundle/shard-1.json" --oracles "$Bundle/shard-1-oracles.json" --output "$Bundle/shard-1-results" --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $Data --execute
& $Python -m bench.run --plan "$Bundle/shard-2.json" --oracles "$Bundle/shard-2-oracles.json" --output "$Bundle/shard-2-results" --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $Data --execute
& $Python -m bench.run --plan "$Bundle/shard-3.json" --oracles "$Bundle/shard-3-oracles.json" --output "$Bundle/shard-3-results" --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $Data --execute
& $Python -m bench.run --plan "$Bundle/shard-4.json" --oracles "$Bundle/shard-4-oracles.json" --output "$Bundle/shard-4-results" --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $Data --execute
```

## Prioritized acceptance checks and evidence

| Priority | Blocker / owner | Smallest observable acceptance check |
|---|---|---|
| 1 | Mini attempt `3a111322…`; Person 4, artifacts held by Atul | Sanitized row, full traceback, grading result/stdout/stderr identify the actual raise site; reproduce/fix with synthetic regression, or prove setup-only classification. No grading policy weakening. |
| 2 | Native bench binding; Person 1 `crocodile/adapters.py`, Part 2 gateway provisioning | With approved key-free chain/endpoint settings, actual native request evidence identifies the same bench VK and Flash Lite with no measured fallback/escalation. Current alias is public; profile JSON is not automatic binding. |
| 3 | Per-machine readiness and complete costs; shard operators / Person 2 / Person 4 exporter | Supply authorized local gateway/header/log evidence, closed/flushed request inventory, reviewed version/usage conventions and price snapshot. Successful single-row evidence alone does not prove complete session costs. |

Keep publication Git SHA/config ID, clean runtime SHA/file hashes, environment
versions/dependency snapshots, plan/oracle/config/settings copies, all
`events.jsonl`/`results.jsonl` attempts and prior-attempt IDs, raw unique session
IDs/request IDs qualified by gateway origin, UTC windows, receipts, original/final
trees, independent grading artifacts, and read-only exporter bundles. Restore
original tests/configs/helpers/indexed data in a fresh grading copy, then run
`python -m pytest -q` with 180-second timeout. Claimed solved stays separate from
independently graded solved. Setup/auth/quota errors and host grading exceptions
are **incomplete**, never measured task failures. Completed independent test
failures are measured zeros only when execution and cost evidence are eligible.
Missing mini adapter slots remain blocked. Resume skips completed run IDs;
retry incomplete only explicitly, retaining all previous evidence and costs.

Bifrost requests × pinned `prices.yaml` remain authoritative; include unsolved,
failed and retry costs. Receipts only cross-check (>1% discrepancy flagged).
Current exporter supports reviewed successful non-retry requests, explicit
complete usage, zero writes, cache reads, and an unbounded price tier. Writes/TTL,
retry/fallback or unknown statuses, missing/ambiguous usage/inventory and unknown
or tiered rates remain incomplete. Atul's reported live row evidence does not
expand exporter support or independently establish its physical schema here.

Earlier shards are quarantined unless contemporaneous artifacts prove identical
v2 input/prompt/source bytes, runtime hashes, models and policies (including the
explicitly accepted limitations), all assigned slots/attempts, restored-test
grades and complete costs with no duplicate origins/session/request IDs. V1
CRLF prompts cannot be relabeled v2. Do not select the cheapest successful retry
or convert setup gaps into task failures. Pooling still requires the complete
54-task / 270-slot union and reviewed cost joins, not raw attempt JSONL.
