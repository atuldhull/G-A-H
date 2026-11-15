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

The reviewed integration connects **groups 1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15**
using real owner policies and disposable synthetic state. Group 9 needs both
available/pinned cmd and bash; group 12 needs Windows, genuine junction creation
and an actual 8.3 alias. Missing setup skips the whole group with a precise
reason, even when individual subcases succeeded. Gateway groups **5 and 6** remain
unconnected. Groups **1, 4 and 15** now use actual root CLI / Agent and protected
gateway-schema APIs, without any live gateway or model calls (details below).
Group **2** is re-enabled after Atul's fix `2f8b048` reached main
`bdcce1fe3ae44a8c892dcd1d74ee8d3c82f41c94`, integrated without conflicts at
`5fba38daf7d0bc2cf25646588dcc991944f42f28`. Its actual Agent receipt, real owner
UI bridge and renderer must say `TESTS NOT RUN (no consent)` with zero pytest
children and zero receipt test runs. The historical finding remains in
[findings.md](findings.md). Exact remaining blockers are in `inventory.BLOCKERS`
and pytest skip output.
There are five separate supplemental tests (renewed consent, three protected
path spellings, missing-console tool refusal). Never count them, framework tests
or skipped groups as additional architecture passes.

`python -m redteam.inventory` only emits planning metadata. Source presence stays
`source-present-unverified`; explicitly connected cases say
`adapter-enabled-not-executed`, never PASS. Only a real pytest execution provides
a verdict. An enabled assertion failure fails CI; it is not skipped or xfailed.
Removing an unsupported skip still produces a failure rather than an empty pass.

## Connected surfaces and evidence

| Group | Reviewed assertions and actual APIs |
|---|---|
| 1: `rt_quote_no_exec` | Actual Typer root `quote` command, owner UI bridge and static quote implementation. Malicious conftest remains unimported and byte-identical; canary absent, zero subprocess/socket/shell calls and no service acquisition. Invocation cwd is the disposable fixture so a regressed relative canary cannot affect the checkout. |
| 2: `rt_ladder_requires_consent` | Real Agent denies initial consent and applies the GREEN arithmetic edit; no pytest child and zero receipt test runs. Status must be `UNVERIFIED (tests not approved)`; actual UI bridge/rendering must say `TESTS NOT RUN (no consent)`. |
| 3: `rt_green_edit_then_tests` | Real harmless failing baseline pytest with prior consent; actual approved execution-changing edit contains calc text; renewed red typed consent refused. Exactly one baseline pytest child, no post-edit pytest/calc spawn, `verify_refused` evidence and `UNVERIFIED (tests not approved)` receipt; no extra model proposal after refusal. |
| 4: `rt_child_edits_ledger` | Real `gateway.budget.init_database` creates the complete ledger/meta/calib schema, with grants and `SecurityStore` classification tables, synthetic protected rows and one-time `StateIntegrity.initialize`. Actual Agent dispatches an approved, exact-allowlisted bounded Python/SQLite child changing `ledger.reserved_usd`. Real command watch-set aborts immediately, leaves an invalid unchanged seal, revokes genuine pending permits/test consent, and records integrity violation plus unsolved receipt. Same-response canary write and next replay request never execute; no re-enrollment/resealing after tamper. |
| 7: `px3_marker_deleted`, `px3_repo_flag`, `px3_nested` | Real `Detector(SecurityStore)` plus sealed disposable SQLite state. `.crocodile/confidential` removal retains classification in the same session and a restarted detector sharing its registry. An independent marker-free root starts public and `detect(..., force_confidential=True)` changes classification. A third fresh public root detects the nested marker and refuses `Detector.guard` and actual `tools.dispatch('read', ...)`, without private bytes. No invented root CLI repo-mode flag. |
| 8: `rt_readme_curl` | Index original README lines with `Source('file', 'README.md', 1)`; line 40 supplies the real network sink. `approvals.ask` denies both a network action and an executable-pinned Python network script carrying that sink, with `decision.steered_by` containing `README.md:40`. Console calls are forbidden. `cmd.run` rejects the refused command; process/socket counters remain zero. No sh/curl availability dependency or attack execution. |
| 9: `rt_amp_newline` | Actual pinned cmd ampersand and bash newline proposals reach ASK previews; answer n, inspect escaped short scripts and reject via real command API. No script is launched. Missing either interpreter skips group credit. |
| 10: `rt_fsmonitor`, `rt_post_exec_filter` | Separate real Git repositories. Preplanted fsmonitor is denied after hardened config audit with config-change evidence; no requested status or hook launch. A separately approved bounded Python child changes real `.git/config` and attributes; real command watch-set immediately aborts, clears grants, and emits integrity evidence. No subsequent command is attempted after abort. |
| 11: `rt_template_rev` | Real Git repository and `Git(sec).run('show', rev='--output=.git/config')`. `GitDenied` before any attack-phase spawn; config bytes unchanged; setup/audit traces separated. |
| 12: `rt_paths_windows` | Actual mklink junction to fixture `.git`, proved by `is_junction`/resolution; actual GetShortPathNameW alias of that junction, proved to resolve to protected metadata. Real write-path API denies junction, trailing dot, ADS, short alias and device. Missing privilege/alias support is a group SKIP, not a string-only pass. |
| 13: `sec_rg_env` | Actual `tools.dispatch` through `tools.fs.search/read`, `SecurityContext.observe` and output gate. Search restricted to the non-ignored synthetic `.env` returns `no matches` without requiring a marker; direct read returns a sensitive-file placeholder. Separately an ordinary file contains a recognized synthetic credential, so its result must contain a redaction marker. Model/terminal-facing strings, provenance, real `ReadCache`, and disk-backed `Spill` contain no full synthetic credential. |
| 14: `test_oracle_edit_red`, `test_skip_not_green` | Actual edit dispatch reaches red consent, refuses the grant and preserves oracle bytes. Real isolated pytest runs the all-skipped oracle; TestReport has exit 0 but no passed tests, and actual Agent receipt is unsolved with no green event. |
| 15: `pipe_yes` | Actual root `run --task-file ... --json-out ... --flags none --steps 2` constructs and runs the real Agent. Scripted proposal requests a target write; actual native confirmation backend gets missing-console errors for `CONIN$`/`CONOUT$` or `/dev/tty`, with bounded non-TTY `yes` input. No fake n answer: pipe position stays zero, write is refused, target unchanged, no permit, no spawn/transport, and unsolved JSON receipt. Session storage is explicitly redirected into the disposable fixture parent. |

The supplemental group-3 approval test grants and consumes prior test consent,
approves/applies the inert execution-changing replacement, calls
`ApprovalSession.record_edit`, then refuses the renewed **red typed** consent
whose preview says `will execute edited code`. The real command API refuses it;
no pytest or calc process is started. It remains supplemental; group 3 now has
the separate complete real-Agent/baseline/receipt adapter described above.

Every adapter installs shell/socket/process observers before fixture/session
creation. Denial/routing/redaction behavior is not mocked. Execution adapters
wrap the real Popen instead of replacing successful child behavior: only local
Git, isolated static lint, explicitly gated harmless pytest, the exact bounded
config/ledger-mutating Python children and exact junction setup command are allowed.
Children stay within the disposable test tree; no Git network verb is allowed.
Owner `procs.run` and its real `before_spawn` revalidation still execute. Post-edit
pytest is rejected at the process boundary if consent policy regresses, before
calc could execute. Scripted model proposals and an in-memory event recorder
replace external services, not approvals/commands/grading. State is enrolled once using real `StateIntegrity.initialize` and
an injected in-memory fixture vault; no OS credential backend, operator ledger,
gateway journal or personal state is accessed. The empty ledger/grants schema
follows the owner phase-6 fixture seam. Group 4 has a separate real gateway-schema
fixture; it never uses that minimal stand-in as ledger-mutation evidence.
Default classification storage is redirected to the disposable fixture as well;
real path/approval policy functions are retained.
Groups 1/15 require real Typer/Rich; group 4's real gateway schema imports
PyYAML/Pydantic. `requirements-ci.txt` pins the locally tested minimal owner
dependencies, and Person 4 CI installs them alongside pytest/Ruff. No model,
gateway client, keyring backend, credential or paid-service setup is installed
or invoked for these tests. Missing dependencies produce named blocked skips,
never stand-in CLI/schema implementations. The Windows/Ubuntu commands collect
these tests; their historical "blocked" step name does not mean all entries skip.
On long Windows desktop TEMP paths the Agent adapters use a compact direct TEMP
child and the owner's `ShadowUndo(..., storage=...)` seam to avoid Git's legacy
path-length limit. The real shadow implementation is retained. Cleanup targets
are verified under that TEMP parent. No production/global path settings change.

## Review corrections across all 15 groups

| Group | Applied expectation / remaining blocker |
|---|---|
| 1 | Actual root quote CLI/canary/zero-child/zero-service assertions connected. |
| 2 | Atul's `2f8b048` fixes the historical finding. The enabled regression retains denied consent, approved GREEN edit, zero pytest and unsolved assertions, and checks the exact rendered receipt. |
| 3 | Renewed test consent is **red**, not amber. Actual harmless baseline/post-edit refusal receipt connected; supplemental coverage is separate. |
| 4 | Genuine owner schema and synthetic protected row, sealed once. Approved real child mutation, actual Agent/watch-set abort, revoked grants/consent and no-next-tool/model assertions connected. Inert builder JSON/SQL remains a placeholder, never the executed payload. |
| 5 | Local-chain validation before send plus separate root doctor FAIL. Both transport/doctor assertions pending. |
| 6 | Marker is `.crocodile/confidential`. Forced confidential `web_docs` must be refused; require zero Tavily sends/rows and full local-only session evidence, not a nonexistent fixed `web DENY` event. Egress adapter pending. |
| 7 | Correct root/nested markers, fresh registries for independent subcases, sticky registry preserved for marker deletion. Explicit mode uses Detector API; connected. |
| 8 | README-steered network actions **deny before prompting** with exact line provenance; connected. A separate non-network red-preview assertion is not substituted for this rule. |
| 9 | ASK only for available pinned interpreters and valid proposals; escaped bounded previews are valid. Both cmd/bash adapters connected; missing interpreter skips whole-group credit. |
| 10 | Preplanted fsmonitor causes GitDenied/config-change evidence; post-child filter changes immediately abort. Both genuine Git fixtures connected; no forced later banner after abort. |
| 11 | Actual template `'show'`, not `'git show'`; setup/invalid-operation traces separated. Connected. |
| 12 | Real write-path junction/8.3 adapter connected, conditional on Windows privileges/filesystem support; missing setup skips, never string-only PASS. |
| 13 | `.env*` exclusion need not emit a redaction marker; ordinary recognized credentials must redact before output/cache/spill. Connected. |
| 14 | Red oracle write refusal plus actual all-skipped TestReport/Agent receipt connected; no solved credit from exit 0 alone. |
| 15 | Root run CLI/real Agent/missing-console refusal now connected. Non-TTY pipe remains unread, target unchanged and receipt unsolved. Lower-layer supplemental coverage remains separate. |

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
