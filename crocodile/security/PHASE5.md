# Part 3 Phase 5: shadow Git file undo

Based on `6f2ec0c` (Phase 4). No edit tool, root CLI or existing undo draft was
present. Implementation and proposed contracts remain in Part 3. Part 1 owns
registration and edit lifecycle integration; no shared contracts were changed.

## Owner integration

```python
from crocodile.security.undo import ShadowUndo, UndoConflict

# Trusted configuration, not model arguments. Reuse the active ApprovalSession
# with its Detector attached, including confidential mode where appropriate.
history = ShadowUndo(session.repo_root, session=session)

# Exact bytes that the approved edit will write; None represents removal.
# Existing permissions must be preserved. New files use 0600 (0666 on Windows).
changes = {"src/example.py": proposed_bytes, "obsolete.txt": None}
checkpoint = history.prepare(changes, reason="apply approved patch", call_id=call_id)
try:
    history.validate(checkpoint)  # all preimages, immediately before applying
    approvals.validate_before_execution(action, decision, session=session)
    apply_exact_changes(changes)  # Part 1's atomic edit tool; preserve permissions
    history.complete(checkpoint) # verify exact postimages, invalidate test consent
except Exception:
    # Cancel ONLY if nothing changed; cancel verifies every preimage.
    # If cancel conflicts, keep the pending checkpoint and report the partial edit.
    # Do not complete() by learning whatever happens to be on disk.
    raise
```

The owner must serialize this sequence, including multiple tool calls and turns.
`prepare` rejects further checkpoints while an edit is pending. On denial or a
no-op failure, call `cancel(checkpoint)` while the preimages are intact. After a
crash, `list()` exposes pending state: use `complete` only when all files equal
their intended results, or `cancel` only when all preimages remain. A mixed or
unexpected state requires explicit reconciliation; the API never discards it.

`snapshot(root, reason, call_id, *, changes, storage=None, session=None)` is the
proposed adapter for the architecture's snapshot interface. The extra mandatory
`changes` argument binds exact targets and expected postimages before editing;
whole-repo snapshots cannot reliably distinguish agent edits from concurrent
user changes. Keep this proposal local until Part 1 agrees to the contract.

Part 1 should register `crocodile undo [N] [--list]` (and the crock alias):

* `--list`: render `history.list()` entries newest first (id, commit, state).
* Undo: invoke `history.undo(N)` and render its returned relative paths with
  `approvals.escape`. The module-level `undo(root, steps=1, ...)` adapter also
  returns `list[str]`. An explicit user undo invocation authorizes the restore;
  model-initiated restores must pass Part 1's ordinary write approval first.
* `UndoConflict.paths`: show every conflicting path, preserve the current files,
  and keep the checkpoint. Do not retry with force or silently drop conflicts.
* `UndoError`, path/classification errors and I/O errors: show an escaped error,
  preserve storage, and stop. An interrupted undo is marked `restoring` and can
  be retried only when each file still equals its exact pre- or postimage.
* `undo` invalidates outstanding approval permits and session test consent.
  Reuse the active session; Part 1 should journal the call and result normally.

The standalone owner handler is available as
`python -m crocodile.security.undo [N] --repo ROOT [--list]`. It determines mode
through Phase 4 before restoration. The root CLI is still a Part 1 handoff.

## Storage and safeguards

Default storage is `%LOCALAPPDATA%/crocodile/shadow/<canonical-root-sha256>/`
(on other platforms, `$LOCALAPPDATA` or `~/.local/share`). A trusted explicit
storage directory supports disposable tests. Storage must not overlap the target
repository or traverse symlinks/junctions. It contains an independent bare Git
repository, `history.json`, and an exclusive operation lock.

Each checkpoint is a Git commit containing a manifest with byte-exact base64
preimages, absence records, modes and SHA-256 postimage signatures. It is retained
by `refs/crocodile/<checkpoint-id>` in shadow Git. Captured content stays local;
no remotes or network Git commands exist. The target repo's HEAD, branch, index,
configuration, untracked files outside the explicit change set, and history are
untouched. Target folders need not be Git repositories.

Git runs through the existing process boundary with a pinned outside-repo Git,
restricted environment, timeout and Windows job cleanup. All Git arguments are
internal fixed templates; hooks, signing, filters, external attributes, autocrlf,
global/system configuration, protocol access and automatic maintenance are
disabled or absent. The initial bare config is pinned and rechecked for each
call. Redirected metadata is rejected. File targets reuse Phase 2 paths and
Phase 4 confidentiality guards, with additional rejection of linked targets.
Protected metadata cannot be captured or restored.

Undo handles modified, created and removed regular files, including binary bytes
and empty files. It preflights the whole selected batch against current bytes,
absence and modes, simulating repeated paths across snapshots. Any initial
conflict prevents all target writes. During restoration it stages bytes next to
the target, rechecks before replacement, and atomically replaces each file.
Pre-existing modes are preserved; new-file undo removes only a matching file.
Parents must already exist: directory creation/removal, ACLs, timestamps, alternate
streams, Git branch/index undo and command side effects are outside this phase.
Limits: 1000 files, 16 MiB per file, 64 MiB combined preimage/intended bytes.

Per-file replacement is atomic; a multi-file batch is not an OS transaction.
An I/O failure or a new conflict during restoration can leave already restored
files; its durable `restoring` entry supports a checked retry. With multi-step
undo, completed entries stay `undone`; inspect `list()` before choosing how many
remaining steps to retry. After a process crash, inspect the recorded PID before
manually clearing a stale `operation.lock`; locks are never removed automatically.
Same-user changes in the final check/replace gap remain a filesystem race, as in
the existing edit boundary. Byte-identical user rewrites cannot be distinguished
from unchanged logical file state. HMAC/watch-set integrity belongs to Phase 6;
this phase does not claim protection from an attacker controlling shadow storage.

## Verification

`tests/security/test_phase5.py` uses disposable real Git storage and synthetic
file content. It covers modified/created/deleted binary files, persistence across
manager instances, unchanged target Git metadata, batch and multi-step conflicts,
pre-edit revalidation, refusal to adopt unexpected postimages, pending cancellation,
interrupted undo recovery, path/size/type/hardlink guards, config tampering, locks,
permission preservation, consent invalidation and standalone CLI handoff.
