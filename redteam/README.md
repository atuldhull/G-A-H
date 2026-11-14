# Red-team fixture framework

This milestone inventories the 15 groups in architecture/10 section 3 (20 named
case IDs). It constructs synthetic inputs; it does **not** execute or pass those
security cases. Team-split ownership places these tests under `redteam/tests/`,
rather than the older architecture example `tests/redteam/`.

From the repository root, with Python 3.12+ and pytest installed:

```text
python -m redteam.inventory
python -m pytest --collect-only -q redteam/tests/test_security_cases.py
python -m pytest -q -ra -p no:cacheprovider redteam/tests
python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache redteam
```

`inventory.py` is the canonical machine-readable inventory. The command prints
JSON containing the group number, exact architecture IDs, expected observable
outcome, owner interfaces, availability, required evidence and blocked reason.
Availability checks **source-file presence only**, without importing another
owner's module. `source-present-unverified` does not certify an API signature,
integration, or security behavior. Missing sources are marked `missing`.

On the initial `person-4` branch the static `quote_task` module is present; the
CLI, agent, security and gateway interfaces are missing. Even case 1 remains
blocked: its end-to-end CLI assertion and Person 3 review are outstanding.
Adding or merging a source file never enables a security test automatically.

## Building fixtures safely

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from redteam.fixtures import build_fixture

with TemporaryDirectory() as directory:
    fixture = build_fixture("rt_readme_curl", Path(directory) / "exercise")
    # Inspect fixture.scenario_file as data. Do not execute the exercise.
```

`build_fixture(case_id, destination) -> Fixture` accepts any of the 20 IDs and
returns the group's `Case`, new root, expected absent canary and `scenario.json`.
The destination must not exist and its parent must exist. It writes only ordinary
UTF-8 files/directories in that new destination. UNC paths and linked parents are
rejected; choose a local temporary directory, never a mapped network drive.
On a filesystem write error,
discard the temporary directory; partial fixtures are not executable test results.
Do not build into a real repository, home directory, or live state directory.

Payloads include inert Python text, a malicious `conftest.py`, synthetic `.env`,
fake git config, deferred edit scripts and command argv. Construction never
imports payloads, runs git/tests/commands, opens a socket, starts an HTTP sink,
reads credentials, or calls a model. All URLs use `example.invalid`; the `sk-`
canary explicitly says it is synthetic. Future adapters must block outbound
transport and intercept command attempts, including `calc`, regardless of policy
success. No live external target is needed to prove a denied action.

Windows junction/ADS/device/8.3 paths stay JSON data. The builder does not create
links or reserved paths on either platform. The ledger is an explicitly named
JSON placeholder, not a valid SQLite/HMAC ledger. The fake `.git/config` is not a
real initialized repository. Reviewed execution adapters must arrange these
realistic surfaces in separate disposable directories before exercising the
owner code. They must record unavailable Windows privileges/8.3 aliases as
blocked subcases; they must not claim a string-only check proved junction safety.

Framework tests guard all builders against subprocess/shell/network use, check
canaries remain absent, verify provenance at README line 40, and account for every
architecture ID. These are framework passes, separate from security verdicts.

## Review and execution gate

See [review.md](review.md) for the Person 3 handoff and group evidence checklist.
All 15 `test_security_case` instances are unconditionally skipped with a reason
naming pending review, the missing interfaces, and the unimplemented adapter.
There are no live assertions yet. Removing the skip alone produces a failure,
not an empty passing test. No `xfail`, fake success, or 0/15 measured pass rate is
reported. Security execution is **not performed / incomplete**, not measured zero.

After Person 3 approves expected outcomes, add explicit execution adapters and
positive evidence of attempted actions plus negative evidence of no forbidden
effect. Each multi-ID group passes only when all its subcases were executed and
passed. An absent canary without a proven attempt is insufficient evidence.
Use bounded fake consoles/transport observers and retain decisions, transcripts,
receipts, relevant journal rows and before/after snapshots per case.

The Person 4 Windows/Ubuntu CI workflow runs the fixture/inventory framework
checks separately from the blocked security-case collection. Verbose skipped-case
entries and `-ra` keep the pending review and missing-interface blockers visible.
Ruff includes `redteam/`. A green CI job establishes framework checks passed;
it does not establish that the skipped security cases passed.
