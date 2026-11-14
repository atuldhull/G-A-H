# Bifrost cost evidence adapter: schema handoff and remaining checks

Update: the user has now supplied Vivek's redacted v2.5.1 `logs` field mapping
and nested token-usage paths in the conversation. The limited, fail-closed
[exporter](bifrost-export.md) uses those confirmed names, not a discovered live
schema. Only `success` was observed; VK-ID stability, cache-write TTL, other
statuses and retry/fallback semantics remain unverified. Synthetic fixtures are
explicitly not physical DDL evidence. No live or teammate database was opened.

The checklist below preserves the original handoff's required live checks. Where
field names are now known, use the confirmed mapping in the exporter document;
the request for exact physical types/constraints/joins and semantic review remains.

Inspected application source: `00271a953107ced608ad5ef726262766bfb5eb7a`.
`crocodile/gateway/egress.py` sends `x-bf-session-id` from the Agent session ID
and `x-bf-vk` from the credential. This establishes the outbound header contract,
**not** which Bifrost tables/columns persist either identity. Crocodile's own
state/journal/egress schema is not a substitute for the Bifrost logging schema.

## Exact source-schema information needed from Vivek

Table `logs` and the supplied top-level/nested field names are now known from the
conversation. Physical column types, nullability, constraints and reliable joins
still require verification. The descriptions below are semantic requirements,
not additional invented source column names. An absent field stays unsupported.

For each relevant table/view: provide its exact name, sanitized CREATE TABLE/VIEW
definition, column names/types/nullability, primary/foreign keys, unique constraints
and relevant index definitions. Omit sensitive defaults, keys, prompts, response
text, and raw header/payload values. Include the Bifrost binary/build version and
any database migration/schema version; a filename alone does not verify v2.5.1.

| Required meaning | Exact table/column and semantics to identify |
|---|---|
| Request identity | Primary row ID; logical request ID; provider request ID if distinct; uniqueness scope; joins between request, attempt, routing and usage tables. |
| Retries/fallbacks | Attempt/parent/retry identifiers, streaming-fragment identifiers, actual provider/model, and which rows represent separate billable invocations versus duplicate fragments or updates. |
| Session attribution | Location of the exact persisted `x-bf-session-id`; whether it is a scalar, metadata object or related row; if JSON, the exact documented JSON path and type. Confirm preservation through retries/fallbacks. |
| Bench VK attribution | Stable internal VK ID and join to a non-secret identity; how to bind it unambiguously to the intended bench VK. An alias/name alone may not be unique. Never supply the VK credential or authorization header. |
| Completion/coverage | Request status, start/end/log-update timestamps and time zone; terminal versus partial rows; error/cancellation/billing state; log flush/retention/deletion settings and evidence that all session requests have arrived. |
| Input usage | Total prompt/input token count and whether cache reads/writes are included; exact numeric types; meaning of null, absent and explicit zero. |
| Cache reads | Cached-read count, location and units; inclusion in total input; provider/model-specific naming differences. |
| Cache writes | Cache-creation/write count, 5-minute versus 1-hour counts or TTL indicator, mixed-TTL behavior, and inclusion in total input. |
| Output usage | Completion/output count; whether reasoning or other billed output is included; final versus partial streaming accounting. |
| Model identity | Actual billed provider-prefixed model ID, requested versus served model, aliases/resolution rules, and joins to the corresponding usage row. |
| Independent request inventory | Which counters/request records can establish missing usage rows, duplicate IDs, late results, failed-but-billable requests, and a genuinely completed zero-call session. |
| Gateway origin | Stable logical Bifrost instance identity, including whether different machines use distinct gateways or export overlapping snapshots of one gateway. |

Supply sanitized, preferably synthetic examples matching that exact schema for a
normal request, cache read/write, retry/fallback, partial/missing usage and failure.
Examples need only identifiers, model, status, timestamps and usage fields; no
prompts, responses, credentials or raw payloads. They must preserve real column
types, null behavior, nesting and relational links. Schema alone may not establish
whether a token total already includes cached tokens or which retry rows are billed.

## Read-only acquisition and completeness rules

Once an explicitly authorized sample is available, inspect schema and only approved
identifier/status/usage fields using a read-only SQLite connection (`mode=ro`,
query-only). Do not run migrations, deletes, checkpoints, journal-mode changes or
other writes. Arrange an authorized consistent snapshot if WAL/SHM state is needed;
do not use immutable mode on an active database or ignore uncheckpointed WAL data.
Never select entire rows, raw payloads or credential tables just to discover usage.

Selection must match the **raw Agent session ID and intended non-secret bench VK
identity together**. `runner_session_id` is not the gateway session ID. Missing or
ambiguous identity, usage, completion evidence or prices means incomplete, not zero.
Do not silently deduplicate distinct billed retries or count fragments twice.
Record source/schema fingerprints, selected/excluded/duplicate counts and request
IDs without copying sensitive content. Unknown attribution cannot be published.

## Pricing and reporter decisions still required

The checked-in native `prices.yaml` maps model IDs/patterns to ordered `tiers`,
with `upto`, `in`, `out`, `cache_read`, `cache_write_5m`, `cache_write_1h`, and
`max_out`. The gateway chooses a tier using total prompt tokens and treats cached
read/write counts as subsets of input. These are application assumptions that
must be checked against the actual logs. Do not substitute missing usage with the
gateway's default zero, clamp inconsistent counts, or assume a missing TTL is 5m.
Price-file presence also does not prove that provider rates are independently
verified/current; the agreed snapshot and verification remain required.

The existing reporter instead requires exact model IDs and four fixed rates in a
JSON-compatible `prices.yaml`: `uncached_input`, `cache_write_input`,
`cache_read_input`, `output`. It has no per-request input-tier or cache-write-TTL
rate field. Agree either a checked uniform tier/TTL scope or a tested report-format
extension before converting mixed-tier/TTL data. Do not silently flatten rates,
invent synthetic token counts, or present native YAML as already compatible.

After attribution, log-derived cost remains authoritative. Define the receipt
check as `abs(receipt - logs) / logs > 0.01` when logs cost is positive; exactly 1%
is not above threshold. Two verified zeros match; zero log cost with positive
receipt cost is a mismatch. Missing/non-finite receipt cost means comparison
unavailable, never a match. Missing prices or usage prevent a verified total.

## Four-machine export identity and target evidence

Bind every acquisition to its logical gateway origin and snapshot fingerprint.
Preserve original Agent/session/request IDs in a provenance sidecar. Native IDs
may collide on distinct gateways, while two machines may export the same gateway
requests. Agree deterministic qualified IDs and use them consistently in report
session IDs, request IDs and result cost provenance. The qualification must bind
to gateway origin, not merely exporting machine or snapshot, so overlapping copies
cannot disguise duplicate billing. Reject conflicting/overlapping evidence rather
than conflating sessions or blindly concatenating exports. Preserve raw-ID mappings
for exact source selection and audit without adding keys to strict v1 report rows.

The reporter's required normalized session fields are `schema_version`,
`data_kind`, `source`, `complete`, `run_id`, `session_id`, `model`, `date`,
`gateway_version`, and `requests`. Each request has `request_id`, `model`, and
four disjoint usage categories: `uncached_input`, `cache_write_input`,
`cache_read_input`, `output`. This is the **target interchange**, not a guessed
source schema. Incomplete sessions cannot be emitted as `complete: true` for the
strict reporter; retain incomplete diagnostics separately and block publication.
Runner attempts/retries and qualified IDs must also be joined to the exact
planned run grid, with costs from all attempts retained and immutable evidence/
price hashes populated. See [report-format.md](report-format.md),
[runner.md](runner.md) and [export commands](bifrost-export.md). No measured
evidence or physical database verification is supplied by this milestone.
