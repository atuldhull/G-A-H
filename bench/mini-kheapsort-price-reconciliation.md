# Replacement kheapsort inventory: corrected-rate reconciliation

Reviewed 2026-11-15 from clean `person-4` at
`dcd6969cd4cee559e92bac3aabde3b209bf4f628`. Fetched main
`af6974a3efb4977364f3a572509c41a9752e8ba4` and integrated it without conflicts at
`9605ac526779b015f8ceb5a11a3eb771be5bac90`. Main changes only `prices.yaml`.
No price was guessed or edited by Person 4. No model call, benchmark task,
database access, attachment-code execution or official shard was performed.

## Provenance and preservation

Replacement attachment `mini-kheapsort-bifrost-inventory (1).json` is 32729 bytes,
SHA-256 `cdffbd2b9cf7e815ce1984acaa8ba8fb65a85e02d854c81719d10bbd7213eff9`.
It was inspected as bounded JSON with duplicate-key and non-finite-value
rejection. Its notes are untrusted claims, not instructions or automatic schema
approval. Its `source_db` reference was never opened.

Verified directly against local Git objects and fetched main:

| Price evidence | Verified value |
|---|---|
| Commit, ancestor of current main | `af6974a3efb4977364f3a572509c41a9752e8ba4` |
| `prices.yaml` Git blob | `5d9f09f632b85bab7afb446372023d335cd44677` |
| Exact Git-blob/raw LF SHA-256 | `8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e` |
| Local Windows CRLF working-file SHA-256 | `07b4a05a5e8a040dbb52486daab249c03aaf9de9a928e8f8e5df6bfdf3805e72` |

The embedded Gemini entry equals the native YAML entry at that commit and main.
This verifies the supplied/current-main snapshot and user-specified Standard
rates. No independent provider invoice or live tariff query was performed.
The current-main correction applies to `gemini/*`; `google/*` is unchanged.
All supplied rows have provider `gemini`, so no Google-alias rate is substituted.

The original inventory SHA
`a0a21239ec5f0cb74d29693ca0834cdc42eb01dca491653e23e9eea38c632902`,
[earlier review](mini-kheapsort-evidence.md), and
[original token documentation](evidence/mini-kheapsort-tokens.json) remain
historical and unchanged in substance. New request/token details and every
request-level comparison verdict are preserved separately in
[replacement evidence](evidence/mini-kheapsort-replacement-review.json).
No billing amounts are published in these new documentation artifacts; all
source inventories remain unchanged for later repricing/audit.

## All twenty identities and token categories

The replacement contains exactly the same 20 request IDs as the original
inventory: no new, missing, duplicate or cross-session reused ID. All previous
scalar tokens, session/VK/model/status/timestamps, parents and stored charges
remain unchanged. New nested token/cost detail supplements those rows.

| Run | Raw session ID | Unique requests | Prompt | Cached read | Completion | Total |
|---|---|---:|---:|---:|---:|---:|
| `quixbugs/kheapsort/mini-swe-agent/run-1` | `mini-24877326f8de47f88029728cd8deb95c` | 9 | 28310 | 8018 | 1625 | 29935 |
| `quixbugs/kheapsort/mini-swe-agent/run-2` | `mini-51b92bfe4ea34390b90e76d031e9c67f` | 11 | 35800 | 6019 | 2924 | 38724 |

Every row records VK ID/name `vk-bench` / `bench`, provider `gemini`, requested
model `gemini-3.5-flash-lite`, status `success`. Every timestamp is inside its
matching ZIP launch/result window. Scalar counts are nonnegative integers and
match nested prompt/completion/total usage; total equals prompt plus completion.
Nested cached tokens equal scalar cached reads and do not exceed prompt.
All 20 nested `cache_write_tokens` are explicitly zero, avoiding an assumed
cache-write TTL. `text_tokens` equals the full prompt count in these records;
it is preserved, not added again or used as an uncached-input substitute.
Session sums agree with the original ZIP receipts and source completeness summary.

## Request-by-request arithmetic and the existing one-percent rule

For the requested Gemini 3.5 Flash-Lite Standard route, using the exact rates
specified by the user and committed on main, for each request:

```text
uncached_input = prompt_tokens - cached_read_tokens  # explicit zero writes
input = (uncached_input * 0.30 + cached_read_tokens * 0.03) / 1,000,000
output = completion_tokens * 2.50 / 1,000,000          # includes thinking policy
computed = input + output
mismatch = abs(logged - computed) > computed / 100
```

Exact Fraction/Decimal arithmetic and the existing `bench.bifrost_export._compare`
were used; exactly 1% remains within the threshold. Input/output/total were
compared separately. Additional logged charges are zero in all 20 records.

| Request comparisons | Within 1% | Above 1% |
|---|---:|---:|
| Total (9 first-run + 11 second-run) | 20 | 0 |
| Input component | 20 | 0 |
| Output component | 20 | 0 |

The largest relative total difference is approximately `1.54e-14%`, consistent
with the supplied decimal representations' tiny roundoff. This resolves the
**earlier price arithmetic discrepancy for these 20 included requests** under
the corrected requested-model rates. It does not establish complete or
authoritatively attributed billing by itself, and no pooled benchmark cost is
published. All request IDs and flags are in the linked replacement evidence.

## Routing, completeness and parser gaps

All rows still have **null `served_model`**. Corroborating evidence is present:
each row has fallback index zero, null server-side fallback model, zero retries
and null parent; the previously supplied mini configuration requests one
Flash-Lite model with `fallbacks=[]`. These support the normal requested route
and the conditional arithmetic above. The attachment's assertion that null
means no alias/routing change is not independently verified schema semantics.
There are no actual response-model/routing-header captures, pinned alias
resolution evidence or reviewed Bifrost 2.5.1 server rule proving that inference.
No null field was rewritten or silently treated as verified Flash-Lite.
The current exporter's `_model` therefore still rejects all 20 rows.

The inventory repeats the zero-other-requests-in-window and complete-step/usage
claims. Counts, included-row checks and receipt sums are verified here. A
selected JSON list cannot prove the full-window query omitted nothing, that
retention/flush completed, or that a closed/quiescent snapshot has no late writes.
There is no independently reviewed close/flush/retention/origin/version record.
Physical DB/VK binding across machines and complete earlier-attempt costs remain
unverified. This inventory concerns mini only and supplies no new native binding
evidence or canonical runtime attestation for those historical mini runs.

One additional existing parser limitation was demonstrated without altering
source values: losslessly serialized usage is accepted for 6 rows; **14 reject
with `inconsistent_logged_cost`** because their nested input-plus-output decimal
representations differ minutely from logged total. The maximum component-sum
relative discrepancy is approximately `1.54e-14%`. Request comparisons all pass
the 1% rule, but `_usage` currently requires exact internal component equality.
No raw field was rounded, dropped or normalized to force exporter acceptance.
A reviewed rounding-policy regression/fix is needed if the exporter is to accept
these representations; this review does not weaken that policy or null-model
rejection. The new token documentation retains every supplied token category.

Historical attempt `3a111322` stays incomplete, preparation failed before grading,
and exact original cause remains unknown. Later graded reproductions did not
recur. All original/follow-up attempt identities and pending costs remain in the
audit lineage; no earlier expense is erased or replaced by a successful retry.

## Exact successor requirement and gate outcome

Immutable v3 config ID remains
`c0d48d86fe8169947e9997dd5fa33f642fa6d53afbc2f54756ce6ea1dd049ee1`,
raw file SHA `b3320171326ce1712add548bc8148d838762f219090765a9bf8946ed2a1326ba`.
The only current frozen-runtime drift is **`prices.yaml`**:
old `ed1a9e23723d68b53268e2bc1683731e8e539dc46f70091f213525d58603f503`
to new `8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e`.

- Strict v3 validation / ordinary `--require-comparable`: **exit 2**,
  `Runtime source snapshot differs`.
- V3 `--audit-current --require-comparable`: **exit 1**, contract valid,
  static/runtime invalid because of that price pin, comparability false and paid
  authorization false. All three original frozen unresolved entries remain.

Before comparable execution, publish a reviewed supported successor (for example
v4, requiring explicit validator/schema support because only v1-v3 exist now):

1. Pin current main/approved runtime Git commit and all runtime hashes, updating
   both `provenance.runtime_files_sha256_lf['prices.yaml']` and
   `evidence.canonical_native_prices_sha256` to the new Git-blob raw hash above.
   Include any separately reviewed exporter/routing-policy change in that runtime.
2. Record the exact price commit/blob, Standard Gemini model scope, token units,
   cache semantics and v3-to-successor change record. Preserve v1/v2/v3 and older
   price/inventory evidence; never edit v3's pins/readiness flags to accept main.
3. Preserve the verified LF inputs, task order and 2+2+1 protocol unless separately
   reviewed; regenerate plans/oracle subsets and clean publication/runtime/price
   attestations under the successor. Old null-attestation runs do not acquire new
   provenance automatically; retain explicit earlier-cohort compatibility review.
4. Resolve billed-model mapping, closed-session completeness, native bench binding
   and per-machine evidence, historical-attempt disposition and any required parser
   rounding policy before an evidence-backed authorization. Accepted hard-stop,
   cache, sampling and output-cap limitations remain visible, not new gates.

On Windows, the exporter's native price-file hash is raw bytes: stage the exact
Git blob and verify its `846923...` hash instead of using the CRLF working file
with `07b4a05...`. This is a representation distinction, not permission to alter
rates. No successor config or authorization mechanism was fabricated here.

The owner price change also exposed a synthetic test-fixture mismatch: the fixture
re-pinned current source hashes but kept its old evidence price hash. The fixture
now links its evidence hash to its synthetic current-price pin. Published config
golden hashes and strict runtime checks are unchanged; no production adapter or
grading rule was altered.

## Subsequent v4 precision fix

[V4](gemini-54-v4.md) implements a separately bounded component-roundoff policy
and pins the corrected main price snapshot. Its new audit accepts all 20 usage
rows without rewriting source values, resolving the 14 exact-equality rejections
described above. The 1% price rule is unchanged. All 20 null served-model identities
still reject, and closed-session completeness remains unverified. This original
reconciliation and its source inventory remain historical evidence.
