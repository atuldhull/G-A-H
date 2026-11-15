# Post-restart inventory audit — v5 remains limited

Reviewed 2026-11-15 from clean `person-4` commit
`d906adf9d123bf9bd61269db7b42543e8fea1280`. Input:
`pilot-v4-18-attempt-bifrost-inventory.json`, 106,011 bytes, SHA-256
`02b59d2eeff208a13f0405e21d01f16973e7c17c29cbe74d5ecadace66c92c67`.
The JSON was parsed with duplicate-key/non-finite rejection, as untrusted data;
its narrative was not executed or treated as independent proof. No provider-key
value, identifier or fingerprint is reproduced in this review.

[Machine-readable audit](evidence/pilot-v4-18-attempt-inventory-review.json)
records each accepted/rejected claim, all 18 attempt/session/run joins, request
IDs, discrepancy details and the actual validator result. The retained source
ZIP hash was checked before reading its result/grading metadata. No ZIP code was
executed or extracted. All raw attachments, v4/v5 configs and frozen evidence
remain unchanged; this new audit does not rewrite their historical conclusions.

| Claim | Decision and actual evidence |
|---|---|
| All 18 attempts and retry lineage | **Accepted within the packet.** Attempt IDs, run/variant/session IDs, times, statuses, grades and `prior_attempt_ids` exactly match all archived runner rows. The three retry rows point to their earlier incomplete attempts. |
| Unique request joins | **Accepted within the packet.** 92 distinct request IDs match their declared lists and exact attempt session; no cross-attempt duplicate. This is not a global database uniqueness proof. |
| Three terminal HTTP 429 errors | **Accepted.** Three final per-attempt rows explicitly contain HTTP 429, `RESOURCE_EXHAUSTED` and provider code `429`, agreeing with terminal closure metadata. This resolves the earlier absence of status evidence. They remain infrastructure-incomplete, not measured task failures. |
| Only three HTTP errors | **Rejected.** There are four error requests: the three terminal errors plus a nonterminal 429 in completed beer-song mini run-2. That session has nine successful rows for nine steps plus the error. The notes attribute it to LiteLLM retry; exact within-step causality is not independently proved. |
| 15 final graded outcomes | **Accepted as historical outcomes.** All 15 latest grading artifacts match the retained runner records and show solved/exit 0. All 18 outer pilot rows still say incomplete, solve null and nonreportable. |
| All token totals match | **Rejected.** 17 of 18 runner totals equal successful-log totals. Book-store mini run-1 undercounts prompt/cache-read/completion by **27,530 / 20,294 / 98**. One unique pair of provided requests equals this gap. The arithmetic is established; the cause of the receipt omission is not. |
| Scalar charge arithmetic | **Accepted conditionally.** All 88 successful rows pass input/output/total comparisons within the pinned 1% rule and the separate bounded component-consistency check. Twelve available receipt estimates match provided successful-row totals; six receipt costs are unavailable. One success row has null `service_tier`; no blanket Standard-tier provenance is inferred. No dollar total is published. |
| Complete usage and session costs | **Rejected.** Four error total costs are null and cannot be assumed free. All 92 rows omit `token_usage`, `total_tokens`, parent-request relationships and explicit cache-write categories required by the exporter. Scalar no-write arithmetic checks do not establish absent categories as zero. |
| Model/VK/fallback fields | **Partially accepted.** All 92 rows name Gemini Flash-Lite and VK name `bench`, with null alias/canonical/served/fallback/rule fields and integer-zero gateway retry/fallback counters. Actual served-model resolution and stable VK-ID binding remain unproved: this inventory has no `virtual_key_id` or per-request response `routing_info`; the earlier four native proofs have different request IDs. Gateway retry counters do not disprove client retries. |
| Key rotation/restart continuity | **Partially accepted.** Six non-pilot 401 rows followed by two successful checks corroborate recovery before the three retried attempts. Those eight rows are kept out of pilot request counts. The timeline is an operator record; it does not independently prove exact process/config continuity or a key-value change. Only current key fingerprint metadata is supplied, without comparable pre-rotation evidence. All 88 successes reference the current key-record label; all four error key references are empty. No key values/fingerprints are displayed or stored here. |
| Closed/flushed complete inventory | **Partially accepted.** Every provided request lies within its archived runner window, with zero provided late rows; the youngest row is **8,234 seconds** before the snapshot, beyond the reported approximate five-second flush. These checks corroborate delayed capture, but do not establish full selection/retention/quiescent-snapshot/gateway-origin completeness from the curated JSON alone. |
| Explicit execution authorization | **Rejected as absent.** No authorization is supplied by the inventory; immutable v5 still records authorization and comparability false. |

The discrepancy pair for book-store mini run-1 is
`cab20c4c-cd6f-4f08-802e-b9eafbd1d69f` and
`da186179-da65-4cf6-83d7-c46706171dbf`. All supplied log rows remain authoritative
evidence to retain; do not drop them to make a receipt match. The three terminal
errors and the extra nonterminal error also retain their earlier successful
calls and unknown error charges. Do not convert unknown cost into zero.

## Gate result

Immutable v5 fingerprint remains
`93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83`.
The actual read-only `bench.canonical --require-comparable` command returned
**exit 1**, with static validation/input hashes valid and zero runtime drift.
`cross_shard_comparable=false`; `paid_runs_authorized=false`.

Remaining gap: reviewed complete per-machine cost/route/VK evidence, including
the missing usage categories, four error charges and verified restart/key/flush
continuity, followed by explicit supported execution authorization. Preserve v5
as an immutable blocked snapshot; a separate audit is not a ready-flag override.
No fresh smoke execution command is issued, and no tasks or shards were run.
