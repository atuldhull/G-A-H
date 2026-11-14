# Missing inputs for the real 54-task index

Inspection on 2026-11-14 at `1a374a5b1dd1772f916d799d199778ed5613938b`
found no Polyglot/QuixBugs checkout, dataset archive, real task index, or reviewed
oracle mapping in this workspace. The search included ignored/hidden filenames
inside this repository, excluding Git/tool caches and credential locations; it
did not search unrelated directories. Existing test fixtures are synthetic.
`bench/report.json` is not a dataset index. No real 54-task index was created.

The dataset owner must supply all of the following before real planning:

1. The local root and pinned upstream revision of the **34 Python Polyglot
   exercises**, with their exact membership and license/provenance recorded.
2. The local root, pinned revision, and exact **20 Python QuixBugs programs**,
   including the recorded selection seed/procedure. The architecture specifies
   20 selected programs but does not identify them. Do not pick a new subset.
3. For every task, a stable lowercase local ID and the actual relative source
   directory beneath its dataset root. Assemblies must be independent,
   nonoverlapping, self-contained trees, retaining original tests, helpers,
   configuration and data. A shared upstream test tree needs a reviewed assembly
   mapping; the planner does not infer one. No links or junctions are accepted.
4. For every task, an actual UTF-8 task-text file beneath the dataset root,
   containing the exact agreed instructions without reference solutions. Its
   index path is independent of the source directory. The planner appends
   `\n\nTest command: `, the shell-quoted command, and a final newline identically
   for every agent. Review that final text/hash, not just the input prompt.
5. For every task, the reviewed test-command argv, dependencies and versions,
   original pytest targets, and additional oracle/configuration/helper/data paths
   needing protection. These must name existing original files, not guesses.
   Standard protection is documented in [README.md](README.md#exact-oracle-rules).
6. One complete task-index JSON and one separate full-suite oracle-map JSON, with
   exactly the same 54 `dataset/id` identities. Publish their hashes, dataset
   revisions/assembly recipe, dependency lock information and source-tree hashes.
   The planner's full-plan identity does **not** hash exercise source contents.

## Formats the current code actually accepts

The index has exactly `schema_version: 1` and a `tasks` list. Each task object has:

| Field | Required input |
|---|---|
| `dataset` | `polyglot` or `quixbugs` |
| `id` | Unique within dataset; `[a-z0-9][a-z0-9._-]*` |
| `source` | Actual directory relative to that dataset root |
| `task_file` | Actual UTF-8 text file relative to that dataset root |
| `test_command` | Array of strings beginning `python`, `-m`, `pytest`, `-q` |
| `test_paths` | Optional array of extra protected paths relative to `source` |

Portable relative paths use `/`, with no empty, `.` or `..` components.
Source/extra-protected paths cannot enter `.meta/`. Preparation excludes every
directory named `.meta`, including nested ones. Do not put solutions in task text.

The oracle map is a JSON object: keys are the exact `dataset/id` values; each
value is a nonempty list of reviewed source-relative pytest file/directory targets,
optionally with `::node` selectors. This map configures the Agent oracle.
`test_paths` instead tells the grader about additional protected originals;
neither replaces the other. The runner requires a map containing **exactly the
tasks in its shard**, so filter the full map as shown in [handoff.md](handoff.md).

## Command compatibility blocker

`bench.plan` can preserve additional pytest arguments, but `bench.run` currently
accepts only exactly `["python", "-m", "pytest", "-q"]`; `bench.grade` executes
that fixed command with a separate 180-second process timeout. The architecture
requires `--timeout=5` for QuixBugs `bitcount`, if selected. Do not omit that
requirement to make validation pass: a reviewed agent/grader command adapter and
the appropriate test dependency are needed. No real target names or oracle files
are inferred by this handoff. Planning validates paths/text, not test collection
or runtime dependencies; those require a separately authorized dataset preflight.
