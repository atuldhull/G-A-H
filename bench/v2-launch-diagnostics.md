# V2 launch diagnostics — 2026-11-15

Inspection started on clean, synchronized `person-4` at
`876bf35ac8919c7953c6d2b7c3d88d8293bdaed2`. This is a separate evidence/status
note: the immutable v2 config, protocol, runtime, grading rules and mini settings
are unchanged. No shard, agent or model request was run. No credentials or
database were opened. Atul's reported gateway/header/log verification remains
specific to his machine; no sanitized live artifact was supplied here.

## Actual gates, including the validator lock

`python -m bench.canonical --config bench/configs/gemini-benchmark-v2.json
--require-comparable` returns **1**. This is not a newly detected runtime/input
mismatch: strict validation passes, all 86 pinned runtime hashes match, the
verified real dataset matches, and all five prepared manifests validate.

The exact CLI predicate in `bench/canonical.py::main` is
`static_valid and cross_shard_comparable`. `validate_config` explicitly requires
both frozen readiness flags to be false and returns
`cross_shard_comparable=false`, `paid_runs_authorized=false`. It also requires the
unresolved mini-attempt entry. The three entries below describe required evidence;
they are not independent dynamically evaluated booleans. Supplying artifacts
will not make this immutable snapshot start returning 0. After evidence review,
an explicitly reviewed successor authorization/revision and its validator support
are required. Do not rewrite v2 or bypass the canonical runner flags.

| Frozen unresolved entry | Exact acceptance evidence | Where it can be obtained |
|---|---|---|
| `mini-attempt-3a111322` | Full attempt/run/session IDs, sanitized result row, full sanitized exception traceback with file/line and chained cause, matching receipt/process outcome, and grading `result.json`, stdout/stderr and relevant original/final test/helper paths. Identify the actual raise site. If no grading directory/result exists, report that absence explicitly. A demonstrated Person 4 defect requires synthetic reproduction and a focused regression; otherwise evidence must support a setup-only classification. | **Atul-only historical evidence.** No local substitute proves what happened in his attempt. Still absent. |
| `native-policy-binding` | A correlated native request/response/journal plus Bifrost log record with unique session/request IDs, logical gateway/version and UTC window, actual non-secret VK ID/name `vk-bench` / `bench`, requested and served model `gemini/gemini-3.5-flash-lite`, one-model cheap/strong chains, no configured fallback and no observed fallback, and the effective sampling fields described below. | Can be checked on **this machine when its gateway/provisioning and authorized log access exist**. Atul can separately supply his own native evidence; his mini row alone does not prove native binding here. |
| `per-machine-execution-and-cost-evidence` | Each operator's actual environment/dependency and policy settings, reviewed header-to-log mapping, authorized physical schema/version, exact IDs and independent closed/flushed complete request inventory, reviewed token convention and pinned native `prices.yaml` bytes/rates. All failed/retried requests must remain attributable; unsupported rows stay incomplete. | **Each machine/gateway owner.** Atul's historical inventory must come from Atul. Local static/input checks run here; local live completeness cannot be established without his setup equivalent. This is not a fourth parity gate. |

Additional runner predicates in `bench/attest.py::attest_plan` are:

| Predicate | Observed on this checkout |
|---|---|
| Static runtime/config/input identity | Pass; no runtime drift. Real inputs and five full/shard plans validated. |
| Frozen paid authorization | **False**; immutable snapshot restriction. |
| Frozen comparability authorization | **False**; immutable snapshot restriction. |
| Clean working tree | True before writing this diagnostics note; required again after commit. |
| Config publication provenance | Present: `876bf35ac8919c7953c6d2b7c3d88d8293bdaed2`. |
| Effective mini identity matches profile/transport and reviewed session header | Profile/transport match; **header verification false**, evidence reference empty in the local key-free settings. |

All predicates are required for `execution_authorized`. This is separate from
`eligible_for_pooled_report`: a limited three-task plan remains development-only
even if a future revision authorizes its execution. Four accepted limitations
(hard-stop containment, mini output cap, cache parity, sampling difference) remain
**limitations, not comparability gates**.

## Local checks and native request evidence

Only TCP connections to the approved `127.0.0.1:18080` were attempted:

- Windows: **ConnectionRefused**, native socket error **10061**.
- Ubuntu WSL2: **connection refused**, socket errno **111**.
- Installed mini in `/home/gunda/venvs/crocodile-mini/bin/python`: **2.4.6**.

No inference request was attempted. A listening port alone would not establish
Bifrost version, credentials, VK binding, model availability or log access. No
authorized local `logs.db`/snapshot path or flush interval has been supplied.
The gateway owner must provide reachability from Windows and WSL, secure
credential provisioning, and non-secret authorized log location/flush guidance
before a separately bounded native probe can be captured.

Source-confirmed facts, **not effective live settings**:

- `crocodile/adapters.py::GatewayEgress.chat` selects the `public` alias for a
  public native bench session. `_vk` prioritizes keyring service `crocodile`,
  entry `vk-public`, then `CROCODILE_VK_PUBLIC`. The alias is not the actual VK
  identity. An environment setting alone cannot prove the keyring choice or
  request binding. Never print/copy values into evidence.
- `chain_for` prioritizes `CROCODILE_CHAIN_CHEAP/STRONG`, then user settings,
  then built-in defaults; `bifrost_url` similarly allows environment/user
  overrides. The key-free bench profile does not automatically activate itself.
- `crocodile/loop.py` requests temperature 0.0, or 0.7 after a switch/rewind.
  The current gateway `chat` accepts `temperature`; the adapter forwards it and
  `crocodile/gateway/egress.py` records it in `model_request` and the request
  body. This establishes the source path, not provider acceptance/effect.
- A single configured Flash-Lite model gives an empty fallback list; the
  gateway may omit the wire `fallbacks` key when empty. Prove both the empty
  configuration and actual served-model/fallback outcome, not just one field.

A future **sanitized native probe record** must retain only an allowlist: Git
SHA/config ID, timestamp/window, gateway origin/version, session ID, request ID,
non-secret virtual-key ID/name, requested/served model, status, fallback
configuration/outcome, requested/forwarded temperature or explicit omission,
thinking policy and token categories. Attach a reviewed reference proving
whether the gateway/provider accepted, transformed, rejected or omitted sampling
parameters. If provider-effective sampling is unavailable, mark it unverified;
do not label source intent as observed sampling. No prompts, messages, tool
payloads, raw headers, key values or unsanitized exception payloads belong in
that record. A log row without sampling fields needs correlated sanitized
request/journal evidence; do not invent database columns.

Cost evidence additionally follows [bifrost-export.md](bifrost-export.md): exact
session/VK selection, stable gateway origin, independent request-ID inventory,
reviewer/evidence reference and the named review flags (`vk_binding_verified`,
`session_finished`, `log_flush_verified`, `request_inventory_complete`,
`retention_verified`, `quiescent_snapshot_verified`, `gateway_origin_verified`),
plus `usage_convention=prompt-includes-cache;total=prompt+completion`. These are
evidence requirements, not flags to set merely because a request succeeded.

## Mini attempt and three-task smoke decision

Repository inspection found references to the attempt prefix only in config,
documentation and synthetic tests, not an actual result row/traceback/grading
artifact. The reported 26 steps, `Submitted` and return code 0 do not establish
the host exception's cause or an independent grade. Preserve **incomplete**;
do not count a measured failure, guess a fix or weaken grading. No runtime fix or
purported regression for that unknown cause was made.

An in-memory selection from the verified v2 inputs still prepares **3 tasks /
15 slots** (shard 1, `--limit 3`: affine-cipher, beer-song, book-store). It does
not execute anything or establish readiness. **A three-task live smoke cannot
run yet:** the historical mini diagnosis, live native/VK/header readiness,
per-machine evidence and reviewed successor authorization remain unresolved.

Validation for this note: the three existing tests for published-v2 immutability,
blocked `--require-comparable`, and pre-dispatch rejection passed; Ruff on
`bench/` passed. The config's raw SHA-256 remains
`4cdf9b9331d84981c624ecdf0ac3a8b9114f50f9374ad1ae89ad4021080e48f6`.
Only this diagnostics document changed; no speculative mini regression or live
security assertion was added.
