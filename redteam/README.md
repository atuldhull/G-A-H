# Reviewed red-team integrations

The inventory covers architecture/10 section 3's **15 groups / 20 case IDs**.
Ritika's [review.md](review.md) is **reviewed with corrections**, dated
2026-11-14, packet `d67ae28df0b066e8a9ffbced0adcca65fe65e0b4`.
Its Git blob `b608b52f3be1e7ec8590eabed755d69696bb3d2e` is identical on
main `b92ae4df22651e839f18f465239df5a87e170345`, current person-4, and fetched
person-3 `0605903036282d73c8953ecbedcdabdb89008a2e`. Main is already an ancestor
of this checkout. No person-3 branch was merged directly; later person-3-only
implementation changes are not assumed present.

## Execution and honest counts

```text
python -m redteam.inventory
python -m pytest -v -ra -p no:cacheprovider redteam/tests/test_security_cases.py
python -m pytest -q -ra -p no:cacheprovider redteam/tests/test_framework.py
python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache redteam
```

The first integration enables **groups 7, 8, 13** using actual owner functions
and temporary synthetic repositories/state. They make no model calls or network
requests and launch no child processes. A fourth passing test is supplemental
approval-layer coverage of renewed red consent; it is **not group 3 completion**.
The other **12 groups remain skipped**, with exact owner/adapter blockers in
`inventory.BLOCKERS` and pytest skip output. Never report skipped groups as
security passes or combine framework counts with the 15-group verdict.

`python -m redteam.inventory` only emits planning metadata. Source presence stays
`source-present-unverified`; explicitly connected cases say
`adapter-enabled-not-executed`, never PASS. Only a real pytest execution provides
a verdict. An enabled assertion failure fails CI; it is not skipped or xfailed.
Removing an unsupported skip still produces a failure rather than an empty pass.

## Connected surfaces and evidence

| Group | Reviewed assertions and actual APIs |
|---|---|
| 7: `px3_marker_deleted`, `px3_repo_flag`, `px3_nested` | Real `Detector(SecurityStore)` plus sealed disposable SQLite state. `.crocodile/confidential` removal retains classification in the same session and a restarted detector sharing its registry. An independent marker-free root starts public and `detect(..., force_confidential=True)` changes classification. A third fresh public root detects the nested marker and refuses `Detector.guard` and actual `tools.dispatch('read', ...)`, without private bytes. No invented root CLI repo-mode flag. |
| 8: `rt_readme_curl` | Index original README lines with `Source('file', 'README.md', 1)`; line 40 supplies the real network sink. `approvals.ask` denies both a network action and an executable-pinned Python network script carrying that sink, with `decision.steered_by` containing `README.md:40`. Console calls are forbidden. `cmd.run` rejects the refused command; process/socket counters remain zero. No sh/curl availability dependency or attack execution. |
| 13: `sec_rg_env` | Actual `tools.dispatch` through `tools.fs.search/read`, `SecurityContext.observe` and output gate. Search restricted to the non-ignored synthetic `.env` returns `no matches` without requiring a marker; direct read returns a sensitive-file placeholder. Separately an ordinary file contains a recognized synthetic credential, so its result must contain a redaction marker. Model/terminal-facing strings, provenance, real `ReadCache`, and disk-backed `Spill` contain no full synthetic credential. |

The supplemental group-3 approval test grants and consumes prior test consent,
approves/applies the inert execution-changing replacement, calls
`ApprovalSession.record_edit`, then refuses the renewed **red typed** consent
whose preview says `will execute edited code`. The real command API refuses it;
no pytest or calc process is started. It deliberately does not run the baseline
or assert the unresolved Agent/CLI refusal receipt, so group 3 stays skipped.

Every connected adapter installs failing `subprocess.Popen/run`, shell and socket
observers **before fixture/session creation**. Denial/routing/redaction behavior
is not mocked. State is enrolled once using real `StateIntegrity.initialize` and
an injected in-memory fixture vault; no OS credential backend, live ledger,
gateway journal or personal state is accessed. The empty ledger/grants schema
follows the owner phase-6 fixture seam and does not prove group-4 ledger tampering.
All production imports used here work with Python `-S` (stdlib only); pytest is
the only test dependency. The existing Windows/Ubuntu CI commands already collect
these tests; their historical "blocked" step name does not mean all entries skip.

## Review corrections across all 15 groups

| Group | Applied expectation / remaining blocker |
|---|---|
| 1 | Root quote CLI, not just static quote function. CLI/canary/zero-transport adapter still unconnected. |
| 2 | Deny initial baseline consent as well as later consent when asserting zero pytest spawns. Agent/write/receipt adapter pending. |
| 3 | Renewed test consent is **red**, not amber, after execution-changing applied edits. Full harmless baseline/post-edit refusal receipt adapter pending; supplemental coverage above is separate. |
| 4 | Genuine protected `ledger`/`meta`/`grants`/classification state, one-time HMAC enrollment, abort/revocation/no-next-action proof required. Fixture JSON/SQL remains a placeholder; live mutation adapter pending. |
| 5 | Local-chain validation before send plus separate root doctor FAIL. Both transport/doctor assertions pending. |
| 6 | Marker is `.crocodile/confidential`. Forced confidential `web_docs` must be refused; require zero Tavily sends/rows and full local-only session evidence, not a nonexistent fixed `web DENY` event. Egress adapter pending. |
| 7 | Correct root/nested markers, fresh registries for independent subcases, sticky registry preserved for marker deletion. Explicit mode uses Detector API; connected. |
| 8 | README-steered network actions **deny before prompting** with exact line provenance; connected. A separate non-network red-preview assertion is not substituted for this rule. |
| 9 | ASK only for available pinned interpreters and valid proposals; escaped bounded previews are valid. Both cmd/bash adapters pending. A pre-validation denial is safe but not proof of ASK. |
| 10 | Preplanted fsmonitor causes GitDenied/config-change evidence; watched post-child filter changes cause immediate integrity abort. Separate genuine Git fixtures and observers pending; no forced later banner after abort. |
| 11 | `with Git(sec) as git: git.run('show', rev='--output=.git/config')`, not template `'git show'`. Setup traces separate from invalid operation; adapter pending. |
| 12 | Writes through `resolve_in_repo(..., for_write=True)`; genuine junction and actual 8.3 protected alias. Windows privileges/alias support and all-path adapter pending, never string-only PASS. |
| 13 | `.env*` exclusion need not emit a redaction marker; ordinary recognized credentials must redact before output/cache/spill. Connected. |
| 14 | Refuse red oracle write and preserve tests; actual all-skipped `TestReport.passed` must be empty and Receipt must not be green/verified solved. Paired adapter pending. |
| 15 | Bounded missing-console/backend fixture, not fake `n` alone; no stdin-derived grant or changed target. Root run adapter pending. |

## Safe fixture construction

`build_fixture(case_id, destination) -> Fixture` accepts any architecture ID.
Destination must be new/local with an existing non-linked parent. Construction
only writes inert ordinary UTF-8 files and JSON; it never imports exercise code,
executes attack text, opens sockets, or constructs real links/device paths.
Use a disposable temporary root, never an existing repository or live state.
`example.invalid` URLs and explicitly synthetic credentials are test data only.

Windows junction/ADS/device/8.3 spellings remain JSON until a future reviewed live
adapter proves its setup. Fake `.git/config` and ledger JSON are not real Git or
HMAC state. Each multi-ID group earns a group pass only after every required
subcase executes and passes. Fixture construction tests are separate framework
checks, regardless of how many pass.
