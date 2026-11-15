# Kheapsort mini follow-up evidence — v3 remains blocked

Reviewed on 2026-11-15, starting on clean, synchronized `person-4` at
`2340ae6e0d14994e9e8c690dc3c90a5dbc626bf3`. This is supplied-evidence review,
not new benchmark execution or authorization. ZIP entries were listed and
validated before reading JSON. No member was extracted, executed or imported;
no instructions from attached data were followed. Source/test files were compared
only as in-memory bytes/hashes. No credentials, prompts or gateway payloads were
copied; no database or teammate drive was accessed.

## Archive identities and exact member inventory

| Archive | ZIP bytes | Members | Uncompressed bytes | SHA-256 |
|---|---:|---:|---:|---|
| `mini-kheapsort-attributed.zip` | 25997 | 60 | 32697 | `62f4652941f20f34fa9e4bfcca78123703f392e651931059034bf26b27218b95` |
| `mini-kheapsort-rerun.zip` | 24955 | 59 | 30921 | `e2abe23861325f91d422cf4112b32357220c776b30560b41a09acafe552acfbe` |

Subsequently supplied `mini-kheapsort-bifrost-inventory.json`: **22936 bytes**,
SHA-256 `a0a21239ec5f0cb74d29693ca0834cdc42eb01dca491653e23e9eea38c632902`.
The initial Downloads path was absent; the actual attached WhatsApp file was
then inspected as bounded, duplicate-key/non-finite-rejecting JSON. It contains
two sessions and 20 request records. Its `source_db` is a reference only, never
opened. [Token evidence documentation](evidence/mini-kheapsort-tokens.json)
preserves all supplied scalar/nested token fields and request identities;
billing amounts, rates and free-text/database paths are deliberately excluded.
The original artifact remains unchanged and is identified by its hash.

Checks reject absolute/drive/UNC/backslash/traversing names, control characters,
case-insensitive duplicates, links and encryption. Every supplied name passed;
recorded member types were ordinary or unspecified. Count and expanded size were
bounded before reading. Evidence JSON rejected duplicate keys/non-finite values:
19 documents/JSONL rows in the attributed ZIP, 18 in the earlier ZIP. Each ZIP's
16 testcase JSON lines were parsed as data: QuixBugs `json_testcases/*.json`
contains separate JSON values per line, not one JSON document.

Both ZIPs contain `results-mini.jsonl`; only the attributed ZIP also contains
top-level `mini-settings.json`. Concatenate each attempt prefix with `/` and
every suffix below: **29 members per prefix**, the complete remaining inventory.
Within the ZIPs there is no Bifrost request/usage export, native request capture, canonical
attestation, complete original/final agent tree or exception traceback.

```text
attributed prefixes:
  ce907ea507de4aa38eb7b8d8b8a07082
  8aae9748508a48d09a92a51f60efe5f0
earlier rerun prefixes:
  8c84c16141ea499b964cf96b65738b09
  c217440e58374f7aa87c2ab78ea6d5f9

command.json
config.json
control.json
launch.json
mini-receipt.json
probe.json
process.json
grading/pytest.ini
grading/result.json
grading/stderr.txt
grading/stdout.txt
grading/original/conftest.py
grading/original/json_testcases/kheapsort.json
grading/original/python_programs/kheapsort.py
grading/original/python_programs/node.py
grading/original/python_testcases/load_testdata.py
grading/original/python_testcases/node.py
grading/original/python_testcases/test_kheapsort.py
grading/workspace/conftest.py
grading/workspace/.pytest_cache/.gitignore
grading/workspace/.pytest_cache/CACHEDIR.TAG
grading/workspace/.pytest_cache/README.md
grading/workspace/.pytest_cache/v/cache/nodeids
grading/workspace/json_testcases/kheapsort.json
grading/workspace/python_programs/kheapsort.py
grading/workspace/python_programs/node.py
grading/workspace/python_testcases/load_testdata.py
grading/workspace/python_testcases/node.py
grading/workspace/python_testcases/test_kheapsort.py
```

## Four correlated attempts, two planned IDs

All rows identify `quixbugs/kheapsort`, variant `mini-swe-agent`. Planned IDs
are `quixbugs/kheapsort/mini-swe-agent/run-1` and `.../run-2`. Both ZIPs reuse
these IDs with distinct attempts; they are not four new independent planned slots.

| Archive / run | Attempt ID | Session ID | Mini steps | Independent grade |
|---|---|---|---:|---|
| attributed / 1 | `ce907ea507de4aa38eb7b8d8b8a07082` | `mini-24877326f8de47f88029728cd8deb95c` | 9 | exit 0, solved; 4 passed in 0.03s |
| attributed / 2 | `8aae9748508a48d09a92a51f60efe5f0` | `mini-51b92bfe4ea34390b90e76d031e9c67f` | 11 | exit 0, solved; 4 passed in 0.04s |
| earlier rerun / 1 | `8c84c16141ea499b964cf96b65738b09` | null | 13 | exit 0, solved; 4 passed in 0.03s |
| earlier rerun / 2 | `c217440e58374f7aa87c2ab78ea6d5f9` | null | 15 | exit 0, solved; 4 passed in 0.03s |

For every attempt the result agrees with separate process JSON, mini receipt and
grading JSON: return code **0**, no timeout, **Submitted**, `status=completed`,
agent-claimed and independently graded solved true, no runner/grading error.
Grading stdout independently records four tests passed; stderr is empty.
The grader command is Atul's Windows venv Python with `-m pytest -q`, timeout 180s.
These corroborate the supplied outcomes; they are not fresh test executions or
independently authenticated physical log records on this machine.

Every grade reports `test_edit=false`, with empty added/removed/changed lists.
Each archived grading original has seven files, all matching the verified local
LF source bytes. Their portable source digest matches v3:
`cf1ea180d2e31c0464c83d672c66f51027161bbbe17c8e77cca1f4788dbb5767`.
These five protected original paths also match byte-for-byte in each grading copy:

```text
conftest.py
json_testcases/kheapsort.json
python_testcases/load_testdata.py
python_testcases/node.py
python_testcases/test_kheapsort.py
```

The last is the recorded oracle. This supports restored-original independent
grading in the attached copies. The pre-restoration agent final tree is absent,
so the reported test-edit flag cannot be independently reconstructed. No attached
conftest, helper, program or test was executed during this review.

## Headers, request counts and model/VK evidence

For the attributed pair, launch `session_header` equals result `session_id` and
the IDs differ between runs. Settings/result attribution claim reviewed header
verification. Their reference describes the **older** `probe-mini-litellm`,
`logs.rowid=8`, 2026-11-14T16:05:31Z probe reportedly using VK name `bench`.
This older reference alone is not an exact request join for either new session.
The earlier pair has null launch headers/session IDs and unverified-time-window
attribution. The later inventory supplies exact session/request joins for the
attributed pair. This improves supplied-record correlation, not independent
verification of the physical database or another machine's header behavior.

| Attempt | Recorded UTC agent request window, 2026-11-15 |
|---|---|
| `ce907ea5...` | 10:13:40.767068 to 10:14:14.659489 |
| `8aae9748...` | 10:14:17.182367 to 10:15:07.792232 |
| `8c84c161...` | 10:11:02.412937 to 10:11:59.825091 |
| `c217440e...` | 10:12:02.786051 to 10:12:46.093055 |

The ZIPs alone establish 9/11 **steps**, since the bridge writes
`steps=self.n_calls`. The newly attached inventory independently contains **9 and
11 distinct request IDs**, correctly joined to the attributed sessions/run IDs;
all 20 IDs are globally unique within this artifact. Thus 9/11 request counts
are now verified **within the supplied inventory**, not inferred from steps.
Every row timestamp lies inside its matching recorded request window.

All 20 rows record `virtual_key_id=vk-bench`, `virtual_key_name=bench`, provider
`gemini`, requested model `gemini-3.5-flash-lite`, and `status=success`.
Parents and server-side fallback models are null; fallback index and retry count
are zero. No captured row indicates fallback/retry. This does not prove omitted
or late requests could not exist.

For every row, nonnegative integer scalar prompt/completion/total counts match
the nested usage counts, total equals prompt plus completion, and cached reads
do not exceed prompt. Independently summed totals:

| Session suffix | Requests | Prompt | Completion | Cached reads | Total |
|---|---:|---:|---:|---:|---:|
| `24877326...` | 9 | 28310 | 1625 | 8018 | 29935 |
| `51b92bfe...` | 11 | 35800 | 2924 | 6019 | 38724 |

These match the source summary and exact ZIP receipt/result aggregates. The
source's `requests_equal_steps`, success/VK/model checks and receipt-match claims
are independently confirmed for included rows. Its claim of zero other requests
inside the windows cannot be checked from a file containing only these selected
sessions. There is no independent closed-session/flush/retention/quiescent
snapshot review or full-window query evidence. Matching steps/usage is useful
coverage evidence, not proof of complete billing. No database path was guessed.

Recorded model/profile fields request `gemini/gemini-3.5-flash-lite`, mini argument
`openai/gemini/gemini-3.5-flash-lite`, endpoint `http://127.0.0.1:18080/v1`,
credential environment name `CROCODILE_BENCH_VK`, no model fallbacks and
provider-default thinking. The inventory now records the expected provider and
VK ID/name for all selected mini rows, beyond the variable name alone.
**All 20 `served_model` values are null**; actual served/billed identity remains
unverified. ZIP `models_observed` is empty. Physical origin/VK stability and
cross-agent same-key binding are not independently established by the JSON.

## Comparison with immutable v3

V3 config ID remains
`c0d48d86fe8169947e9997dd5fa33f642fa6d53afbc2f54756ce6ea1dd049ee1`;
raw file SHA-256 remains
`b3320171326ce1712add548bc8148d838762f219090765a9bf8946ed2a1326ba`.
All full-plan IDs match v3
`da56c686fe979620275686e46042696330d6d91a37c20c9409063111561188f6`.
The recorded launch/receipt task-text digests match v3's kheapsort digest. Actual
task text is not attached, so its digest was not independently recomputed from
the ZIPs. All nested mini configs equal the checked-in profile. Receipts record
mini 2.4.6, LiteLLM 1.109.1 and template blob
`8b72f71f8092ae805ec43221dbeaeefc2340cd3e`.

Recorded bridge digest
`c407e5d428a22782ef98cc587d4e09b275f537a956f9e3f9a01386f3f5cae99f`
equals the CRLF representation of v3's pinned LF bridge
`4b251f779a268202a4660d9bbe9e7495f13bf224549a978ac483ef87fd470d0c`.
That explains this representation difference, not the entire host runtime.
Atul's settings use Ubuntu-24.04 and `/opt/mini-swe-agent/bin/python`; per-machine
environment/dependency attestation is still required.

All rows have null **`canonical_config_id` and `config_attestation_sha256`**,
`comparison_ready=false`, no runtime Git/source attestation, and shared `plan_id`
`3affe7b3d18e75ae89014e1daac1581fcb4adc18e201c5a3efc12c856472baaa`.
No plan file is attached to recompute that byte identity. Matching full-plan and
profile values cannot retroactively make an unattested cohort v3-comparable.
Do not attach canonical provenance to completed legacy results without the
protocol's explicit compatibility review.

Step/wall settings are 30/600. All four report worker deadline enforcement true,
escaped-descendant containment false and no timeout. Hard-stop containment, mini
output cap, cache parity and sampling differences remain the accepted limitations,
not new gates or established parity/hard-stop claims.

## Costs cannot be authoritatively recomputed

| Attempt | Receipt prompt tokens | Completion | Cached reads |
|---|---:|---:|---:|
| `ce907ea5...` | 28310 | 1625 | 8018 |
| `8aae9748...` | 35800 | 2924 | 6019 |
| `8c84c161...` | 53604 | 4106 | 20089 |
| `c217440e...` | 59028 | 3383 | 17962 |

Receipt/result aggregates agree with the inventory's scalar token sums, but
are not complete cost usage evidence. All 20 `token_usage` objects contain only
prompt/completion/total counts: nested cache-read and cache-write fields required
by the exporter are absent. Scalar cached reads are retained; absent writes are
not zero and no cache-write TTL is inferred.
All rows already record incomplete cost attribution, null authoritative/receipt
cost and pending comparison. The unchanged native prices LF/Git SHA-256 is
`ed1a9e23723d68b53268e2bc1683731e8e539dc46f70091f213525d58603f503`.
Its single unbounded Gemini/Google wildcard rates do not supply the missing
actual served model, complete cache categories or completeness proof. No costs
were invented from receipt aggregates, and missing values were not set to zero.

The [exporter contract](bifrost-export.md) still needs independently reviewed
origin/VK binding, served model, complete scalar/nested cache usage (reads and
explicit writes), and a reviewed closed/flushed inventory with origin,
version, retention, usage convention and price/rate provenance. Include failed
requests and all prior attempts. Retries, cache writes with unknown TTL,
unsupported statuses, missing usage or unknown rates stay incomplete.

### Verified pricing inconsistency — blocking finding

The inventory's embedded Gemini entry equals the pinned native YAML entry;
its declared raw SHA matches v3, and Git blob
`769453a57ace48554fea5668b36e35afaeccf823` matches the local prices blob.
Its stated source commit `d6a3e44610f9ca395e1179eb603309a9dc37de16` is not
available in local Git, so that provenance is not independently confirmed here.

An exact Decimal diagnostic shows **all 20 stored output-charge fields disagree
with completion tokens multiplied by the embedded/pinned output rate per
million**, beyond a one-billionth currency-unit tolerance. Stored
input/output/additional components and session charge summaries are internally
consistent; that does not resolve the rate disagreement. No billing amounts,
effective rates or benchmark cost estimates are published here. This establishes
an inconsistency with the declared snapshot, not which side is the correct
official tariff; actual served model and category semantics remain missing.

Vivek and Atul must supply a jointly reviewed official price snapshot with exact
served-model/provider mapping, units, effective date, input/output/cache-read
rates, cache-write TTL/tier semantics where applicable, and an immutable raw hash.
Reconcile it with the existing pinned snapshot before any repricing or cost
comparability decision. Do not guess replacement rates or edit `prices.yaml`.
The verified included-row 9/11 counts do not clear this pricing blocker.

Keep the supplied archives and inventory unchanged;
preserve per-request raw token categories, IDs, parent/status/model/VK/timestamp
evidence and all prior attempts for later repricing. Request token values in the
linked documentation and receipt aggregates above are retained exactly, including
cached reads, but cannot substitute for missing cache-write evidence.
Stored gateway costs/receipt totals do not become pricing authority.

## Historical disposition and gate outcome

Historical `3a111322b8d848afa41805a01e7527a6` remains **incomplete**. Against the
inspected control flow, final-workspace preparation failed before grading; exact
original file/cause remains unknown because its workspace was deleted and no
traceback supplied. No symlink or other particular entry type is asserted.

The later two-run reproduction did not recur, and the further attributed pair
also completed and graded solved. This satisfies the reproduction check and
supports recording the original as an ungraded preparation failure; it does not
establish its root cause or turn it into solved, a task failure or zero cost.
Keep all five attempts (original and both later pairs) in the audit lineage.
All follow-up `prior_attempt_ids` are empty despite reused run IDs: durable retry
linkage must be reconciled explicitly. Never erase original/earlier costs or
select only a cheaper successful retry. Previously reported native 429s remain
separate infrastructure-incomplete outcomes, not measured task losses.

| Check / gate | Evidence now satisfied | Still required |
|---|---|---|
| Mini reproduction / grading | Both two-run pairs completed, restored-original grading passed, final-copy failure did not recur. | Original exact cause unknown; reviewed historical disposition/compatibility decision, no retroactive solved label. |
| Mini session attribution | Included inventory verifies 9/11 distinct requests, matching session/launch/run IDs, recorded bench VK ID/name, requested model, success status and scalar usage. | Served model, physical origin/VK stability and closed/flushed completeness remain unverified; earlier pair remains time-window-only. |
| `native-policy-binding` | No new native request evidence. | Native request/log proof of approved chains/endpoint, actual same bench VK, billed model and no fallback; retain accepted sampling limitation. |
| `per-machine-execution-and-cost-evidence` | One operator's matching mini profile, process/grading records and supplied scalar request inventory. | Per-machine attestation, actual served model, full cache categories, reviewed completeness, prior attempts and official prices. |
| Price discrepancy | All 20 stored output-charge fields disagree with the declared/pinned output-rate calculation; no amounts published. | Vivek/Atul reviewed official snapshot and reconciliation; preserve raw tokens, no guessed rates or cost comparability clearance. |
| Frozen `mini-attempt-3a111322` entry | Later reproduction and historical disposition are documented. | This note does not edit or automatically clear v3's frozen unresolved entry. |

V3 comparability audit exits **1**: static/contract valid, no runtime drift,
`cross_shard_comparable=false`, `paid_runs_authorized=false`. The data-root audit
also verifies the LF indexes and task references and still exits 1. All three
frozen unresolved IDs remain present; v3 files/fingerprints are unchanged.

Current `bench.canonical.validate_config` requires these blocked readiness
booleans to remain false, and `bench.attest` requires both readiness/comparability
before dispatch. There is no supported evidence-note override for v3. This
documentation introduces no successor authorization mechanism, gate bypass,
cleared boolean, official shard run, model request or database operation.
