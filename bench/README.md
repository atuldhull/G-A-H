# Benchmark workspace preparation and independent grading

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
python -m pytest -q -p no:cacheprovider bench/tests
python -m ruff check --no-cache bench
```

Pytest and Ruff are development tools, not runtime dependencies. Install them
separately if unavailable; the utility does not install anything.

## Independent task grading (milestone 2)

The grader restores an original oracle in a fresh copy of the agent's final tree
before running tests. Only the pytest subprocess imports exercise code; the grader
itself only reads and copies files. The utility uses the standard library, while
the selected Python interpreter must also have pytest and the exercise's required
dependencies installed. Nothing is installed by this utility.

```powershell
python -m bench.grade --original "C:\tasks\exercise" --final "C:\runs\agent-final" --output "C:\grades\task-1" --task-id "polyglot/example"
```

```python
from bench.grade import grade_exercise

result = grade_exercise(
    "tasks/exercise", "runs/agent-final", "grades/task-1",
    task_id="polyglot/example",
)
```

The output directory must be new, its parent must exist, and it must not overlap
either input. Both input trees remain unchanged. Preparation validates both trees
and strips `.meta/` using the milestone 1 utility. Artifacts are:

- `original/`: a frozen, metadata-free copy of the original exercise.
- `workspace/`: the fresh agent copy with the original oracle restored.
- `pytest.ini`: an empty fallback outside the workspace, preventing pytest from
  discovering unrelated configuration above the artifacts. Usable original
  workspace configuration takes precedence.
- `stdout.txt`, `stderr.txt`: subprocess output, including available partial
  output after failure or timeout.
- `result.json`: the machine-readable result. Setup/execution errors after output
  creation are retained here. Invalid arguments, overlapping paths, and existing
  outputs fail before creating artifacts and are reported by the CLI instead.

### Exact oracle rules

Rules apply to relative paths after `.meta/` exclusion. Protection matching is
case-insensitive on every host, conservatively covering Windows case aliases;
reported paths preserve their original spelling:

1. Every file below a directory named `test` or `tests` is protected,
   including helper modules, `__init__.py`, data, and fixtures.
2. `test_*.py`, `*_test.py`, and `conftest.py` are protected anywhere in the tree.
3. These configuration files are protected everywhere, as **whole files**:
   `pytest.ini`, `.pytest.ini`, `pytest.toml`, `.pytest.toml`, `pyproject.toml`,
   `tox.ini`, and `setup.cfg`. This includes non-pytest sections of shared configs.
4. Root `pytest.py`, `pytest/`, `sitecustomize.py`, and `usercustomize.py` are also
   protected to prevent agent-added runtime modules from shadowing the runner.
5. Repeat `--test-path RELATIVE_PATH` (or pass `test_paths=[...]`) to protect
   additional original files or entire directories, for example custom `check_*`
   tests or fixture data outside test directories. Paths must exist in the original
   and cannot be absolute, contain `..`, refer to `.`, or enter `.meta/`.

If an agent replaces a protected file with a directory, its contents are protected
as well. A path component matching rules 1-3 protects everything below it.
Bytecode (`*.pyc`, `*.pyo`) and `__pycache__/` and `.pytest_cache/` directories are
removed from both snapshots before comparison and execution; they are not oracle
edits. The original configuration's custom discovery settings are honored, but
are **not parsed to infer additional protected paths**: the harness must supply
those with `--test-path` before using a nonstandard suite.

Protected files in the final tree are compared with the original using SHA-256
content hashes and relative paths. `test_changes.added`, `.removed`, and `.changed`
are sorted POSIX-style relative path lists. `test_edit` is true if any list is
nonempty, including configuration, helper, or fixture edits. Agent-added protected
files are removed; all original protected files are then copied back, including
files the agent removed or replaced with directories. Ordinary solution files
remain from the agent tree.

### Execution and result semantics

The subprocess runs `[sys.executable, "-m", "pytest", "-q"]` with `workspace/` as
its working directory, closed stdin, captured output, and a default **180-second**
timeout. `--timeout SECONDS` / `timeout=...` accepts a finite positive override
for fast tests. Caller `PYTEST_*` and `PYTHON*` overrides are removed; plugin
autoload is disabled, bytecode writes are disabled, and `PYTEST_ADDOPTS` fixes
`--rootdir` and `--confcutdir` to the grading workspace. Original explicit plugins
and configuration remain active. These boundaries follow pytest's documented
[configuration](https://docs.pytest.org/en/stable/reference/customize.html) and
[plugin controls](https://docs.pytest.org/en/stable/how-to/plugins.html).

The version 1 JSON includes `task_id`, `pytest_exit_code` (null when no completed
pytest exit is available), `timed_out`, `timeout_seconds`, `solved`, `test_edit`,
`test_changes`, `error` (null or a diagnostic), `stdout_path`, `stderr_path`,
`workspace_path`, `command`, and `extra_test_paths`. Artifact paths are absolute.
`solved` is true only for a completed pytest exit 0; timeout or execution/setup
error is never solved. No-tests-collected (exit 5) is not solved. The CLI returns
0 for solved, 1 for unsolved or a recorded error, and 2 for invalid setup before
grading. It prints the result JSON when grading artifacts are available.

**Architecture ambiguity resolved:** section 1 does not define "test files" or
whether a test edit overrides a restored oracle pass. The conservative rules
above freeze configs and fixtures as well as tests, and remove added tests.
Following "solved = exit 0", a correct solution can have both `solved: true` and
`test_edit: true`; the harness must separately flag this as red for Crocodile.
Freezing entire shared config files may undo legitimate packaging edits. Helpers
outside these rules require explicit additional paths, as do nonstandard test
names selected by original configuration.

This executes exercise code as the current user, without an OS sandbox. Inputs
must be stable, trusted, self-contained benchmark exercises; original config and
tests must not direct execution to external workspaces. The timeout kills/waits
for the direct pytest process; separately spawned descendants are not guaranteed
to stop. Arbitrary malicious solution code can still affect its environment or
runner, so restoration is not a security boundary. Resource isolation and process
tree containment remain future integration work.

### Later harness integration

After each agent run, the harness will call `grade_exercise` using an immutable
original task, the agent's final tree, a unique artifact directory, the task ID,
and any suite-specific extra oracle paths. It will consume `result.json`, retain
test-edit flags and logs, and join the result with agent/run/model IDs and costs
from Bifrost logs. The grader does not trust the agent's own solved claim.

Task selection, identical prompts and caps, execution through Parts 1-3,
Bifrost-derived accounting, and benchmark reports remain later milestones. These
utilities produce no benchmark scores or savings claims and do not change shared
contracts or other owners' code.
