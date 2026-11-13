# Python compatibility, environments, and bench approvals

## Python 3.12 and interpreter placement

Python 3.12 is supported. `undo.py` uses postponed annotations because the
`ShadowUndo.list` method otherwise shadows the built-in in later `list[str]`
return annotations. The original import failure was reproduced on Python 3.12.10
and the fix was verified on that actual interpreter, not only on Python 3.14.

Keep the application/test virtual environment **outside the target repository**
and any command cwd. For example, from a checkout, create a sibling environment:

```powershell
py -3.12 -m venv ..\.venvs\crocodile
& ..\.venvs\crocodile\Scripts\python.exe -m pip install pytest ruff
# Install the merged app's declared runtime dependencies in that environment too.
& ..\.venvs\crocodile\Scripts\python.exe -m pytest -q -p no:cacheprovider --confcutdir=tests/security tests/security
```

Use a trusted outside-repo interpreter in command/test argv too. An in-repo
`.venv/Scripts/python.exe` is deliberately rejected by executable pinning. Do not
relax that rule to make preview or relative-cwd tests pass. The repository's tests
must run from the outside environment; an editable app install does not put the
environment's executable inside the source tree.

## Official noninteractive bench session

Normal `ApprovalSession(...)` remains console-only. `yes_green` still cannot
approve test execution. No environment variable, repo marker, or Action field
enables automatic approval.

The trusted bench harness can call `ApprovalSession.for_bench` **before task
preparation**, on an existing empty directory directly beneath a trusted scratch
parent. The parent defaults to the OS temporary directory. Explicit parents are
trusted harness configuration, never model/repo arguments. Populated repositories,
linked paths and mismatched parents are refused. The session pins that root's
identity; replacing, moving or redirecting it aborts the session. Populate it in
place during preparation rather than deleting/recreating the directory.

```python
import sys
import tempfile
from pathlib import Path
from crocodile.security import Action, ApprovalSession, approvals, cmd

scratch = Path(tempfile.gettempdir()).resolve()
with tempfile.TemporaryDirectory(prefix="crocodile-bench-", dir=scratch) as workspace:
    security_session = ApprovalSession.for_bench(
        Path(workspace), parent=scratch, user_task=original_task,
        integrity=integrity, confidentiality=detector,
    )
    try:
        # Part 4 prepares the public task into this root AFTER session creation.
        prepare_task(destination=security_session.repo_root)
        action = Action(
            "test_consent",
            argv=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        )
        decision = approvals.ask(action, session=security_session)
        result = cmd.run(
            action.argv, security_session.repo_root, timeout=120,
            session=security_session, action=action, decision=decision,
        )
        # Grade/capture results before the temporary workspace is removed.
    finally:
        security_session.close_bench()
```

The harness supplies its already initialized integrity manager and Detector, with
the same state store, when those integrations are available. Their absence does
not become a claim of HMAC protection; the Phase 6 startup requirements still
apply. The harness owns preparation, original-test restoration/grading, durable
journaling and cleanup. Never copy confidential/user data into a public bench
workspace to bypass its original classification.

Parallel trials must also obey Phase 6's shared-state watch rules: coordinate
authorized writers while a child is watched. Do not disable the watch or split
the global budget into independent budgets just to avoid integrity conflicts.

Eligible local writes, shell actions and exact test-consent actions automatically
receive ordinary single-use permits. Hard denials happen first. Known network
sinks and Git mutation approvals are not auto-approved; a confidential session
cannot use bench auto. Fixed Git reads still use the existing hardened Git API.
Tests must use `Action('test_consent', ...)`, disable the pytest cache provider,
and avoid forbidden `-o`/config overrides. Changed argv/config/preimages invalidate
pending permits. Root identity, interpreter pinning, protected paths, timeout,
restricted child environment, process-tree cleanup, output redaction, and command
integrity watches remain on the normal path through `cmd.run` and `procs.run`.

`bench_session_started`/`bench_session_closed` events identify the lifecycle;
automatic approval events say `by='bench'` and retain risk level/source metadata,
the action digest, redacted resolved argv, cwd, and relevant config hashes.
They must never be presented as interactive human approval. Closing revokes
consent/permits and refuses further use of that session.

This is a disposable workspace and an explicit trusted automation authorization,
**not an OS sandbox**. Approved child code still has same-user capabilities,
including network access; URL/command policy is not a general child-network fence.
Do not use bench auto for security acceptance clips or normal user repositories.

## Part 1 / Part 4 handoff

Part 4 should create the empty workspace and session, then prepare the task there.
Part 1 should reuse that session in its `SecurityBridge` and send approvals and
execution through the ordinary `approvals.ask` / `cmd.run` path shown above. Keep
the permit, exact Action and session together. Remove the auto branch that routes
to `StubCmd`/a plain subprocess runner. If an auto run has no harness-created
session, refuse it instead of enabling auto mode on an already populated repo.

This commit changes Part 3 only; the teammate's adapter must be connected by its
owner. The teammate-reported secret scanner, exact-pytest consent and removal of
`pytest -o` remain their changes; they are not reimplemented here. Phase 7's pinned
integration findings remain historical evidence, not a report of this newer
owner work.

## Verification of this follow-up

* Native Windows Python 3.12.10: original `undo` import reproduced
  `TypeError: 'function' object is not subscriptable`; corrected import PASS.
* Full Python 3.12 suite: **182 tests, 160 subtests PASS** (403.77 seconds).
* Latest bench audit-metadata checks on 3.12: **12 tests, 6 subtests PASS**.
* Python 3.14 ordinary-approval/bench compatibility: **43 tests, 54 subtests PASS**.
* Ruff, compilation and Git whitespace checks PASS.

The isolated 3.12 test runtime was downloaded from the official
[Python 3.12.10 release](https://www.python.org/downloads/release/python-31210/)
and kept outside the checkout. The installed system interpreter was unchanged.
This is a pinned-minor-version test, not a recommendation to downgrade production
Python to that patch release. No teammate runtime or shared contracts were edited.
