# Part 3 Phase 6: state integrity and user doctor

Based on Phase 5 `09b1311`. No Part 2 ledger/router/egress implementation or Part 1
root CLI exists in this checkout. Changes stay in Part 3 and its tests; no shared
contracts, money logic, routing enforcement or gateway logging were added.

## Key storage and initial enrollment

`HMACKeys` stores exactly 32 random bytes (hex encoded) in service `crocodile`,
username `hmac_key`. Production uses the explicit
`keyring.backends.Windows.WinVaultKeyring` backend: no backend discovery, env key,
plaintext fallback or repo config. Install `keyring` and `pywin32` with the app.
See the [upstream Windows backend](https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py)
and [keyring API](https://keyring.readthedocs.io/en/stable/). Backends injected in
fixtures are a trusted owner seam. Non-Windows production fails closed until an
approved secure backend is supplied.

Part 1's explicit `init` command should ask Part 2 to create its schema, then:

```python
from crocodile.security.integrity import StateIntegrity

integrity = StateIntegrity(state_db_path)
# db is Part 2's connection, with no attached/temp databases.
db.execute("BEGIN IMMEDIATE")
try:
    integrity.initialize(db)  # one-time trusted enrollment, creates key if missing
    db.commit()
except BaseException:
    db.rollback()
    raise
```

The required tables are `ledger`, `confidential_repos`, `grants`; Part 2 owns ledger
and grants, while registry writes stay with Part 3. The owners must create the
agreed schema first. The integrity module creates/updates only `meta.hmac`. Enrollment refuses an
existing seal before accessing/creating a key. Never call initialize to repair a
verification failure or automatically enroll an existing untrusted database.
Serialize init across processes. Verification never creates keys, files, tables
or seals; missing key, missing DB/table/seal, bad schema, lock or mismatch refuses
use. A lost key requires an explicit recovery/review procedure outside this API.

HMAC-SHA-256 covers a versioned canonical digest of protected schemas/indexes/
triggers and sorted typed row values. It protects **all ledger windows**, avoiding
an unchecked rollover at UTC midnight, and includes grants, registry, canaries,
Part 3's classification journal, and non-HMAC meta rows. Optional-table absence is
signed too. SQLite logical reads include committed WAL state; physical DB page
layout and SELECT order do not affect the signature. Journal/egress/calibration
tables remain Part 2 owned and are outside this HMAC scope. Hash chains remain P1.

## Authorized writes and Part 2 reservation handoff

```python
db.execute("BEGIN IMMEDIATE")  # Part 2's existing reservation writer lock
try:
    integrity.before_reserve(db, session=session)  # fail closed + abort event
    with integrity.authorized_write(db):         # verify old seal under same lock
        # Part 2 checks balance and writes held/settled/cancelled/heartbeat rows.
        owner_update_ledger(db)
        # Context recomputes meta.hmac AFTER writes, in the SAME transaction.
    db.commit()
except BaseException:
    db.rollback()
    raise
```

Use `authorized_write` for every protected-state mutation, including grant,
heartbeat, settlement, expiration and schema migration operations. It verifies
before yielding, never blesses existing tampering, and rolls back the whole
transaction on failure. The owner must not commit/rollback/swap connections in
the context body. Hold the writer lock through verification, balance calculation,
row writes, seal update and commit; do not separately verify then later reserve.

`verify_state(integrity, connection=db, session=session)` is also available for
owner tool decisions/reservations. The session parameter latches the abort and
emits the event; callers without a session receive `IntegrityViolation` and must
propagate it without network/ledger work. Keep failed-verification events outside
the rejected protected transaction. Part 2 owns durable event journaling.

## Part 1 session and Part 3 integration

```python
from crocodile.security import ApprovalSession
from crocodile.security.classification import SecurityStore
from crocodile.security.confidential import Detector

store = SecurityStore(state_db_path, integrity=integrity)
detector = Detector(store=store)
# Determine mode through detector before loading prompt text/cloud credentials.
session = ApprovalSession(repo_root, mode=mode, integrity=integrity,
                          confidentiality=detector)
```

Attach the SAME StateIntegrity to the session and SecurityStore. Attached registry
reads verify before trusting evidence; authorized classification/canary writes
verify and re-seal within their existing transaction. A disappearing sealed DB
never becomes empty/public evidence. `binding.bind` verifies before every approval
decision and immediately before execution; fixed free Git reads also verify.
Shadow undo verifies at every locked operation. Other Part 1 tools must call
`session.verify_integrity()` before their decisions, including read-only tools.

For backwards-compatible Phase 0–5 fixtures, a session without attached integrity
can still perform local operations. Its command watch-set uses raw DB/WAL hashes;
it does NOT claim HMAC verification. `doctor` fails such a session. Production
startup must require successful enrollment/verification and attach integrity
before registering tools or allowing reservations; do not expose this option to
model arguments.

`cmd.run` watches every execution; target `Git._call` watches every mutation,
including timeout/exception exits, with a final check in the existing pre-spawn
callback. Git's per-call config audit remains in place. Watched paths:

* User `config.yaml`, `policy.yaml`, `prices.yaml`, and state HMAC.
* The configured empty-hooks directory and Git wrapper's actual empty-hooks dir.
* Repo `.git/config`, `.git/hooks/**`, `.git/info/attributes`, `.gitattributes`,
  `.gitmodules`, and recursive `.crocodile/**`.

Hashing includes absent paths, directory membership, file bytes and basic modes;
links/special or multiply linked files, unreadable paths, more than 50,000 entries
or 256 MiB fail closed. Protected state is bounded to 100,000 rows per table.
Unexpected changes discard the tool result, clear approval permits/test consent,
disable Git and permanently abort the session. Further decisions and executions
are refused. One `integrity_violation` event records an escaped path/table label,
expected/found digest or generic status, and `session_aborted=True`; no row values,
config contents or credentials are emitted. Part 1 must render a red banner and
stop the loop; Part 2 journals the event through its normal owner API.

Do not run authorized state/config writers concurrently with a watched child.
Newly signed but changed state during that interval is treated as unexpected.
Legitimate config/marker changes belong to explicit owner operations outside
command watches; validate and commit them before starting a new tool watch.
Do not whitelist whatever a child left behind or re-sign after an integrity error.
Tracked Git metadata changes during a mutation also abort; approval of a broad
checkout does not waive metadata integrity checks.

## User doctor and remaining owner hooks

`doctor.diagnose(session=..., config=..., prices=..., evidence=..., environment=...)`
returns a report with `passed` and credential-masked, control-escaped `render()`.
It checks state/key verification, pinned tools outside the repo, numeric tiered
prices for every chain model (no missing/TBD values), local model prefix/exact
allowlist/cloud-tag rejection, loopback endpoints, and context >= configured
window and 32768. Missing `OLLAMA_NO_CLOUD=1` is a warning; apply this setting to
the daemon too. Environment checks alone cannot attest a separately started
daemon's environment.

No network client, routing enforcement, admin credential or ACL-changing operation
is introduced. Part 2 should supply **fresh trusted probe evidence**, bound to the
current configuration, collected through its egress boundary:

* `ollama_tags`: `/api/tags` JSON with exact tag name, digest and positive blob size.
* `ollama_show`: tag -> `/api/show` JSON with nonempty model_info, no remote
  host/model/cloud fields (nested fields are checked too).
* `gateway`: reachable/inference_auth booleans; vk_alias=`local`; requested_model
  with anthropic/openai prefix; refusal_status=4xx; provider_calls=0. This is an
  explicit test that local VK refuses a cloud model without a provider call.
* `socket_guard_active=True`, `limits_admin_owned=True`,
  `limits_user_writable=False`: Part 2's live guard/ACL probe attestations.

Absent or unsuccessful evidence yields FAIL, never a fake healthy result. Do not
load public/Tavily credentials in confidential mode for these probes. The report
discards raw probe/exception text and additionally masks password/key/token
assignments, Bearer/Basic headers, VK/Tavily prefixes and shared credential forms.

Part 1 must register `crocodile doctor` (and crock alias), collect owner probes,
render checks and return nonzero on FAIL. Standalone
`python -m crocodile.security.doctor --repo ROOT --config-dir DIR` uses safe YAML
loading (PyYAML required), verifies all three settings files exist and are
mappings, and performs local diagnostics. It intentionally fails missing live
probe checks until Part 2 provides its adapter. Live gateway/ACL integration was
unavailable in this checkout; routing and ledger ownership remain with Part 2.

## Verification and limits

Disposable tests cover key creation/no rotation/backend errors, transaction and
connection checks, authorized resealing/rollback, historical ledger tampering,
registry/grants/schema/seal changes, committed WAL changes with a live connection,
missing DB, classification/canary resealing, real harmless child edits to settings
and ledger, exception exits, Git mutation watches, abort latching, watch caps and
hardlinks, doctor success/failures and masked diagnostics.

This is detection, not a sandbox or rollback mechanism. A violating command may
already have side effects. No detection is promised for a transient change fully
restored before the final hash, or an attacker who reads the same-user Credential
Manager key and recomputes signatures. Limits/VK enforcement and safe daemon
routing remain independent Part 2 controls. ACLs/alternate streams are not hashed.
