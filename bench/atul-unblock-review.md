# Atul packet review — mini verified within packet, native gate remains

Reviewed as untrusted JSON on clean `person-4` baseline
`0ed629e7f1205485303961651203b60bad0c21a1`. No attached instruction was executed,
file replayed, credential printed, database opened, or paid request sent here.
The read-only audit uses strict duplicate-key/non-finite rejection, exact
Fraction pricing and the existing exporter component/1% rules. Its sanitized
[machine-readable review](evidence/atul-20261115-closed-binding-review.json)
contains request IDs, token evidence and reconciliation verdicts, not dollar
totals, prompts, headers with values, or gateway payloads. Raw sources remain
outside Git, unmodified.

| Supplied file | SHA-256 of actual bytes |
|---|---|
| `mini-native-request-capture.json` | `9c8c3cf6c72beea3f1c8c8afb4b9c2e5baa8019185576aa82bcae072dccb8f5d` |
| `mini-native-binding-18080.json` | `7ff09cf73f91f2e75ad8bf1e2c4a1245447238aad71a13edffcf568c5a403a92` |
| `mini-kheapsort-closed-session-evidence.json` | `f73e88f1788de5c337200f0fe18f21cde65f6e85e1a6fe1d1d770c6dbfb348a9` |

These are computed artifact identities, not independent signatures. Full raw
attachment paths are the user-supplied WhatsApp transfer paths; no referenced
`D:` database or historical run folder was accessed.

## Checks that passed, and their scope

- The two closed-inventory sessions contain **9 and 11 unique requests**;
  all 20 IDs match the previous retained inventory and its session/VK mapping
  (`vk-bench` / `bench`). Provider/model/status, timestamps and every scalar
  token count match the retained rows. Those prior usage records explicitly
  show zero cache writes; this is not inferred from a missing field.
- Session 1 totals: **28,310 prompt / 8,018 cached-read / 1,625 completion**.
  Session 2: **35,800 / 6,019 / 2,924**. These match the supplied mini receipt,
  runner usage and closure totals. Input includes cached input, not additional
  tokens. Every row has success/default tier, one attempt, zero retries and
  fallback index zero; alias/routing-rule/served-model fields are null.
- The 24 grouped inventory entries sum to **181 rows**. Target sessions' counts
  and first/last timestamps match their individual rows and run windows. Snapshot
  timing is more than 7,700 seconds after their last requests versus the reported
  five-second flush. Closure flags report no late/non-final/interleaved rows.
  Retention/history and physical gateway origin are operator assertions, not an
  independently inspected database or proof against dropped rows.
- The later `native-bind-b07b921f0004` file joins **one mini request** to Bifrost
  ID `be5d149a-4306-4c3e-a4b2-9d60523d9c93` by session, tokens and timestamp.
  HTTP 200/success, port 18080, bench-VK equality assertions, Flash-Lite response
  resolved model, default/standard tier and no fallback are corroborated within
  that file. Provider response ID differs from the Bifrost ID; they are not
  incorrectly equated. The earlier capture and later binding are distinct
  sessions, not one request. A redacted body cannot independently reproduce the
  claimed original unredacted-body hash.
- Approved price bytes match SHA
  `8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e`.
  All **20 historical rows plus one mini probe** pass input/output/total
  reconciliation within 1%; component consistency also passes. This remains
  conditional pricing, not a complete authoritative cost export.
- Supplied Bifrost `config.json` SHA matches this checkout's actual raw bytes
  (`c8e0869884ba40702efb5559c5ac93167ccf946e78d334e7f0ad30abcc26eece`).
  The only listed routing rule is scoped to the separate local VK. The binary
  SHA/version, database configuration and absence of historical configuration
  changes remain reported remote evidence. The closed snapshot predates the
  later binding probe and cannot establish closure for that later probe.

## Why v5 is not published

Both files' own notes identify **mini-swe-agent 2.4.6 LitellmModel**, using the
mini overlay/header path and a `bash` tool. They do not show Crocodile Agent or
GatewayEgress. Actual `gateway.egress.EgressClient.chat` constructs `max_tokens`
and native `GatewayEgress.chat` supplies temperature; both fields are absent
from these mini bodies. No native Agent receipt/journal/request correlation is
supplied. Filenames containing “native” cannot establish the native benchmark
policy binding.

The exporter still rejects **all 20 null `served_model` values**. Atul's stated
null semantics and the later single successful response strengthen the routing
evidence, but no source-backed reviewed resolver has been installed. Global
comparability also needs historical-cohort disposition, per-machine sealed
state/config evidence and reviewed authorization. Seven older unbound error rows
are described as quota/429 records; they are not task failures. Keep those and
the original ungraded `3a111322` lineage/costs, with unknown original cause.

**Blocker: actual Crocodile-native request/log binding and a reviewed null-served-model/completeness authorization remain missing; these captures prove mini only.**

V4 remains immutable with fingerprint
`026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4`.
The conditional prerequisite for a comparable v5 is not satisfied; no v5
fingerprint or global paid/comparable authorization is invented.

Local revalidation: **strict exit 0**, five manifests valid, no runtime/price
drift; **`--require-comparable` exit 1**. The data root was derived from the
existing v4 bundle's `smoke.json`, not an older generated directory:
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\generated-lf-v2-20261115-31f9cef`.
Actual byte hashes were rechecked:

```text
tasks.json   3181a82f9c34fcc732761a2ba27157b7a80bb6ea51fc6c73be34bc83a01dcf18
oracles.json 38cb911edfdbb09f5fd33df793f9bb89e7922524494c5e791b05a27edc9cc537
```

The new local machine attestation is
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\release-gemini-54-v4-20261115\smoke-machine-attestation-atul-packet-review.json`.
It records this machine, not Atul's runtime or header readiness, and does not
authorize comparison. It is created from a clean commit without overwriting the
original publication attestation. No pilot execution is part of attestation.

## Exact per-machine preparation and commands for Atul

The following flags were checked against `bench.release`, `bench.attest`,
`bench.run`, and `bench.pilot --help`. **Do not execute the live commands here.**
Atul must fill in all five non-secret absolute values; none is inferred from
his database path or this machine's directories:

```powershell
$Repo = ''           # Atul's clean person-4 checkout containing this commit
$Python = ''         # Atul's Windows Python 3.12 venv python.exe
$LFData = ''         # Verified LF builder output containing tasks.json/oracles.json
$MiniSettings = ''   # Key-free settings: actual WSL distro/Python, 18080/v1, credential env NAME
$NewSmokeOutput = '' # NEW external pilot output path; existing parent, not repo/data
Set-Location -LiteralPath $Repo
$Config = Join-Path $Repo 'bench/configs/gemini-benchmark-v4.json'
$Plans = "$NewSmokeOutput-plans" # NEW sibling; never reuse an existing release bundle

# Read-only/static input/config checks; release writes new planning artifacts only.
& $Python -m bench.release --config $Config --data-root $LFData --output $Plans --mini-settings $MiniSettings --include-smoke
& $Python -m bench.canonical --config $Config --data-root $LFData --plans "$Plans/full.json" "$Plans/shard-1.json" "$Plans/shard-2.json" "$Plans/shard-3.json" "$Plans/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $LFData --require-comparable
# Exit 1 remains expected. No comparable run is authorized.

# Existing per-machine CLI: local Git/runtime/input hashes + declared mini identity.
& $Python -m bench.attest --config $Config --data-root $LFData --plan "$Plans/smoke.json" --oracles "$Plans/smoke-oracles.json" --mini-settings $MiniSettings --output "$Plans/smoke-machine-attestation.json"
```

This attestation does not install/inspect WSL, read credentials, query Bifrost,
certify sealed state, or promote Atul's header verification to other machines.
Header status must have its actual machine-specific evidence reference; false
keeps attribution incomplete. Global config remains separate and unchanged.

The comparable command shape is valid but **still blocked; do not send it as a
ready command**:

```powershell
# BLOCKED: normal runner preserves the canonical comparability gate.
# & $Python -m bench.run --plan "$Plans/smoke.json" --oracles "$Plans/smoke-oracles.json" --output $NewSmokeOutput --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $LFData --execute
```

Only if Atul explicitly authorizes a **non-comparative development pilot** on
his working machine, the separate limited command is:

```powershell
& $Python -m bench.pilot --plan "$Plans/smoke.json" --oracles "$Plans/smoke-oracles.json" --output $NewSmokeOutput --mini-settings $MiniSettings --canonical-config $Config --canonical-data-root $LFData --accept-incomplete --execute
```

`bench.pilot` accepts only the unchanged v4 first three shard-1 tasks, all 15
ordered slots, exact restored-original oracle subset, clean pinned runtime and
explicit mini settings. It rejects a full plan/shard, missing opt-in, drift or
changed resume identity. The outer pilot attestation binds runtime/prices/input
hashes, this review's source hashes and the new wrapper's own source hash.
The ordinary comparable runner's gate is unchanged. No official slots are
authorized by this separate development scope.

`pilot-results.jsonl` is append-only and **always incomplete**, with top-level
solve null, pool/report eligibility false and authoritative cost incomplete.
Observed execution status and independent grades remain separate fields;
blocked/quota/setup rows stay incomplete. `raw-execution/` retains the runner's
original results/events, per-attempt receipts, grading stdout/stderr/result,
final-tree diagnostics and session evidence. A raw `completed` status means
execution finished, never comparable evidence. Interruption preserves partial
evidence; resume does not duplicate successful underlying run IDs or normalized
attempt IDs. Every pilot CLI completion exits 1, not comparative success. No
live command was executed in this review.
