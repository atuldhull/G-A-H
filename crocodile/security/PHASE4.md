# Part 3 Phase 4: confidential detection and audit

Based on `3f594ee`. No separate Phase 4 draft, Part 2 gateway/journal code, root CLI,
or shared contracts were present. Changes stay in Part 3's package and its tests.
Phase commits are pushed only to person-3.

## Detection before prompt/credential loading

```python
from crocodile.security.confidential import Detector, mode_for
from crocodile.security.classification import SecurityStore

store = SecurityStore(state_db, journals=part2_jsonl_journals)
mode = mode_for(
    repo_path,
    cwd=working_directory,
    tool_paths=tool_paths,
    store=store,
    session_id=session_id,
)
# Only now load task text and let Part 2 select credentials and routing.
```

`mode_for` replaces the always-public stub. It canonicalizes paths, discovers the
nearest Git root, checks ancestors through the filesystem root, consults sticky
state, and scans down at startup with the 50,000-entry cap. .git, node_modules and
.venv are excluded. Inaccessible/linked directory scans and capped scans refuse
public classification with the --confidential instruction. Explicit force mode
still validates state and identities; it does not bypass corrupt state.

The trusted optional root parameter narrows the known repo scope (useful for
unversioned folders and isolated tests). It must contain repo_path. Relative repo
and tool paths resolve against the supplied cwd; tool paths default to the repo
when cwd is omitted. Pass cwd explicitly when it differs from the repo.

Real Git identity uses the Phase 2 pinned, hardened Git reader to obtain available
first-commit and origin URL identities. Canonical paths remain available for loose
or unborn directories. Unsafe/inconclusive metadata refuses rather than silently
dropping Git identities. Linked Git worktrees remain unsupported, as in Phase 2.

Nested marked folders become deny zones without making public siblings private.
Their path identities persist independently from their public parent's Git ID.
Removed markers, missing registry rows, branch changes and clone/remote aliases
remain confidential through journal evidence. Detection returns a red-alert
message when sticky state retains classification after marker removal/change.

`paths.resolve_in_repo(..., store=store)` now also consults sticky canonical
ancestor state for public reads/writes; the existing search post-filter inherits
the default-store guard. A public session cannot read/edit a private subtree just
because its marker was deleted. Custom stores must be passed by the owner.

For approval integration, attach the same Detector as
`ApprovalSession(..., confidentiality=detector)`. Binding rechecks it and guards
targets; promotion to confidential invalidates pending permits/test consent.
Recheck at each turn before model egress too, not just when tools are proposed.
If mode changes, Part 2 must re-establish its routing/session boundary before any
send. A session already confidential never downgrades itself in place.

## Registry and journal ownership

SecurityStore lazily uses %APPDATA%/crocodile/state.db (platform fallback under
~/.local/state/crocodile). Public inspection of absent state creates no database.
State and configured classification journals must live outside the target repo.
Read/parse/lock errors fail closed.

Only confidential_repos, canaries and the append-only
security_classification_events table are created/written by Part 3. The first two
match Architecture 04. The separate classification journal makes row-deletion
recovery possible without taking ownership of Part 2's events table or logging.
Existing Part 2 SQLite events and explicitly configured JSONL journals are read
as additional evidence, never rewritten. JSONL envelopes use ts/type/payload and
session; session_started payloads provide mode, repo_root and/or normalized
repo_id parts (realpath, first_commit, remote). Missing configured journals refuse.

Identity matching uses ANY available ID and the transitive alias family. Public
session_started rows never clear confidentiality. Only a console-authorized
classification_changed event supersedes earlier confidential evidence. Audit
evaluates identity history at session-start time, without applying future aliases
retroactively. Corrupt state refuses; HMAC/watch-set protection is a later phase.
Deleting all state and all independent journals cannot be recovered by this phase
alone. Part 2 must wire its durable journal and the later integrity owner must
protect authorized writes across shared state.

## Interactive init and canaries

`set_classification(repo, confidential=True/False, store=..., canary_source=...)`
is the Part 3 handler for init. It uses the console-only backend, drains queued
keys, shows repo identities, and requires the displayed word plus two-digit nonce.
No console, piped stdin, plain yes or changed preview inputs cannot authorize it.
Source pre-images, identity, marker and classification history are revalidated.

--public cannot override a marked/sticky ancestor from a child folder. It removes
the selected marker and writes a durable explicit-public event for matching
identities; it does not erase past evidence or registered canaries. Shared Git IDs
mean the alias family is affected; the review shows those IDs. Other surviving
markers can re-establish confidentiality on the next detection.

--confidential creates a cryptographic CANARY-<128-bit hex> token, registers it,
and creates .crocodile/confidential and .crocodile/canary. An explicitly selected
supported source file may receive a comment. Protected/linked/hard-linked targets
are refused. Registration/classification precedes file writes: an I/O failure
leaves the repo confidential rather than rolling back to public.

`canaries.check(payload, store=store)` is Part 2's send-time hook. Pass actual
public/Tavily UTF-8 payload bytes/text or the structured send envelope. Unsupported
byte encodings and NUL-bearing wire data refuse rather than return a clean scan.
It scans every
registered token, including decoded JSON string escapes. A hit sets blocked=True;
findings contain counts and token hashes only. Registry/scan errors must also
refuse sending. Part 2 owns blocking the send and writing the egress record. This
is an exact canary check, not paraphrase/child-process exfiltration detection.

## Audit and audit --all

`audit.audit_database(state_db, allowlist=tags, gateway_logs=normalized_logs,
session=None, all_sessions=False, journals=...)` opens evidence read-only. Default
scope is the latest egress session; an explicit session or --all is supported.
There is no network sender or log producer in this module.

PASS requires valid evidence, journal-backed session modes, local-key alias,
allowlisted ollama/ requested models, actual Ollama models/provider, local Bifrost
destination, empty fallbacks, and matching request IDs in normalized gateway logs
with Ollama provider/model. Cloud tags, conflicting logs, duplicate IDs, malformed
metadata, contradictory public session labels and sent public canary hits fail.
Absent rows, missing session/gateway evidence or unreadable data are INCOMPLETE,
never a vacuous PASS. Reports redact credentials and escape terminal controls.

Blocked attempts are listed separately and need not have an actual provider/model.
The zero-Tavily condition applies to sent confidential requests. A blocked Tavily
attempt is logged and listed, rather than being counted as an outbound request;
this resolves the spec's tension between logging every blocked attempt and the
older literal "zero Tavily rows" wording. No PASS claim covers direct key use or
unlogged/approved child traffic outside the agent egress boundary.

Part 2 must supply normalized gateway records with request_id/provider/model.
Their actual /api/logs response schema/auth has not been guessed or implemented
here. A trusted export or the owner's existing egress client can supply them.

Standalone handlers until Part 1 registers the root CLI:

```powershell
python -m crocodile.security.confidential mode --repo REPO --state-db STATE
python -m crocodile.security.confidential init --repo REPO --confidential --state-db STATE
python -m crocodile.security.confidential init --repo REPO --public --state-db STATE
python -m crocodile.security.audit --state-db STATE --allow-model qwen2.5-coder:7b --gateway-log LOG.json
python -m crocodile.security.audit --all --state-db STATE --allow-model qwen2.5-coder:7b --gateway-log LOG.json
```

Audit exit codes are 0 PASS, 1 FAIL, 2 INCOMPLETE. Part 1 owns shared CLI wiring and
read/search/edit hooks. Part 2 owns credentials, gateway routing, model/host
enforcement, context fitting, socket guard, HTTP logs and journal integration.
No files in those owners' folders or shared contracts were changed.

## Verification and live availability

Fixtures cover ancestor/realpath/repo-flag/relative-path detection, nested deny
zones, bounded scans, clone/remote aliases, registry deletion recovery, SQLite and
JSONL journal adapters, console changes, canary creation/comments/send-time
blocking, session rechecks, audit scopes, missing/malformed evidence and routing
violations. Real local Git identity lookup uses a harmless temporary repository.

Live availability check on this task: no Part 2 code in this checkout, no listeners
on the standard Bifrost/Ollama ports 8080/11434, and no default Crocodile state.db.
Therefore no live routing/audit pass is claimed; the owner handoff is exercised
with deterministic egress and normalized gateway-log fixtures instead.

Windows / Python 3.14 validation: the complete Phase 0-4 run passed 134 tests and
109 subtests. Final focused detection/audit/approval checks passed 79 tests and
57 subtests, including the additional partial-identity audit case (135 distinct
tests verified across the runs). Ruff, compileall, import smoke and Git whitespace
checks passed. Classification confirmation uses fake console fixtures; no real
repository classification or live provider routing was changed by the tests.
