# Read-only Bifrost cost evidence (limited mapping support)

The user supplied Vivek's redacted v2.5.1 field mapping in the conversation. This
is **schema evidence**, not verification of a physical database or a complete
session. No teammate drive/database, keys, live requests or paid models were used.
Tests create SQLite fixtures with those column names and explicitly synthetic SQL
types/constraints. No source-table or nested usage key is discovered by guessing.

## Confirmed mapping and supported scope

The fixed source is table `logs`, with `session_id`, `id`, `parent_request_id`,
`virtual_key_name`, `virtual_key_id`, `provider`, `model`, `served_model`,
`prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_read_tokens`,
`token_usage`, `cost`, `status`, `timestamp`. Other columns are never selected.
The only accepted status is exactly `success`; parent IDs must be SQL NULL.
Empty strings do not substitute for absent parent IDs.

Confirmed `token_usage` JSON paths are:

```text
prompt_tokens
completion_tokens
total_tokens
prompt_tokens_details.cached_tokens
prompt_tokens_details.cache_write_tokens
cost.input_cost
cost.output_cost
cost.total_cost
```

All five token counts must be explicitly present, nonnegative integers. The
JSON totals/read count must equal the scalar columns. A reviewed convention must
establish that prompt tokens include cached reads/writes and total equals prompt
plus completion. Cached portions cannot exceed prompt tokens; no clamping or
missing-to-zero defaults are used. JSON cost fields, when present, must sum
consistently and agree with a supplied scalar cost. Missing Bifrost cost fields
do not replace token-derived pricing; receipt and stored Bifrost cost are never
the authoritative charge. Invalid or contradictory supplied cost fields fail.

Component consistency allows only binary64 representation noise: the smallest
of **8 ULPs** at the larger compared magnitude, **1e-12 USD absolute**, and
**1e-12 relative**. There is no epsilon floor, zero/nonzero costs cannot match,
and overflow/underflow cannot create a tolerance. Both input-plus-output versus
JSON total and scalar versus JSON total use this bound; material mismatches
remain incomplete even below 1%. Raw SQLite/JSON evidence is never rewritten.
This precision policy is independent of the unchanged **1% price/receipt
discrepancy rule**; authoritative pricing still uses exact token/rate arithmetic.

Supported complete costs are **ordinary success and cache-read success, with
explicit zero cache writes**, no retry/fallback relationship and a known served
model with a single unbounded native price tier. Bare served model names are
prefixed with `provider`; already-prefixed names must agree with that provider.
Requested, actual and planned model identities must agree for v1 report evidence.
Prices resolve an exact entry first, otherwise exactly one declared `provider/*`
match. Unknown/ambiguous models, absent/negative/non-finite rates, bounded or
multiple tiers, or missing served model make the session incomplete.

**Positive cache writes remain incomplete** because the supplied mapping does
not establish TTL. Neither 5m nor 1h is guessed. Retry parents, differing served
models, and other statuses also remain incomplete until their billing/completion
semantics are reviewed. Their request IDs, parents and statuses stay in diagnostics.
The checked-in Haiku model currently has multiple tiers: it is intentionally
unsupported, even for a request apparently below its first threshold. Do not
change benchmark models to evade this limitation; tier support needs a reviewed
report-format extension.

## Closed-session selection and explicit review

`selection.json` must supply `run_id`, raw Agent `session_id`, stable
`gateway_instance_id`, `gateway_version: "2.5.1"`, `data_kind` (`measured` or
`synthetic`), expected non-secret `virtual_key_id` and `virtual_key_name`, exact
planned `model`, UTC `date` (`YYYY-MM-DD`), and independent complete `request_ids`.
Its `review` object requires a reviewer name and evidence reference plus:

```json
{
  "reviewer": "<actual reviewer>",
  "evidence_reference": "<reviewed closed-session inventory and source checks>",
  "vk_binding_verified": false,
  "session_finished": false,
  "log_flush_verified": false,
  "request_inventory_complete": false,
  "retention_verified": false,
  "quiescent_snapshot_verified": false,
  "gateway_origin_verified": false,
  "usage_convention": "prompt-includes-cache;total=prompt+completion"
}
```

The false values deliberately block export. Set each true only after the named
check has independent evidence; a successful row or supplied schema is not that
evidence. In particular, VK-ID stability, row completeness, retention, retry
coverage and late writes were **not** established by Vivek's sample. Reviewers
must also verify the declared usage convention. The adapter hashes the supplied
review/selection; it cannot authenticate that a human assertion is true. No
physical Bifrost version is inferred from a filename or SQLite schema marker.

Every unique selected request ID must match the independently reviewed inventory
exactly. A reviewed empty inventory is a known zero-call session only after all
completion checks; a model price is still required. The SQL filter uses exact
binary comparisons for session, VK ID and VK name together. A request ID reused
across other attribution scopes is ambiguous. Identical full selected rows with
the same ID are deduplicated; conflicting versions are incomplete, not discarded.

Provide the **Agent** receipt with its matching raw `session` and optional
`cost_usd`, not the runner's UUID. After successful token pricing, a discrepancy
is flagged when `abs(receipt - computed) > computed * 0.01`. Exactly 1% is not
above threshold. Zero/zero agrees; zero computed and positive receipt disagrees.
Missing/invalid receipt cost means comparison unavailable, not agreement. A
mismatch never changes the authoritative token-derived cost.

## Acquisition, commands and output

Use an explicitly authorized, quiescent **standalone SQLite snapshot**, with no
WAL, SHM or rollback-journal sidecars. The reader checks reviewed quiescence before
opening with SQLite URI `mode=ro&immutable=1`, sets query-only/trusted-schema
connection controls, checks the `logs` table/columns, and verifies the database
byte hash before and after reads. Active/WAL databases are refused; immutable mode
is not a method for reading an active store. No checkpoint, migration, delete or
database write occurs. Never point it at a teammate's drive without authorization.

From the repository root, using reviewed local files and a new output directory:

```powershell
python -m bench.bifrost_export export --db "C:\benchmark-inputs\authorized-snapshot.db" --prices prices.yaml --selection "C:\benchmark-inputs\selection.json" --receipt "C:\benchmark-inputs\receipt.json" --output "C:\benchmark-evidence\machine-1-run-1"
```

The native YAML parser uses the application's existing **PyYAML** dependency only
for non-JSON YAML. It preserves decimal rates and rejects duplicate mappings.
JSON-syntax native price fixtures need only the standard library, so existing
minimal CI dependencies are sufficient for the core tests. Missing PyYAML for a
native YAML input is explicitly incomplete; nothing is installed automatically.
No rate is fabricated. The dormant normalized cache-write rate comes from the
known native 5m rate, but every exported write count is verified zero, so no TTL
charge is inferred.

Outputs are a new directory containing:

- `evidence.jsonl`: strict v1 reporter session/request rows, **only if complete**.
- `prices.yaml`: normalized JSON-compatible v1 rates for the exact actual model.
- `costs.jsonl`: authoritative costs and receipt comparisons, with evidence/price
  byte hashes in the existing `cost_provenance` shape. These are cost records,
  not full graded run-result rows; join grading/plan metadata before reporting.
- `diagnostics.json`: completeness issues, duplicate counts, raw-to-qualified ID
  mappings, request/parent/status data, source hashes, actual column metadata and
  reviewed selection evidence. It explicitly says physical version is unverified.
- `manifest.json`: hashes of the four output files. This is integrity metadata,
  not source authentication. Interrupted output without a valid manifest is unusable.

Incomplete output contains no reporter session or cost rows and no usable price
profile. CLI exit codes: 0 complete, 1 incomplete, 2 invalid invocation/output.
Terminal output is generic; raw usage JSON, prompts, keys and payloads are never
printed or copied into evidence. Source request IDs and model/status fields are
retained as required for auditing.

## Combining four machines

```powershell
python -m bench.bifrost_export combine --inputs "C:\evidence\machine-1" "C:\evidence\machine-2" "C:\evidence\machine-3" "C:\evidence\machine-4" --output "C:\evidence\combined"
```

Use individual complete bundles sharing the exact agreed native price-file hash
and data kind. IDs are reversible base64 encodings of `[gateway_instance_id,
raw_id]`, qualified by **logical gateway**, not exporting machine or snapshot.
This keeps independent gateway IDs distinct while copies from the same gateway
still collide. Review the origin binding: labels alone cannot prove independence.
The combiner verifies file hashes, rates, recomputed costs and global uniqueness;
overlapping run/session/request IDs or the same snapshot relabeled as another
origin are rejected. Incomplete bundles cannot disappear by filtering.
Combined evidence/price hashes replace the input bundle hashes in every cost
provenance record. Source diagnostics remain retained. Nothing is merged into a
Bifrost database and no benchmark report is published.

## Still needed before live attribution

Verify physical DDL/types/constraints and binary v2.5.1, capture an authorized
consistent snapshot, bind the bench VK and gateway origin, establish the input/
cache accounting convention, and independently inventory all requests through
session close and logging flush. The runner does not yet capture Bifrost request
IDs as an independent complete inventory. TTLs, retry/fallback billing, other
terminal statuses, retention and late/failure usage remain unverified. Tiered
pricing/report schema support is also pending. Current expected benchmark-model
costs cannot be declared complete merely because the narrow synthetic tests pass.
# Reviewed null served-model resolution (v5)

`bifrost-2.5.1-null-served-model-v1` is a per-request rule, not a blanket
substitution. Explicit non-null `served_model` retains the existing path. For a
null value the exporter additionally reads only the observed optional SQL
columns `alias`, `canonical_model_name`, `server_side_fallback_model`,
`routing_rule_id`, `fallback_index`, `number_of_retries`. Missing columns fail
closed for that row; no physical SQL type or additional response column is
invented. All four nullable fields must be present and null, and both counters
must be integer zero.

The selection JSON may supply `routing_evidence` with exactly `schema_version`
(integer 1), `source_sha256` (actual reviewed source artifact SHA-256) and
`requests` (map by the exact selected Bifrost request IDs). Each proof records
`request_id`, `session_id`, `virtual_key_name`, `provider`, `routing_info` and
`resolved_model_used`. The first four must match the selected database row;
the existing exact session/VK-ID/VK-name selection and independent completeness
review remain mandatory. `routing_info.provider` and `requested_provider` must
match the logged provider; its `requested_model` and `model`, the separate
`resolved_model_used`, and the logged `model` must be identical. Missing, mixed,
retried, aliased or mismatched evidence remains incomplete.

[The four native proofs](evidence/croc-native-routing-proof.json) demonstrate
this sidecar shape. When embedding it in one session selection, filter its
request map to that selection's exact IDs; proofs outside the reviewed
inventory reject. Response routing info is supplied by the reviewed sidecar,
not guessed as a `logs.db` column. A hash/reference is provenance metadata,
not independent authentication; a reviewer must actually check the joins.

Raw rows and `served_model: null` remain unchanged. Diagnostics add
`resolved_model`, `model_resolution` and `routing_evidence_source_sha256`.
The cost calculation still checks usage/cache categories, component precision,
exact official rates and the separate 1% discrepancy rule. No cache-write TTL,
unknown price, retry completion or missing usage becomes supported by this rule.
Historical v4 pilots stay incomplete and excluded from pooled results even when
some individual requests can now be resolved. See the v5 release for the
remaining post-restart/session-completeness requirement.
