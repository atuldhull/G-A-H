# Benchmark preparation, grading, planning, and offline reporting

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

Execution through Parts 1-3 and the Bifrost export/accounting adapter remain later
integration work. Offline reporting is implemented below, with no real measured
results supplied. These utilities do not change shared contracts or other owners'
code.

## Deterministic run planning (milestone 3)

The repository does not contain Polyglot or QuixBugs dataset checkouts or a verified
mapping of their native files to self-contained exercises. The planner therefore
uses an **explicit JSON task index**, not guessed filenames or directory globbing.
It discovers and validates declared exercises beneath the supplied local roots.
Unindexed directories are not treated as tasks. The source dataset version and
which tasks constitute the intended 34 Polyglot / 20 QuixBugs sets must be verified
before creating a real benchmark index; a small smoke index is not a full suite.

### Input contract

Provide an index with exactly `schema_version` (integer 1) and `tasks` (a list).
This is an explicitly **synthetic format example**, not a claim about either real
dataset's layout or contents:

```json
{
  "schema_version": 1,
  "tasks": [
    {
      "dataset": "polyglot",
      "id": "example-a",
      "source": "exercises/example-a",
      "task_file": "prompts/example-a.txt",
      "test_command": ["python", "-m", "pytest", "-q"],
      "test_paths": []
    },
    {
      "dataset": "quixbugs",
      "id": "example-b",
      "source": "exercises/example-b",
      "task_file": "prompts/example-b.txt",
      "test_command": ["python", "-m", "pytest", "-q"],
      "test_paths": ["oracle-data"]
    }
  ]
}
```

Each selected dataset root would contain its declared directories and files. For
example, the synthetic Polyglot entry above declares:

```text
POLYGLOT_ROOT/
  exercises/example-a/   # a nonempty, self-contained exercise, including tests
  prompts/example-a.txt  # explicitly supplied UTF-8 task text
```

The example names are arbitrary: the planner uses the index's paths verbatim.
`source` and `task_file` are relative to that entry's dataset root; optional
`test_paths` are relative to its exercise source and are passed to the future
grader as extra oracle paths. Each extra path must exist. Source paths must be
distinct and nonoverlapping, including across datasets. A native checkout with
shared implementation or test directories needs a reviewed assembly/adapter step
to produce independent exercise directories first; this planner does not invent
that mapping or copy any files.

IDs use lowercase ASCII letters, digits, dots, underscores, or hyphens, starting
with a letter or digit. Stable task IDs are `dataset/id`, so the same local ID in
different datasets is allowed. Duplicate canonical IDs, duplicate JSON keys,
unknown fields, empty prompts, empty exercises, missing paths, links/junctions in
exercise trees, and overlapping exercise sources fail clearly. Relative paths use
forward slashes and cannot be absolute, contain `..`, `.` or empty components,
backslashes, colons, or control characters. Source and extra oracle paths cannot
enter `.meta/`; prompt paths may explicitly name a file inside metadata, but the
index author must verify that it contains instructions rather than a solution.

Every task must declare its test command as argv beginning with
`["python", "-m", "pytest", "-q"]`. Further arguments are preserved, never executed
or interpreted as a shell command. `--runslow` is rejected. The index author must
verify suite-specific arguments, including the architecture's `--timeout=5` for
QuixBugs bitcount; no special filename or task identity is inferred. The planner
cannot confirm pytest collection or plugin availability without executing tests,
which is outside this command's scope.

### CLI and selection

From the repository root, with real roots and a reviewed task index supplied:

```powershell
python -m bench.plan --set both --polyglot "C:\datasets\polyglot" --quixbugs "C:\datasets\quixbugs" --task-index "C:\benchmark-inputs\tasks.json" --limit 3 --runs 2 --dry-run --output "C:\benchmark-plans\smoke.json"
```

Single-dataset examples require only that selected root:

```powershell
python -m bench.plan --set polyglot --polyglot "C:\datasets\polyglot" --task-index "C:\benchmark-inputs\tasks.json" --dry-run --output "C:\benchmark-plans\polyglot.json"
python -m bench.plan --set quixbugs --quixbugs "C:\datasets\quixbugs" --task-index "C:\benchmark-inputs\tasks.json" --dry-run --output "C:\benchmark-plans\quixbugs.json"
```

`--set` defaults to `both`. Index schema and duplicate IDs are validated globally;
only selected datasets' filesystem paths are inspected, and each selected dataset
must have at least one indexed task. Every task in a selected dataset is validated
**before** applying the limit, so a broken task beyond the limit is not hidden.

Tasks are ordered by canonical task ID (Polyglot first, then QuixBugs, then local
ID). `--limit N` is a positive **global task limit**, applied after set selection
and sorting and before expanding runs. It is not a per-dataset quota: a small
`--set both --limit N` can select only Polyglot tasks. Omit it to select all indexed
tasks. Values larger than the available count select all tasks.

`--runs N` is a positive repeat count for **both Crocodile and mini-swe-agent**,
default 2 independent runs each. The all-off twin always has one run per task.
For T tasks, total planned runs are `T * (2 * N + 1)`. Runs are ordered by task,
then `crocodile`, `mini-swe-agent`, `all-off-twin`, then one-based run number.
Run IDs are `dataset/id/variant/run-N`; no model sampling seeds are invented.

This command is **always planning-only**, including when `--dry-run` is omitted.
The flag explicitly labels a dry run. It prints selected/indexed task counts,
selected counts per dataset, and run counts per variant, and writes the same
manifest in either mode. It never invokes agents, prepares workspaces, starts
pytest, imports exercise code, makes network/model calls, or estimates costs.
All validation and reads finish before opening the output. The output manifest
must be a new file outside the selected dataset roots, with an existing parent;
existing output files and dangling links are not overwritten. Errors exit 2;
successful planning exits 0.

The importable API is `bench.plan.build_plan(task_index, polyglot=...,
quixbugs=..., dataset_set="both", limit=None, runs=2)`, followed by
`bench.plan.write_manifest(plan, output)`.

### Output and future execution

The version 1 manifest contains selected task and run arrays, counts, roots,
repeat counts, and `execution_enabled: false`. Every planned run records its
stable task/run IDs, dataset, agent variant, run number, resolved absolute source
path, test command argv, extra oracle paths, **30 steps**, and **600 seconds**.
Every variant receives identical task text: the UTF-8 prompt verbatim followed by
`\n\nTest command: `, a shell-quoted display of the argv, and a final newline. The
executor must treat argv as arguments and give this frozen text to every agent;
mini's standard wrapper template is separate. The text's SHA-256 is recorded.

The architecture's model, thinking/effort, Bifrost/cache policy, mini version,
parallelism 4, and 180-second independent grading timeout are recorded as
**intended policy**, not proof of configured or available infrastructure. JSON
keys and ordering are deterministic; there are no timestamps or random IDs.
Reordering the input tasks or changing only the output path does not change the
manifest bytes. Absolute paths are local to the machine; task/run IDs are portable.
Dataset contents must remain stable, and the later harness must pin/revalidate
dataset revisions; the planner hashes task text, not the entire exercise tree.

Before real runs, verify dataset revisions, the full task mapping and chosen
QuixBugs subset, prompts without solutions, original tests and extra oracle
paths, and actual test commands/dependencies. The milestone 2 grader currently
uses a fixed `python -m pytest -q`; applying task-specific arguments such as
bitcount's timeout consistently in agent and authoritative grading commands still
needs a harness adapter. The executor must also enforce the recorded model,
gateway/cache policy, caps, all-off flags, independent workspace isolation, and
WSL path translation for mini. None of that infrastructure is asserted ready.

The future harness will prepare a separate workspace for every manifest run,
dispatch its variant with the frozen prompt and caps, independently grade its
final tree, and join run IDs with grading artifacts and Bifrost-derived costs.
This milestone produces plans only, with no benchmark results or cost claims.

## Offline benchmark reporting (milestone 4)

`python -m bench.report` validates a complete run plan, JSONL results, a normalized
Bifrost session export, and a `prices.yaml` snapshot, then calculates pass rates,
paired task differences and W/L/T counts, CPST including unsolved costs, and
geometric cost ratios on jointly solved paired runs. Intervals use 10,000
whole-task bootstrap resamples with a recorded statistical seed. Missing or
invalid pairs and unverifiable costs are rejected; insufficient comparisons are
explicitly inconclusive, never silently converted to zero.

See [report-format.md](report-format.md) for the exact input schemas, CLI, cost
verification, repeated-run definitions, and limitations. The checked-in
[report.md](report.md) and [report.json](report.json) are **incomplete status
artifacts**, with no benchmark measurements. Synthetic evidence exists only in
tests and cannot be published through the report writer. Runtime execution and a
trusted gateway export adapter still need integration before a real scorecard can
replace these status files.
