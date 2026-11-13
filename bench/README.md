# Benchmark task workspace preparation

This first Person 4 milestone prepares disposable exercise workspaces for the
future benchmark harness. It copies ordinary files, tests, and empty directories,
excluding every directory named `.meta` at every depth. The evaluation design
identifies `.meta/` as containing solutions. Source contents are never modified.

## Usage

Run from the repository root with Python 3.12 or newer. The preparation utility
uses only the Python standard library; it does not import or execute exercise
code, collect tests, run an agent, call a model, or access the network.

```powershell
python -m bench.prepare --source "C:\tasks\exercise" --destination "C:\workspaces\exercise-run-1"
```

The source must be an existing directory. The destination must not exist, and its
parent directory must already exist. Success prints the resolved workspace path
and exits with code 0. Invalid paths and copy failures print an error to stderr
and exit with code 1; argument errors use argparse's exit code 2.

The same operation is importable:

```python
from bench.prepare import prepare_workspace

workspace = prepare_workspace(source="tasks/exercise", destination="runs/task-1")
```

## Boundaries and failure handling

- Source and destination cannot overlap. Resolved paths are checked, including
  aliases through existing parent directories.
- Existing destinations, including dangling symlinks, are never overwritten.
- Symlinks, Windows junctions, and non-regular files are rejected throughout the
  exercise, including inside excluded `.meta/` directories and at the source root.
- A `.meta` directory cannot itself be used as the exercise root.
- The complete tree is validated before the destination is created. Copy errors
  and Python interruptions such as Ctrl+C remove the newly created destination.
  A destination created by another process before our exclusive creation is left
  untouched.
- File contents are preserved; timestamps, permissions, and other filesystem
  metadata are not promised. A regular file named `.meta` is retained: the
  exclusion applies to directories.

Use a stable source and a destination parent you control. This utility is not an
OS sandbox and does not guarantee safety against concurrent filesystem mutation.
The destination is visible while copying; consume it only after success. Forced
process termination, power loss, or filesystem errors that prevent cleanup can
leave a destination requiring inspection. It does not detect solutions stored
outside `.meta/`.

## Validation

The tests create synthetic exercises in pytest temporary directories; no real
benchmark tasks or generated reports are checked in. Link tests skip when the
host cannot create that link type. Junction tests run only on Windows; FIFO tests
run only where supported.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q -p no:cacheprovider bench/tests/test_prepare.py
python -m ruff check --no-cache bench
```

Pytest and Ruff are development tools, not runtime dependencies. Install them
separately if unavailable; the utility does not install anything.

Later milestones will add task selection, identical task text and caps, execution
through Parts 1-3, original-test restoration before grading, Bifrost-derived cost
accounting, and reports. This milestone produces no benchmark scores or savings
claims and makes no changes to shared contracts or other owners' code.
