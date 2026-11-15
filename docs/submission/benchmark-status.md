# Benchmark status: incomplete, not zero

As of 2026-11-15, v4's real inputs and plans validate, but comparable measured
results remain incomplete. [bench/report.md](../../bench/report.md) and
[report.json](../../bench/report.json) remain the unchanged incomplete reporting
artifacts; their absent measurements are not replaced by planning metadata.
The approved price snapshot is now pinned, but a complete attributable measured
run grid is still missing.

| Item | Evidence / status |
|---|---|
| Canonical config | [gemini-benchmark-v4.json](../../bench/configs/gemini-benchmark-v4.json), immutable |
| Config fingerprint | `026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4` |
| Runtime checkpoint | `deaf328ab72c5149ba8e67a511a606b912aa4b1e` |
| Price SHA-256 | `8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e` |
| Input counts | 34 Polyglot + 20 QuixBugs = 54 validated tasks, not task solves |
| Planned slots | 270: two Crocodile, two mini, one all-off per task |
| Shards | Tasks 1–14, 15–28, 29–41, 42–54; 70 / 70 / 65 / 65 slots |
| Smoke | Prepared 3 tasks / 15 slots; not executed as a comparable cohort |
| Strict config/manifests | Exit 0; five manifests valid; no runtime/price drift |
| Comparability | `--require-comparable` exit 1; paid authorization false |
| Comparable pass rates / CPST / savings / ratios | **Incomplete; no measured value published** |

Exact input hashes, pinned dataset commits, external bundle paths and commands
are in [team-handoff-v4.md](../../bench/team-handoff-v4.md). The existing external
bundle contains `full.json`, `shard-1.json` through `shard-4.json`, `smoke.json`,
their oracle subsets/attestations, `mini-settings.json`, `prices.yaml` and
`price-snapshot.json`. A clean attestation records its own historical commit;
do not rewrite it to pretend it records this documentation commit.

## Evidence required before live smoke

1. **Atul / reviewer / Person 4:** explicit disposition of historical attempt
   `3a111322` and rerun-cohort compatibility/retry/cost lineage. Original final
   preparation failed before grading; exact original file/cause is unknown.
   Later successful reproductions do not retroactively solve it or erase cost.
2. **Atul / Vivek:** sanitized actual native request/log correlation proving
   stable bench VK identity, endpoint 18080, Flash-Lite billed model and no
   fallback. Settings/source intent alone do not establish effective routing.
3. **Vivek / operators:** actual served-model/routing evidence and independently
   reviewed closed, flushed, retained, quiescent complete session inventories,
   gateway origin/version, exact request/session/VK joins and token conventions.
   Current 20-request evidence still has null served-model identities; selected
   rows alone cannot prove session completeness.
4. **Operators / Person 4 / reviewer:** secure per-machine configuration/header
   evidence, valid owner-enrolled sealed state, and a supported reviewed
   authorization revision/mechanism. Do not flip immutable v4 ready flags.

The [v4 request audit](../../bench/evidence/mini-kheapsort-v4-audit.json) records
usage consistency and conditional price comparisons for the supplied rows. It
does not establish a publishable complete cost. Raw token evidence and older
inventories are retained for later attribution/repricing; no dollar total is
published in this pack. Quota responses, setup errors and interruptions remain
incomplete attempts, not solved-task failures or measured zeros.

No paid calls, official shard, full benchmark, benchmark savings or CPST result
is authorized or claimed by these submission materials.
