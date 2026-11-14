# In-process runner and attempt evidence

`bench.run` connects supported planned runs to the merged Agent and independent
grader. This milestone was validated only with synthetic tasks and injected fake
agents/approval sessions. It does not publish benchmark results or cost claims.
It uses the standard library plus existing bench utilities; live Agent runtime
dependencies remain those declared by the merged application.

## API and explicit execution

```python
run_plan(plan_path, output, *, oracles,
         agent_factory=None, session_factory=None, scratch_parent=None,
         security_options=None, retry_incomplete=False, clock=time.monotonic)
```

Returns all terminal attempt records, including earlier attempts on resume.
Inject **both** factories for synthetic validation. `agent_factory` accepts the
merged Agent constructor; `session_factory` accepts `ApprovalSession.for_bench`'s
arguments. Omitting both lazily loads those real APIs. Importing `bench.run` does
not load live services. No code in the runner accesses credentials or Bifrost
databases; real Agent execution can contact services and incur charges.

CLI shape for a **future authorized execution**, not a command run for validation:

```text
python -m bench.run --plan PLAN.json --output NEW_RUN_DIRECTORY --oracles ORACLES.json --execute
```

Without `--execute`, the CLI exits 2 before loading the oracle file or services.
For nonexecuting planning use `bench.plan --dry-run`. No dependency installation,
gateway configuration, or credential handling is performed by this utility.

`ORACLES.json` maps **exactly the selected task IDs** to reviewed nonempty lists of
pytest targets, for example this synthetic mapping:

```json
{"polyglot/synthetic": ["test_solution.py"]}
```

Targets are relative files/directories, optionally with pytest `::node` selectors.
They must exist in the frozen original. Choose targets covering the agreed suite;
these are not executable argv, shell scripts, or `test_paths` fixture data. No test
collection is done to guess targets. This runner currently refuses any planned
command other than exactly `python -m pytest -q`: custom arguments require an
agent/grader adapter, not a silently changed authoritative command.

The plan must retain 2 Crocodile + 2 mini + 1 all-off runs in its sorted
task/variant/repeat order. Each mini entry produces an explicit `blocked` /
`MissingMiniRunner` record at its planned position, without invoking Agent or
creating an approval session. The supported runs continue in order. This is
incomplete 3-of-5 execution support, never substitution or full-suite completion.
The current CLI therefore exits 1 with the blocked mini attempts; status 0 must
not be interpreted as benchmark/cost verification in any future extension.

## Per-attempt protocol and caps

Before copying any exercise, the runner allocates unique attempt and runner-session
UUIDs and a fresh local temporary workspace. It calls `for_bench` on that empty
direct child of the trusted scratch parent, then freezes the original into the
attempt artifacts and calls `populate_workspace(original, sec.repo_root)`. This
new preparation API validates the tree, rejects links and overlaps, excludes every
`.meta/` directory, and populates an existing empty root **without replacing its
identity**. The older `prepare_workspace` API still rejects existing destinations.
A failed population can leave partial contents; close the session before removing
the temporary root. Inputs and scratch directories must be stable and trusted.

Agent receives the frozen task text, explicit oracle list, `approve_mode="auto"`,
the actual `security_session=sec`, and `step_cap=30`. Crocodile receives
`flags=None`; all-off receives `flags=set()`. The actual Agent generates its own
session ID; the runner cannot override it with the current constructor. That ID
is persisted immediately after construction and before `Agent.run()`, and must be
unique across attempts. **Use `session_id`, not `runner_session_id`, to join future
Bifrost `x-bf-session-id` rows.** A constructor failure can leave that ID unknown;
such an attempt is incomplete, not a verified zero-cost session.

The merged Agent loop enforces its supplied **30-step cap**. Receipt step counts
over 30, invalid token counts, mismatched session IDs, or declared stubs make the
attempt incomplete. Token counts retain the Agent convention: prompt tokens
include cached tokens. Missing data stays null rather than becoming measured zero.

The **600-second hard deadline is not enforced**: the owner API has no hard
cancellation argument. The runner raises at event boundaries or on late return
and records timeout/incomplete. A blocked model/tool call can exceed 600 seconds
before control returns; no worker thread is abandoned to keep spending. The
timer includes Agent construction/run, starts after preparation, and excludes
the independent grader's separate 180-second timeout. Result fields always say
`hard_deadline_enforced: false`. Part 1 must supply supported hard interruption
and child cleanup before comparable capped live benchmarks.

Every returned bench session has `close_bench()` called in `finally`, including
copy/constructor failures, run exceptions, cooperative timeouts and interrupts.
An Agent-consumed interrupt (`STOPPED: interrupted`) also halts later dispatch.
The runner saves the returned receipt or partial `agent.r` on failure, then
retains a separate final tree and calls `grade_exercise` in a fresh copy with the
frozen original oracle restored. Grading never runs in the Agent workspace or
the original. On KeyboardInterrupt/SystemExit, it preserves available evidence
and defers grading rather than continuing work after the stop.

## Durable records and safe resume

The output directory must not overlap a dataset. It contains:

- `plan.json`: immutable byte-for-byte plan snapshot; `plan_id` is its SHA-256.
- `oracles.json`: immutable reviewed oracle mapping; each attempt also records
  its `oracle_targets`. Resume cannot silently change this execution input.
- `events.jsonl`: append-only attempt-start/workspace/session-binding lifecycle.
- `results.jsonl`: append-only **one terminal record per attempt**, not one mutable
  row per run. Retries have new attempt/session IDs and retain all prior costs and
  evidence for future attribution.
- `attempts/UUID/`: original/final trees, `receipt.json`, `security-events.json`
  and the grader's fresh workspace, result and stdout/stderr artifacts.

Security-event snapshots redact permit-token and credential-named fields instead
of persisting authority-bearing tokens; the source session's event list is not
modified. Part 3 remains responsible for redacting arbitrary command/output text.

JSON writes use flush + fsync. A single-writer exclusive `.runner.lock` prevents
concurrent writers. Resume refuses changed plan bytes, malformed/truncated logs,
duplicate completed run IDs or reused Agent sessions. A lock left after process
termination requires operator review/removal once the original writer is known
to be stopped; the runner never automatically removes a stale lock or truncates
a damaged journal. Filesystem/power-loss guarantees remain those of the host.

On resume, a lifecycle attempt without a terminal result gets an append-only
`interrupted` / `OrphanedAttempt` result, preserving its last recorded session ID.
Temporary trees left by a killed process require inspection; the runner does not
reuse or execute them. A completed attempt, **including a graded failure**, is
never rerun. Blocked/incomplete/interrupted attempts remain untouched unless
`retry_incomplete=True` / `--retry-incomplete` is explicitly supplied. Retries
must later be included in costs; selecting only the cheapest successful attempt
would bias the benchmark. Catchable interrupts close the session and remove the
temporary workspace; forced process termination cannot run Python `finally`.

Terminal fields include plan/full-plan/run/task/attempt IDs, full-plan position,
shard, variant/repeat, actual and runner session IDs, planned and observed models,
steps/usage, UTC start/end, total and agent-phase durations, cap policy, errors,
and evidence paths. Null paths/values mean unavailable, not measured absence.
`agent_claimed_solved` and `agent_status` retain the receipt; the complete grader
result (including `test_edit`) and `independently_graded_solved` remain separate.
`solved` requires completed execution, a completed positive independent grade,
and no execution timeout/error. Test tampering remains a separate red flag.
Exception diagnostics record type and phase; raw exception strings are omitted
because they may contain headers or task data.

## Remaining integration gaps

Every result has `comparison_ready: false` and `cost_attribution.status:
incomplete`. `receipt_cost_usd` is retained as unverified evidence;
`authoritative_cost_usd` stays null. No cost is computed or promoted to a claim.

The next cost adapter must read Bifrost `logs.db` **read-only**, verify bench VK
and actual Agent session attribution, include failed/late calls and all retries,
normalize cache read/write/uncached/output counts, and price a hashed snapshot of
the agreed `prices.yaml`. Missing/ambiguous attribution is incomplete. The >1%
receipt-versus-log cost comparison is pending that evidence, not falsely passed.
Native gateway prices and the offline reporter's normalized interchange differ;
conversion plus source hashes is still required. These attempt records deliberately
are not the reporter's verified-cost input schema and cannot be published directly.

Mini still needs its separate pinned 2.4.6 environment, WSL path/process adapter,
identical task/model/test/cap/cache settings, session headers, receipt/usage capture
and independent grading. Preserve its two planned slots. The runner also does not
configure the bench VK, disable owner-default escalation/fallback/sampling, or
initialize shared integrity/budget state. Trusted callers may supply initialized
`integrity`/`confidentiality` objects through `security_options`; absence is not
proof of protected state. Coordinate live fairness and hard-deadline APIs with
Parts 1–3 before the three-task live smoke. No paid/live run was done here.
