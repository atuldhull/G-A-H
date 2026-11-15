# Gemini 54 v4 — price-corrected, live execution blocked

[Immutable v4 config](configs/gemini-benchmark-v4.json) pins runtime checkpoint
`deaf328ab72c5149ba8e67a511a606b912aa4b1e`, including integrated main
`af6974a3efb4977364f3a572509c41a9752e8ba4` through merge
`9605ac526779b015f8ceb5a11a3eb771be5bac90`. All 87 runtime/price source hashes
were checked against that Git checkpoint and the checkout. The publication
commit is recorded by Git and each clean attestation, avoiding self-reference.

```text
v4 config ID    026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4
v4 raw LF SHA   357c0937e274500d226033b03b2d2fc199bbff169f22c8bea2793b6d29ac2eb7
price Git SHA   8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e
price Git blob  5d9f09f632b85bab7afb446372023d335cd44677
tasks.json      3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18
oracles.json    38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537
full-plan ID    da56c686fe979620275686e46042696330d6d91a37c20c9409063111561188f6
```

V1/v2/v3, prior inventories and token evidence remain unchanged. V3 config ID is
`c0d48d86fe8169947e9997dd5fa33f642fa6d53afbc2f54756ce6ea1dd049ee1`, raw LF SHA
`b3320171326ce1712add548bc8148d838762f219090765a9bf8946ed2a1326ba`.
V3 now audits the expected exporter/validator/price drift; no old pin is waived.

## V3 to v4 changes and unchanged experiment

- Corrected main's Gemini 3.5 Flash-Lite Standard rates: input 0.30/M USD,
  output including thinking 2.50/M, cached input 0.03/M. The old price snapshot
  `ed1a9e23723d68b53268e2bc1683731e8e539dc46f70091f213525d58603f503` is historical.
  `google/*` is unchanged; no Google-alias or other-model rate substitution.
- Logged component consistency uses the smallest of **8 binary64 ULPs** at the
  larger compared magnitude, **1e-12 USD absolute**, and **1e-12 relative**.
  There is no epsilon floor; zero/nonzero values, overflow and underflow cannot
  create a match. Both component sum/JSON-total and scalar/JSON-total comparisons
  use this bound. No source value is rounded or rewritten.
- The separate **strictly greater than 1%** price/receipt rule is unchanged.
  Exact token/rate arithmetic remains authoritative. Material component errors
  remain incomplete even when below 1%; missing usage and ambiguous routing
  still reject. Fourteen synthetic row shapes, scalar differences, ULP/cap/zero
  boundaries and negative cases exercise these rules.
- V4 validation explicitly checks that its precision policy matches the exporter.
  [The re-audit](evidence/mini-kheapsort-v4-audit.json) records 20 accepted usage
  rows, resolving the previous 14 component-roundoff rejections, and 20 price
  comparisons within 1%. All 20 null served-model identities still reject.

Dataset commits are unchanged: Polyglot
`7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`, QuixBugs
`4257f44b0ff1181dedaedee6a447e133219fcebf`. All 54 original source/prompt/oracle
references, portable digests, LF index hashes and builder MANIFEST were validated.
No exercise, agent, paid model or real benchmark test was executed in preparation.

The fixed 54-task order, contiguous ranges **1–14 / 15–28 / 29–41 / 42–54**,
and per-task order **Crocodile 1, Crocodile 2, mini 1, mini 2, twin 1** remain.
Bifrost 2.5.1, endpoint 127.0.0.1:18080 (mini /v1), bench VK logical identity
vk-bench/bench, Flash-Lite wire models/chains, no measured fallbacks/escalation,
provider-default thinking, flags and independent restored-original grading remain.
Never store VK values. Step/wall policy is 30/600; grading is separate with 180s
pytest timeout. Atul's accepted hard-stop containment, mini output-cap, cache
parity and sampling differences remain documented limitations, not new gates.

## Twenty-request audit and remaining evidence

Source replacement inventory SHA is
`cdffbd2b9cf7e815ce1984acaa8ba8fb65a85e02d854c81719d10bbd7213eff9`.
It was read without mutation; no physical database, key or payload was accessed.
The nine requests for `mini-24877326f8de47f88029728cd8deb95c` and eleven for
`mini-51b92bfe4ea34390b90e76d031e9c67f` retain matching IDs/VK/requested model,
success status, consistent scalar/nested usage and explicit zero cache writes.
Conditional requested-route pricing still agrees within 1% for all twenty.

The audit does **not** produce a complete cost export. Zero fallback/retry fields
and single-model config corroborate requested routing, but actual `served_model`
is null. No null field is converted to Flash-Lite by assumption. The selected
inventory and matching step/usage sums do not independently prove close, flush,
retention, quiescence or absence of other/late requests. All original and later
attempts/costs stay retained; `3a111322` remains ungraded preparation failure,
exact original cause unknown, with later reproductions not recurring.

| Frozen gate / owner | Exact evidence needed before any separately authorized smoke |
|---|---|
| `mini-attempt-3a111322` — Atul / Person 4 / reviewer | Explicit disposition of the historical incomplete attempt and unattested rerun cohort, retry lineage and earlier costs. No retroactive solved/zero-cost label; original root cause remains unknown. |
| `native-policy-binding` — Person 1 / Person 2 / operator | Sanitized actual native request/log correlation for single Flash-Lite chains, 18080 endpoint, same stable bench VK, billed model and no fallback. Profile intent or mini-only records are insufficient. |
| `per-machine-execution-and-cost-evidence` — Person 2 / operators / Person 4 | Actual served-model/routing joins, or reviewed Bifrost null/alias semantics plus pinned routing proof and a separately reviewed resolver if required. Current exporter still refuses null. Independently reviewed finished/flushed/retained/quiescent complete request inventory, origin/version/VK binding and usage convention; valid owner-enrolled sealed state and secure per-machine transport/settings/environment attestations. |

Exporter review flags are `vk_binding_verified`, `session_finished`,
`log_flush_verified`, `request_inventory_complete`, `retention_verified`,
`quiescent_snapshot_verified`, `gateway_origin_verified`, plus reviewer/reference
and `prompt-includes-cache;total=prompt+completion`. True values require their
underlying evidence; this milestone supplies none by declaration alone. Local
Windows/WSL live connectivity/header readiness is not established by this prep.

## Prepared bundle, validation and attestations

All artifacts are outside the repository:

```powershell
$Python = 'C:\Users\gunda\venvs\crocodile\Scripts\python.exe'
$Base = 'C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132'
$Data = "$Base\generated-lf-v2-20261115-31f9cef"
$Bundle = "$Base\release-gemini-54-v4-20261115"
$Config = (Resolve-Path 'bench/configs/gemini-benchmark-v4.json').Path
$MiniSettings = (Resolve-Path 'bench/configs/mini-settings.ubuntu.json').Path
# Reproduction requires a NEW output path; existing artifacts are immutable:
& $Python -m bench.release --config $Config --data-root $Data --output $Bundle --mini-settings $MiniSettings --include-smoke
& $Python -m bench.canonical --config $Config --data-root $Data --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $Data --require-comparable
# Strict validation exits 0; --require-comparable exits 1. Neither authorizes a run.

# From the clean publication commit; outputs must be new:
foreach ($Label in @('full', 'shard-1', 'shard-2', 'shard-3', 'shard-4', 'smoke')) {
    & $Python -m bench.attest --config $Config --data-root $Data --plan "$Bundle/$Label.json" --oracles "$Bundle/$Label-oracles.json" --mini-settings "$Bundle/mini-settings.json" --output "$Bundle/$Label-attestation.json"
    if ($LASTEXITCODE -ne 0) { throw 'Attestation creation failed' }
}
```

Counts are **54/270**, four shards **14/70, 14/70, 13/65, 13/65**, smoke **3/15**.
All six manifests match independent `bench.plan --dry-run` output byte-for-byte.
The smoke is shard 1/4's first three tasks (`affine-cipher`, `beer-song`,
`book-store`), development-only with no QuixBugs coverage. Oracle subsets retain
exact originals; `release-preparation.json` records hashes and not-executed
commands. Six attestations bind clean publication/runtime/config/plan/oracle
identities and key-free mini settings, with no runtime/price drift. The local
settings keep session-header verification false; do not copy Atul's flag as local
proof. `full-attestation.json` and `smoke-attestation.json` are the main entry points.

The bundle's `prices.yaml` contains exact approved Git bytes (hash `846923...`),
and `price-snapshot.json` records commit/blob/hash. Windows CRLF working-file bytes
have a different raw hash and are not the canonical exporter snapshot.

V4's strict CLI exits **0**, dataset and manifests validate, runtime/price drift
is empty. `--require-comparable` exits **1**, with paid authorization and
comparability false. This is an immutable blocked successor; do not flip its
booleans or drop canonical flags. Live evidence needs review and a supported
authorization revision/mechanism before execution. Earlier cohort repricing
alone does not establish identical runtime, budgets or policy; explicit
compatibility review remains necessary. No paid run or official shard is enabled.
