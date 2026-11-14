# Person 4 CI

Workflow: `.github/workflows/person-4.yml` (`Person 4 checks`). It runs on every
push to `person-4` and every pull request targeting `main`, without path filters.
The matrix checks `windows-latest` and `ubuntu-latest`, both with Python 3.12.
Matrix fail-fast is disabled so both platform outcomes remain available.

The two direct development dependencies are pinned:

- `pytest==9.1.1`: required by the existing synthetic test suites. Version 9 also
  supports the pytest TOML configuration formats covered by grading tests.
- `ruff==0.17.5`: the CI linter. Its explicit policy is `E4,E7,E9,F`, a starter
  correctness baseline covering invalid syntax, undefined names, unused imports,
  and related errors. Import sorting, exception-style changes, formatting, and
  stricter optional rules are not silently introduced as part of this CI task.

Pytest's own transitive requirements are installed by pip. No project package,
Rich, model SDK, gateway, pricing library, real dataset, or benchmark agent is
installed. The implementation under test otherwise uses the standard library.
Actions are pinned to verified release commit SHAs; checkout does not persist
credentials. Workflow permissions are limited to `contents: read`. No custom
secrets or paid-service credentials are referenced.

## Commands and scope

The job sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONDONTWRITEBYTECODE=1`,
then runs:

```text
python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache bench crocodile/ui
python -m pytest -q -ra -p no:cacheprovider bench/tests crocodile/ui/tests
```

`--isolated` keeps the lint policy independent of other owners' future root
configuration. Both implementation and test Python files inside these two
Person 4 directories are linted. Ruff does not auto-fix or modify files.
The test step also runs after a lint failure, provided dependency installation
succeeded and the job was not cancelled; neither check is allowed to fail quietly.

Only the named synthetic test directories are collected. Grader unit tests run
pytest in tiny test-created temporary exercises to validate grading behavior;
these are not real benchmark runs. No `bench.plan`/`bench.grade` execution against
external tasks, benchmark race, Bifrost process, model call, dataset download,
real receipt/report publication, or network-backed exercise is part of CI.

## Platform skips and interpreting results

Pytest's `-ra` prints skip reasons and final counts. Existing Windows symlink tests
may skip when creation privileges are unavailable; FIFO coverage is unavailable
on Windows. Ubuntu runs the FIFO/symlink coverage and skips the Windows-only
junction test. Skips remain visible but are not failures. A genuine assertion,
collection, dependency, or lint failure remains a failed job; there is no blanket
`continue-on-error` or new test exclusion.

Jobs time out after 15 minutes. A newer run for the same ref cancels an older run.
For a particular commit, inspect both matrix jobs on GitHub Actions and their
steps/logs. Local checks on another Python version do not establish a Python 3.12
remote pass, and one successful matrix job does not establish both platforms pass.
This document describes the workflow; it is not a CI pass badge or benchmark claim.

Tightening the lint policy requires a separate, authorized source-cleanup change.
The default Ruff 0.17 rules additionally flag existing import order, exception
style, and implicit string concatenation; this milestone defines its baseline
explicitly rather than editing existing bench/UI code or hiding individual files.
