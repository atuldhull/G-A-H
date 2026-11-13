# Part 3 Phase 2: command, path and Git safeguards

Based on Phase 1 `a25a8e2`. No separate Phase 2 draft was present. All changes
remain in the Part 3 package and its tests; shared contracts and Part 1 files are
unchanged.

## Command execution

`cmd.run` retains its Phase 1 signature. It validates argv, binds the action to a
resolved executable and cwd, obtains or consumes approval, and revalidates at the
process boundary immediately before spawning. Direct Git calls must use the
fixed-template wrapper. Direct Crocodile and Python -m crocodile self-invocation
are refused. Batch-file arguments containing shell metacharacters are refused.
Shell/interpreter scripts remain approved arbitrary execution, visibly labelled
unparsed script; they are not classified as read-only commands.

`ApprovalSession` captures git/rg/ruff/python executable paths and size/mtime at
session start. Missing tools stay unavailable for that session. Pinned tools
cannot silently change location or metadata. Search ignores relative/current-dir
entries and every resolved PATH directory inside the repo/cwd. Executables must
be absolute local files outside both, with Windows executable-type restrictions.

`procs.run` is the package's internal process-spawn boundary. Children get closed
stdin, shell=False, a positive finite caller timeout, non-inherited handles, and
an environment constructed from an allowlist. Provider/VK credentials, arbitrary
KEY/TOKEN/SECRET variables, proxies, PYTHONPATH, user pytest options and inherited
Git configuration variables are absent. PATH is sanitized. Profile and temp
variables point to a per-call scratch directory outside the repo, removed after
cleanup. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 remains forced.

Windows children use CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED.
They join a job with KILL_ON_JOB_CLOSE and no breakaway before the initial thread
resumes. Job creation/assignment/resumption errors fail closed and terminate the
suspended child. Normal main-child exit, timeout and exceptions terminate the job,
wait up to five seconds for its active-process count to drain, then close its
handle. File-backed stdout/stderr avoids hanging on
inherited descendant pipes. Non-Windows CI uses a fresh process group and kills
the group on completion; this is not a restricted-token sandbox.

References: [Windows job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[assignment of suspended processes](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject),
[thread enumeration](https://learn.microsoft.com/en-us/windows/win32/toolhelp/thread-walking).

## Paths and writes

`paths.resolve_in_repo(path, root, *, cwd=None, for_write=False, mode='public')`
rejects escaping canonical paths, UNC/device namespaces, drive-relative names,
ADS, Windows device names, and controls. Windows trailing dots/spaces normalize
before checking; realpath expands existing short-name aliases, symlinks and
junctions. Lexical and resolved intermediate names are checked for protected
metadata. Writes reject protected config/credential/editor paths and hard-linked
targets. Public-mode paths inside marked confidential subtrees are denied.

Phase 1 binding now uses this validator for cwd and proposed write targets.
`paths.atomic_write` provides same-directory temporary files plus os.replace and
final validation. Part 1 retains approval/pre-image verification, file-undo hooks,
and ownership of integrating this into read/search/edit. Parent directories must
exist. It is not a filesystem sandbox: an explicitly approved arbitrary child
can write elsewhere as the same OS user. The child/network residual warnings from
the architecture still apply.

## Git wrapper

```python
from crocodile.security.git import Git

with Git(session) as git:
    status = git.run("status")
    history = git.run("log", rev="HEAD", count=20)
    patch = git.run("diff", rev="HEAD", paths=["module.py"])
```

The API accepts template names, not raw options. Reads: status, diff, log, show.
Mutations: commit, restore, detached checkout/switch, stash push, reset-hard,
explicit-file clean, branch-delete and push. Mutations require console approval;
irreversible forms are red. Confidential/steered pushes are denied. Push requires
an audited named remote, a validated branch, and an explicit commit-SHA refspec.
It never accepts a model-supplied transport URL or arbitrary refspec.

Revisions obey the architecture's grammar and resolve through
rev-parse --verify --end-of-options REV^{commit}; actual templates receive only
the resulting SHA. Counts are integers in [1, 200]. Paths are validated and follow
--. Banned option-prefix paths and revisions are refused. Mutation trees/current
tracked paths cannot include protected files. Restore/clean require explicit files.

Before every Git process, including internal revision/config queries, config and
attribute hashes are checked. New/changed attributes are inventoried recursively
(bounded to 50,000 entries). Config changes trigger a no-includes audit against
explicit safe core settings, remote URL/fetch, branch remote/merge/rebase, and
user name/email. Unexpected keys disable free Git for the entire session with an
event naming the keys. Includes, fsmonitor/filter commands and external helpers
in repository config are rejected rather than executed. Any change after the
audit but before spawn refuses the operation and requires a fresh audit.

Each call uses the pinned git, no pager, empty hooks directory, fsmonitor/editor/
askpass/credentials/ssh/external-diff overrides, disabled external protocol,
disabled system/global attributes and config, and no interactive prompts.
diff/log/show disable external diff and textconv. Filter drivers named in all
inventoried attribute files get empty process/clean/smudge and required=false.
Environment overrides cannot re-enable helpers. Attribute changes after a Git
operation are logged and force the next audit.

Only ordinary local .git directories are supported. Linked/submodule worktrees,
shared metadata, alternate object stores, linked attribute trees and inconclusive
scans fail closed. Support for them requires an explicit metadata-path contract.

## Remaining handoffs

- Part 1: adopt paths.resolve_in_repo / atomic_write and Git templates in its
  tool implementations. Existing Part 1 files are not changed. Preserve final
  approval checks and undo/oracle logic from Phase 1.
- Part 2: persist security events and integrate integrity checks around process
  execution/Git mutations. Registry-based confidentiality and HMAC/watch-set remain
  later phases; the detection stub has not been promoted to a finished control.
- Part 4: integrate security regression tests into CI and red-team acceptance.
  Native Windows job tests are required in Windows CI; neutral tests also run
  without Windows APIs. No shared contract changes have second-owner agreement.

Verification uses trusted temporary repositories, helper canaries, Python fixtures,
and actual Windows descendant processes. Commands remain the Phase 1 pytest/Ruff
checks under tests/security, with plugin autoload disabled.

Windows / Python 3.14 verification: the complete regression run passed 64 tests
and 88 subtests; its remaining descendant fixture hit an overly short startup
allowance. After changing that fixture's allowance from 1.5 to 10 seconds, its
targeted rerun passed (both normal-exit and timeout cleanup). All 65 regression
tests have therefore passed across those runs. Ruff, compileall, import smoke,
and Git whitespace checks passed. Test fixture cleanup retries only transient
Windows sharing violations for up to two seconds; it never ignores failed process
termination. No runtime dependencies or shared project configuration were added.

Phase commits are pushed only to the user-requested person-3 branch.
