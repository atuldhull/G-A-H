# CLI and security integration

The normal `crocodile run` path initializes integrity, sticky confidential detection,
and the original user task before tools or model requests. It requires the explicitly
enrolled Part 2/3 state database and the HMAC key in Windows Credential Manager.
Startup never repairs or re-enrolls a missing or invalid seal. `CROCODILE_STATE_DB`
selects the shared database; the default is Part 3's application state path.
Keep this database and session storage outside the target repository.

Root commands delegate to their owner implementations: `quote`, `audit`, `undo`,
`doctor`, and `redteam`. `audit` requires explicit `--allow-model` values and returns
0 for PASS, 1 for FAIL, or 2 for incomplete evidence. Part 4 currently supplies only
a redteam case inventory: `redteam` returns 2; `redteam --inventory` returns 0 for
the inventory itself. Neither path claims that security assertions ran.

File reads and search hits enter the provenance index before truncation with their
original path and line number. Tool output, cache entries, spill reads, journal
payloads, and model-visible messages use the Part 3 scanner. Repository suggestions
remain untrusted, including after resume.

Approved writes bind the exact diff, resolved targets and preimages. The bridge
captures shadow-Git preimages and consumes the grant immediately before applying
the captured replacement bytes. A race refuses the write. Successful edits pass
their applied replacement text to the test-consent handler. Conflicts and partial
operation failures retain recovery evidence rather than overwriting user changes.
`undo --repo PATH` restores modified/deleted files and removes created files through
the separate shadow history; intervening changes produce a conflict. Creating new
parent directories is not supported by this file-edit API.

`run --resume SESSION --repo PATH` loads an HMAC-signed local checkpoint. It restores
the original task, conversation, task state and provenance, and never restores
permits or test consent. A changed task, signature failure, repository mismatch or
unknown pending operation refuses resume; pending operations are never replayed.

`run --yes` refuses execution. Only a trusted harness can supply an
`ApprovalSession.for_bench` created before populating its empty disposable workspace.
That session must also carry integrity and confidential detection. All its commands
still use the hardened runner and policy hard denials. Ordinary sessions use the
console, including typed confirmation for red actions. Put Python and virtual
environments outside the target repository; executable pinning rejects in-repo tools.

The optional budget integrity guard verifies and reseals inside each existing
`BEGIN IMMEDIATE` transaction for reservation, settlement, cancellation and heartbeat.
The gateway adapter attaches the same integrity manager used by the agent. Pricing,
balance arithmetic, limits and routing remain owned by Part 2. State tampering aborts
the session before another model/tool request.

Verification uses synthetic credentials, scripted model responses, real SQLite,
real console-permit logic and disposable command/Git/file fixtures. Live Bifrost,
Ollama and Tavily checks require teammate services and credentials. Part 4's executable
security assertions and feature-freeze recording remain teammate handoffs.

## Verification record — 2026-11-14

Native Windows Python 3.12.10, with the interpreter and dependencies outside the
target repository. No live provider credentials were used.

| Checks | Result |
| --- | --- |
| `tests/security tests/gateway` | 219 passed; 160 subtests passed |
| CLI/security integration, transactional budget and adapter tests | 20 passed |
| Additional consent and confidential gateway integration cases | 2 passed |
| Existing Part 1 loop, rewind, web, UI and engine tests | 43 passed initially; 2 outdated fixtures corrected and their targeted rerun passed (all 45 covered) |
| `redteam/tests` | 47 framework/fixture tests passed; 15 security assertions skipped as explicitly unimplemented |
| Ruff on changed Python files, Python 3.12 compile/import checks, `git diff --check` | Passed |

The two fixture corrections use the actual security bridge instead of a plain
runner and provide enough output to exercise masking after central output gating.
The path-escape assertion now accepts the hardened validator's wording. The
fixture credential store is synthetic; HMACs are checked against real SQLite rows
in a fresh transaction on every check, including after deliberate tampering.

Total: 333 unique passed tests across these runs, plus 160 subtests; 15 explicit
Part 4 security skips. This is fixture verification, not a live confidential-egress
audit or completion of Part 4's redteam assertions. Feature freeze was not declared,
so demo recordings were not made.
