# Parts 1 and 2 shared contract decisions — 2026-11-15

Implemented under the user's shared-contract integration request. These are the
same constants/resolvers used by Part 3; adapters translate owner-specific APIs.
This records the implementation decision, not an assertion that teammates have
separately reviewed or merged it.

## One state resolver

`crocodile.shared_state.resolve_state_path(path=None)` owns database selection.
Fresh Windows installations use `%APPDATA%\crocodile\state.db`. The non-Windows
default is `$XDG_STATE_HOME/crocodile/state.db`, or `~/.local/state/crocodile/state.db`.
`security.classification.default_state_path` and `runtime_security.state_path` are
compatibility entry points to that same resolver, not independent defaults.

Upgrade rules deliberately avoid moving/copying an active ledger or WAL:

| Existing state | Resolution |
| --- | --- |
| Neither historical Windows path exists | Return the fresh APPDATA default; do not create/enroll it. |
| Only APPDATA has a DB | Use it. |
| Only LOCALAPPDATA has a DB | Adopt it in place as this installation's resolved database. Every owner uses this same path; do not create an empty APPDATA replacement. |
| Both have a DB, even if one is empty | Refuse automatic selection. Review the histories and explicitly choose the existing DB using `CROCODILE_STATE_DB` or an explicit CLI path. |
| An env override names a missing file while historical state exists | Refuse; an upgrade must not silently abandon the ledger. |
| A DB is absent but its WAL/SHM/journal remains | Refuse until the existing state is recovered. |

Paths must be absolute and must not traverse symlinks/junctions. An explicit
trusted API/CLI path is a deliberate owner selection; it is not inferred from repo
text. The resolver never copies, deletes, merges or reseals databases. A new DB
still requires the existing trusted schema/HMAC enrollment flow before execution.

For an intentional physical move, stop all writers, take a SQLite-consistent
backup, verify its existing HMAC with the same stored key, and explicitly select
the verified target. Preserve the original for recovery; do not blindly copy only
`state.db` while its WAL is active or re-enroll an invalid seal.

CLI startup, signed resume, gateway budgeting/journaling, classification, integrity
and diagnostics use the shared resolver. `doctor --config-dir` selects configuration
files, not a different database; `doctor --state-db` is an explicit DB override.
New signed session checkpoints bind the resolved DB path and refuse a different
database on resume. Older signed checkpoints without that field remain readable
against the shared selection and gain the binding when saved again.

Session files, shadow Git and process scratch directories continue to use local
application storage. They are not additional state databases.

## Canonical credentials

Service: **`crocodile`**, using the explicit Windows `WinVaultKeyring` backend.
Backend discovery, environment-variable keys and on-read legacy aliases are absent
from the production lookups.

| Purpose | Canonical username |
| --- | --- |
| Confidential gateway | `vk_local` |
| Public gateway | `vk_public` |
| Trusted bench gateway | `vk_bench` |
| Public Tavily search | `tavily_key` |
| State HMAC key | `hmac_key` (unchanged) |

`CredentialStore.gateway(alias)` and `CredentialStore.get(name)` are the shared
lookup interfaces. `SecurityContext` requires `vk_local` when a confidential
session starts, resumes or upgrades from public to confidential. Missing credentials
fail closed before model/tool work. The gateway reads `vk_local` again immediately
before a confidential model call, so deletion after startup also refuses egress.
The HMAC key is independently required for state verification; public/bench/Tavily
credentials are never looked up as substitutes for the confidential gateway key.

Confidential web availability is short-circuited before Tavily lookup, and forced
web calls are denied before loading any Tavily credential. The development egress
stub refuses confidential sessions. `CROCODILE_VK*`, `TAVILY_API_KEY`, generic
provider-key variables and old dashed names cannot rescue missing confidential
credentials. Normal public gateway/Tavily production lookups also use only the
canonical identifiers; environment-based provisioning must be updated.

Existing dashed gateway entries and `tavily` entries are **not** used automatically.
An explicit trusted provisioning operation can copy an old entry to its canonical
name, preserving the old entry and refusing conflicting values:

```python
from crocodile.credentials import copy_legacy_credential, windows_backend
copy_legacy_credential("local", backend=windows_backend())
# Other explicit choices: "public", "bench", "tavily".
```

This helper returns no secret and verifies readback. It is never called by startup
or model/tool execution. No real user credential was read/copied by this change's
fixture verification.

## Session-start event and replay

New writes use `journal_contract.SESSION_STARTED == "session_started"`, with a
`type`/`payload` envelope. The normal producer supplies `repo_root`, `mode`, flags
and tier; the enclosing record supplies session ID and timestamp. Both the SQLite
and local JSONL producer normalize old callers that still request `session_start`.

Readers accept historical `session_start` and `session_started`, both SQLite rows
and JSONL `type`/`payload` or flattened `event` envelopes. A legacy `repo` string
becomes `repo_root`; a legacy explicit `confidential: true` becomes confidential
mode. Conflicting envelope names, repository identities or mode flags are refused.
Missing/invalid evidence is not silently interpreted as public.

`EventJournal.get_events`, resume, sticky classification and audit all consume the
normalization helpers. Historical journals are read without rewriting protected
rows or signatures. Public session-start records do not clear older confidential
classification; only the existing explicit classification-change flow can do that.
Replay retains confidential mode if another start event later says public.

The additive `contracts.State.mode` and `repo_root` fields expose replay context;
unknown mode stays `None`. `State.events` and the gateway adapter's resumed events
use canonical `type`/`payload` envelopes rather than discarding event names. Resume
continues to preserve OUTCOME UNKNOWN tool results and never replays side effects.
Signed agent resume still restores no command permits or test consent.

## Verification scope

Native Windows Python 3.12.10 fixtures cover fresh resolution, both historical
locations, preserved grants, normal startup/resume sharing one database, ambiguous
and missing-path failures, independent doctor config/state paths, canonical-only
confidential credentials, absent-key refusal despite env/legacy/public/Tavily keys,
explicit credential-copy conflict refusal, and both legacy session-start spellings
through SQLite/JSONL replay, sticky classification and audit.

The final contract/journal run passed **22 tests**. The broader owner regression
run passed **83 tests and 32 subtests** (the unrelated full bench command fixture
was deselected; the new bench credential/session fixture passed). Coverage includes
canonical JSONL/SQLite writes and replay, correct public/bench credential selection,
database-bound resume refusal and compatibility with older signed checkpoints.
Changed-file Ruff, Python 3.12 compile checks and `git diff --check` passed.

All secrets in tests are synthetic; no real credential migration, database relocation
or live confidential egress was performed. Deployment owners must provision/copy
canonical credentials explicitly before using an older installation's new runtime.
