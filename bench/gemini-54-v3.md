# Gemini 54 v3 — immutable preparation, live launch blocked

[configs/gemini-benchmark-v3.json](configs/gemini-benchmark-v3.json) freezes main
`bdcce1fe3ae44a8c892dcd1d74ee8d3c82f41c94`, integrated without conflicts by
`5fba38daf7d0bc2cf25646588dcc991944f42f28`, plus Person 4's runtime checkpoint
`40b84833217bbe77490689daf41d743fc1c1eaa0` (87 LF-normalized source pins).
The config publication commit is recorded by Git and each attestation, avoiding
self-referential hashes. V1 and V2 remain historical; neither file was changed.

```text
v3 config ID    c0d48d86fe8169947e9997dd5fa33f642fa6d53afbc2f54756ce6ea1dd049ee1
v3 raw LF SHA   b3320171326ce1712add548bc8148d838762f219090765a9bf8946ed2a1326ba
tasks.json      3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18
oracles.json    38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537
full-plan ID    da56c686fe979620275686e46042696330d6d91a37c20c9409063111561188f6
historical v2   700089ad8472546868ea39edee3f8e43b5b9ff87204cfaabf9268a0d616a0494
v2 raw LF SHA   4cdf9b9331d84981c624ecdf0ac3a8b9114f50f9374ad1ae89ad4021080e48f6
```

Dataset commits remain Polyglot `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`
and QuixBugs `4257f44b0ff1181dedaedee6a447e133219fcebf`. The existing verified
LF inputs were revalidated: both exact JSON hashes, every original oracle,
54 prompt/source digests and the builder MANIFEST. No builder, exercise, agent
or paid request was executed for this preparation. Manifests contain local
absolute paths; their byte hashes differ across machines. Portable task/config
and full-plan identities must agree.

## Changes from v2

- Main includes Atul's RT-2 fix `2f8b048`. The real Agent, UI bridge and renderer
  regression requires zero pytest children, zero test runs, unsolved status
  `UNVERIFIED (tests not approved)` and `TESTS NOT RUN (no consent)`.
- Mini includes `7c3a643` and `b79d9fd`: sanitized stage/message/relative path and
  bench frames, a bounded metadata-only inventory before workspace cleanup, and
  canonical Windows temporary-parent paths. No file contents or link targets
  enter new diagnostics; strict link/junction/special-file rejection remains.
- Historical-release tests verify V2's original config/file hashes without
  requiring current code to equal an old runtime. Strict execution validation
  continues to reject drift. V3 also pins `bench/failure_evidence.py`.
- `bench.release --include-smoke` emits the same first-three-of-shard-1 smoke
  alongside the full plan and all four shards, with original oracle subsets.
- [Supplied evidence review](mini-3a111322-diagnosis.md) replaces the historical
  claim that no artifacts were supplied. Final-copy failure is localized against
  inspected control flow; the exact original file/raise remains unknown. There
  is no traceback or final workspace. Mini's session/header is null. The native
  summary supports VK name/requested model only; it is not complete log evidence.
  The two reported 429s are infrastructure-incomplete, not measured task losses.

Task order, source/prompt bytes, shard ranges, run IDs, wire models, independent
grading and all four accepted limitations are unchanged. Earlier v1/v2 runs are
not automatically v3-compatible: retain contemporaneous runtime/config/inputs,
all attempts and complete grading/cost evidence; require explicit compatibility
review, never relabel a cohort or select only successful retries.

## Policy and accepted limitations

Bifrost 2.5.1 at `http://127.0.0.1:18080`, mini `/v1`; logical VK identity
`vk-bench` / `bench`, credential supplied securely via environment. Native wire
model is `gemini/gemini-3.5-flash-lite`; mini's LiteLLM argument is
`openai/gemini/gemini-3.5-flash-lite`. Both native rung chains are single-model;
no measured fallback or Flash escalation. Thinking is provider-default.

Atul accepts these as limitations, **not comparability gates**: hard-stop/full
descendant containment, mini's omitted output cap versus native 4096, cache
semantics/parity (including all-off's disabled cache lever), and native sampling
0.0/0.7 versus mini's omitted sampling override. No matched sampling, cache parity
or hard-stop claim is made. Step policy remains 30; wall policy remains 600s with
native cooperative checks and mini's worker/group watchdog. Grading separately
uses a fresh copy, restores original protected tests/config/helpers/data, runs
`python -m pytest -q` with 180s timeout, and records independent outcomes.

## Current gates

Strict static/input/manifest validation must exit **0** with no runtime drift.
`--require-comparable` exits **1**: `cross_shard_comparable=false` and
`paid_runs_authorized=false`. Contract/hash/runtime errors exit **2**. Auditing
cannot waive drift or unlock this immutable blocked release.

| Priority / gate | Owner | Smallest observable acceptance evidence |
|---|---|---|
| P0: `mini-attempt-3a111322` | Person 4 / Atul / reviewer | Evidence-backed disposition of the original final-copy exception, or explicitly reviewed setup-only classification. Safe future diagnostics/regressions do not establish the original cause. Never count it as a task failure. |
| P0: `native-policy-binding` | Person 1 adapters, Person 2 gateway, operators | Sanitized native request/log correlation: same stable bench VK identity, exact Flash-Lite wire/billed model, endpoint, no fallback, effective sampling policy. VK name/requested model alone are insufficient. |
| P0: `per-machine-execution-and-cost-evidence` | Operators / Person 2 / Person 4 exporter | Reviewed actual environment/mini settings and session-header request join; authorized physical schema check and closed/flushed complete request inventory, consistent explicit usage and reviewed price hash/rates. Unsupported retries/cache writes/missing fields stay incomplete. |

Gateway/header/log forwarding is reported verified on Atul's machine, not
independently verified here or on the other shard machines. The supplied native
summary has no request IDs, stable VK ID, served models, cache categories or
fallback/sampling fields. It does not clear these gates. New paid authorization
and a reviewed readiness revision are required before a live smoke; official
shards must not start. Setup/auth/quota/diagnostic failures preserve their planned
slots as incomplete, never zero-score task losses or Crocodile substitutions.

## Prepared artifacts and reproducible commands

Run from the repository root. The commands below use actual CLI options; only
planning, validation and attestations are executed. Choose fresh output names
when reproducing; preparation and attestation refuse overwrites.

```powershell
$Python = 'C:\Users\gunda\venvs\crocodile\Scripts\python.exe'
$Base = 'C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132'
$Data = "$Base\generated-lf-v2-20261115-31f9cef"
$Bundle = "$Base\release-gemini-54-v3-20261115"
$Config = (Resolve-Path 'bench/configs/gemini-benchmark-v3.json').Path
$MiniSettings = (Resolve-Path 'bench/configs/mini-settings.ubuntu.json').Path
& $Python -m bench.release --config $Config --data-root $Data --output $Bundle --mini-settings $MiniSettings --include-smoke
& $Python -m bench.canonical --config $Config --data-root $Data --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $Data --require-comparable
# Expected: exit 1 on the final command, not permission to execute.

# After publication, from a clean checkout; each output must be new:
foreach ($Label in @('full', 'shard-1', 'shard-2', 'shard-3', 'shard-4', 'smoke')) {
    & $Python -m bench.attest --config $Config --data-root $Data --plan "$Bundle/$Label.json" --oracles "$Bundle/$Label-oracles.json" --mini-settings "$Bundle/mini-settings.json" --output "$Bundle/$Label-attestation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Attestation creation failed' }
}
```

The full plan has **54 tasks / 270 slots**, contiguous shards **14/14/13/13**
tasks and **70/70/65/65** slots. Every task retains Crocodile 1, Crocodile 2,
mini 1, mini 2, all-off twin 1. The smoke has **3 tasks / 15 slots (6/6/3)**:
`polyglot/affine-cipher`, `polyglot/beer-song`, `polyglot/book-store`, positions
1–3 of shard 1/4. It is development-only and has no QuixBugs coverage.

Full/smoke plans are `$Bundle/full.json` and `$Bundle/smoke.json`; their oracle
subsets are `$Bundle/full-oracles.json` and `$Bundle/smoke-oracles.json`.
`release-preparation.json` records exact byte hashes and not-executed command
arrays. `full-attestation.json`, `smoke-attestation.json` and each shard's
attestation bind the publication/config/runtime/input/plan/oracle/mini identities
and clean Git state. Both execution authorization and pooled eligibility remain
false. The key-free settings copy deliberately leaves header verification false.

Independent dry runs use `bench.plan --set both --runs 2 --task-index
"$Data/tasks.json" --polyglot "$Data/polyglot" --quixbugs "$Data/quixbugs"
--output NEW_PATH --dry-run`; smoke adds `--shard 1/4 --limit 3`.
The eventual runner shape, **not executed and blocked under this config**, is:

```powershell
& $Python -m bench.run --plan "$Bundle/smoke.json" --oracles "$Bundle/smoke-oracles.json" --mini-settings "$Bundle/mini-settings.json" --canonical-config $Config --canonical-data-root $Data --output "$Bundle/smoke-results" --execute
```

Any future authorized execution must retain canonical config/attestation,
results/events JSONL (including incomplete/prior attempts), original/final and
grading evidence, sanitized receipts/commands/config/session IDs, and read-only
cost exports with the canonical native prices snapshot. Receipt cost is a
cross-check, not authority. Evidence completeness and original-test grading
remain mandatory even where an accepted limitation is not a launch gate.
