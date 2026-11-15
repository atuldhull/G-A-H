# Gemini 54 v5 — constrained resolution, historical pilot retained

Published 2026-11-15 from runtime checkpoint
`e442377be017edf58638f24f2c4da2a1deac8556`. The immutable
[v5 config](configs/gemini-benchmark-v5.json) pins 88 runtime files, corrected
prices, reviewed evidence and the unchanged LF inputs. The config-containing
publication commit is recorded by Git and each clean machine attestation.

```text
v5 config ID   93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83
v5 raw LF SHA  0d338d3913ac855993aecf85f6127c2be36302789500dd13f77a0d0fcd808b4c
prices.yaml    8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e
tasks.json     3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18
oracles.json   38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537
full-plan ID   da56c686fe979620275686e46042696330d6d91a37c20c9409063111561188f6
```

Dataset commits remain Polyglot `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`
and QuixBugs `4257f44b0ff1181dedaedee6a447e133219fcebf`. V4's config bytes,
fingerprint, prior evidence, attestations and pilot rows are unchanged. V4 now
has expected historical exporter/validator drift; it is not repinned to v5.

## Audited source evidence

All sources were parsed as untrusted JSON/JSONL/ZIP data. All **641** ZIP paths
were checked for traversal, duplicate/case-colliding paths, drive/absolute paths,
encryption and special files before selected metadata was read. No source code,
bytecode, task text or command from the ZIP was executed or extracted. Raw
attachments stay outside Git and have not been rewritten.

| Source | SHA-256 of actual bytes |
|---|---|
| `croc-native-binding-20261115-190653.json` | `a5ee19904f8091d49abbbac952a47c3516e38dc917bcfab7c3f02fc628ef734d` |
| `croc-native-requests-20261115-190653.jsonl` | `33717d459a9fc23fbed643064e7cebbe6e51125868af9ec3169d279ffe4c730c` |
| `pilot-v4-20261115-191021.zip` | `32caad72ba81d63ec7b4afe568e6c124a9e1a8bfeaf99a699a58cb7c4b02ae6e` |

[The sanitized review](evidence/croc-native-pilot-v4-review.json) records **four
actual Crocodile calls**, two sessions, joined by session/timestamp/request and
provider response IDs across the wire, journal and Bifrost rows. Agent run IDs,
usage totals, two supplemental grade artifacts and original oracle bytes match
the archive. The native core hash and price pin match the recorded clean
`89bdfed` runtime. All four requests have the intended Flash-Lite requested,
resolved and log model, bench-VK equality assertions, standard/default tier and
four price/component reconciliations within the existing rules. No dollar total
or complete-cost export is published.

This is Atul's sanitized remote evidence, forwarded through recorder 18099 to
Bifrost 18080; it is not a live observation on this machine or all shard hosts.
VK hash equality is asserted in both sanitized wire layers; a secret/digest
value was not supplied for independent recomputation. Per-message hashes mean
the unredacted whole-body hash cannot be independently reconstructed here.
Native code omits the empty fallback field; its journal records `[]`, and the
observed responses/logs show no fallback. Do not claim native wire bodies
explicitly contained `fallbacks: []`. Mini's explicit empty list is unchanged.

## V4 pilot disposition and v4 to v5 changes

The ZIP contains **18 raw attempts**, **15 final slots**, **15 final independently
graded solves** and three preserved incomplete RuntimeErrors. Corresponding
grade artifacts match their rows, passed-test output is present, and the original
protected test bytes match the verified LF sources in original/grading snapshots.
All portable prompt/run fields match the local v4 plan; only absolute source and
task-file paths differ by machine. The three later retry rows point to the three
earlier attempt IDs; completed slots were not duplicated.

All **18 outer pilot rows remain incomplete**, top-level solve null, cost
incomplete and pool/report eligibility false. The three incomplete attempts also
have observed failing grades; infrastructure-incomplete status prevents those
grades from becoming measured task failures. Atul reports quota/429s, key rotation
and restart, but the selected ZIP receipts/results/events contain no HTTP-429 or
key/restart record. The later time window and retry lineage are observable;
the actual error codes, key identities and restart/config continuity still need
the closed Bifrost inventory. These are not three confirmed benchmark losses.

V5 adds only the [reviewed constrained resolver](bifrost-export.md) and evidence
validation. Null `served_model` needs all four observed alias/canonical/fallback/
rule fields present and null, both counters integer zero, and exact per-request
response routing requested = resolved = logged model/provider. The sidecar must
join request/session/VK name; existing exact VK-ID selection and completeness
review remain required. [Four native proof records](evidence/croc-native-routing-proof.json)
are retained separately. Missing proof, missing columns, nonzero retries,
aliases, fallback/routing mismatches or unsupported usage/rates reject. Raw nulls
stay null. No blanket inference is made for older mini rows.

All pre-v5 probes/pilots are excluded from the measured v5 cohort. Keep their
receipts, attempted calls and unknown costs; original `3a111322` remains ungraded
with unknown exact cause. No retrospective solve or zero-cost label is applied.
The 2+2+1 order, 30-step/600-second policy, independent restored-original grading,
and four accepted containment/output/cache/sampling limitations remain unchanged.
No hard-stop or cross-machine parity claim is added.

**Remaining condition: reviewed post-restart closed Bifrost inventory for all 18 pilot attempts, including actual 429 rows, both provider-key identities and per-machine VK/session/model/usage joins, followed by reviewed execution authorization.**

Strict validation exits **0**, five full/shard manifests validate and runtime/
price drift is empty. `--require-comparable` exits **1**. V5 is an immutable
blocked snapshot; do not flip its readiness booleans. Complete evidence requires
a supported reviewed authorization/successor, not mutation of v4/v5.

## New local bundle and exact commands

The local regenerated bundle is
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\release-gemini-54-v5-20261115`.
Data root was derived from the v4 bundle, then both LF JSON hashes were rechecked:
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\generated-lf-v2-20261115-31f9cef`.
Counts: full **54/270**, shards **14/70, 14/70, 13/65, 13/65**, smoke **3/15**.
Every bundle uses the same stable task/run IDs and order. Preparation runs no
agents or exercise code. Six `*-attestation.json` files bind clean publication,
config/runtime/price/input/plan/oracle identities and declared local mini settings;
local header readiness remains false. They do not attest Atul's machine.

For Atul, fill the following non-secret absolute path variables. The supplied
archive records LF data under `D:\bench-data2` and mini under Ubuntu-24.04 at
`/opt/mini-swe-agent/bin/python`; verify current paths/settings rather than copying
this machine's values. `$Bundle` must be NEW and external, with an existing parent.
Flags below were checked against actual CLI help.

```powershell
$Repo = ''         # clean person-4 containing published v5
$Python = ''       # Windows Python 3.12 venv python.exe
$LFData = ''       # verified LF builder output; archive recorded D:\bench-data2
$MiniSettings = '' # key-free actual machine settings; no credential values
$Bundle = ''       # NEW external v5 planning bundle
Set-Location -LiteralPath $Repo
$Config = "$Repo/bench/configs/gemini-benchmark-v5.json"
& $Python -m bench.release --config $Config --data-root $LFData --output $Bundle --mini-settings $MiniSettings --include-smoke
& $Python -m bench.canonical --config $Config --data-root $LFData --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $LFData --require-comparable
foreach ($Label in @('full','shard-1','shard-2','shard-3','shard-4','smoke')) {
    & $Python -m bench.attest --config $Config --data-root $LFData --plan "$Bundle/$Label.json" --oracles "$Bundle/$Label-oracles.json" --mini-settings "$Bundle/mini-settings.json" --output "$Bundle/$Label-attestation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Attestation failed' }
}
```

Attestation creation exits 0 for artifact creation only; comparison/execution
authorization stays false. Versions, secure state enrollment, actual settings,
request headers, closed logs and provider-key continuity need each operator's
evidence; none is inferred from a path or another machine's success.

The runner shape is unchanged, but remains **blocked**. Do not execute it or the
old v4 pilot against the changed v5 runtime; do not drop canonical arguments:

```powershell
# BLOCKED until a separately reviewed execution authorization/successor:
# & $Python -m bench.run --plan "$Bundle/smoke.json" --oracles "$Bundle/smoke-oracles.json" --mini-settings "$Bundle/mini-settings.json" --canonical-config $Config --canonical-data-root $LFData --output "$Bundle/smoke-results" --execute
```

No paid call, official shard, Bifrost database write or complete benchmark report
was performed during this release. The supplied v4 pilot remains limited
historical evidence, never a rewritten reportable cohort.
