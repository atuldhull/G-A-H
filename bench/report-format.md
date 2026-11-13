# Offline report input contract (version 1)

This is a local interchange format for the benchmark harness and a trusted Bifrost
exporter. It is **not a claim that the current gateway emits this native format**.
No real benchmark costs or results are supplied with this milestone. All numeric
fixtures used to test it live only in synthetic pytest fixtures.

## Inputs and invocation

Run from the repository root:

```powershell
python -m bench.report --plan "C:\benchmark\plan.json" --results "C:\benchmark\results.jsonl" --bifrost-logs "C:\benchmark\bifrost.jsonl" --prices "C:\benchmark\prices.yaml" --seed 1729 --summary bench/report.json --markdown bench/report.md --overwrite
```

The statistical seed is required, is a nonnegative integer, and is recorded. It
controls offline bootstrap sampling, **not independent model runs**. Outputs
default to `bench/report.json` and `bench/report.md`. Existing outputs require
`--overwrite`; outputs must differ from each other and all inputs. No exercise
code, test runner, model, gateway, or network is invoked by this module.

The importable API is `calculate_report(plan_path, results_path, logs_path,
prices_path, seed=...)`, then `write_reports(summary, summary_path, markdown_path,
overwrite=False)`. `render_markdown(summary)` is separately available for tests.
Calculation is standard-library only. It rejects invalid input before publication;
the CLI exits 2 on failure and 0 after writing both reports.

Four explicit local input files are required:

1. A milestone 3 run-plan JSON file. Its complete task/run grid is authoritative.
   Both main agents must have equal positive repeat counts; the twin has one run.
   Task IDs, datasets, run IDs/numbers, prompt hashes, test commands, and 30-step /
   600-second caps must match. A missing task cannot disappear merely because both
   paired result rows are absent. Only tasks selected in this plan are measured;
   completeness does not establish that this is the full intended 34/20 suite.
2. One JSONL result row per planned run, with the exact fields below.
3. One normalized Bifrost session JSONL record per planned run, including an
   explicit completed empty request list for a known zero-call session.
4. One `prices.yaml` snapshot using the JSON-compatible YAML profile below.

JSONL is UTF-8, with one object per line, no blank records, and an optional final
newline. Duplicate object keys, rows, request/session IDs, unknown/missing result
or evidence fields, missing planned records, extra records, inconsistent metadata,
NaN, infinity, negative money/usage, and nonnumeric money are rejected. Monetary
values are JSON numbers, not strings. There are no implicit defaults for missing
measurements and no silent filtering of incomplete pairs.

## Run-result JSONL fields

Each line has exactly these fields:

| Fields | Type and meaning |
|---|---|
| `schema_version` | Integer 1 |
| `data_kind` | `measured` or `synthetic`; same in results, session export, and prices |
| `run_id`, `task_id`, `dataset`, `agent_variant`, `run_number` | Identity copied from the plan; task and one-based run number preserve pairing |
| `task_text_sha256`, `test_command`, `step_cap`, `wall_clock_cap_seconds` | Fairness values copied from the planned run; the command is argv |
| `model` | Planned model; one common model for the experiment |
| `date` | Canonical `YYYY-MM-DD` measurement date, matching its session export |
| `gateway_version` | Nonempty gateway version; one common version across the experiment |
| `solved`, `test_edit`, `timed_out` | Actual JSON booleans from independent grading |
| `pytest_exit_code` | Integer for a completed run; null for a timeout or execution/setup error |
| `error` | Null, or a nonempty diagnostic for an execution/setup error |
| `cost_usd` | Finite nonnegative USD number; recomputed and checked, not trusted |
| `cost_provenance` | Exact object described below |

`solved` must equal a completed pytest exit 0. Timeouts and execution errors need
`solved: false` and a null exit code. An unexplained null exit code is incomplete
data and is rejected. Failed/completed runs still require complete cost evidence.
`test_edit` remains separate from oracle success and is counted as a red flag for
Crocodile. The reporting module does not silently turn a passing oracle into a
failure or hide its test edits.

The provenance object has exactly four string fields:

| Field | Required value |
|---|---|
| `kind` | `bifrost_logs_x_prices_yaml` |
| `session_id` | The matching exported Bifrost session ID |
| `logs_sha256` | SHA-256 of the exact Bifrost JSONL file bytes |
| `prices_sha256` | SHA-256 of the exact `prices.yaml` bytes |

A bare `verified: true` flag, agent/LiteLLM accounting, or unrelated evidence does
not satisfy this schema. The module independently checks file hashes, joins
session and run identity, and recomputes the charge before accepting each row.

## Normalized Bifrost session export

Each JSONL record has exactly `schema_version` (1), `data_kind`, `source`
(`bifrost`), `complete` (true), `run_id`, `session_id`, `model`, `date`,
`gateway_version`, and `requests` (a list). IDs and versions are nonempty strings;
run/session IDs must be unique. Requests may be an explicitly empty list only
when the exporter has verified that the completed session made no calls.

Each request has exactly `request_id` (globally unique nonempty string), `model`,
and `usage`. Usage has exactly four **nonnegative integer** counts:
`uncached_input`, `cache_write_input`, `cache_read_input`, and `output`.
These categories must be disjoint: the adapter must subtract cached portions
from any provider input total instead of charging the same tokens twice.

Every request model must match the session/planned model and be priced. Mixed or
fallback-model comparisons are rejected under this benchmark's same-model rule.
The trusted exporter must gather **all** requests, including failed/unsolved and
timeout-session usage, filter the correct benchmark VK/session IDs, reconcile
late usage, and only then mark a session complete. Do not put raw credentials or
VK values in these files.

This exporter/normalization adapter is an integration requirement, not implemented
here. Hashes establish immutable local evidence identity and arithmetic
consistency; they cannot establish that a fabricated/truncated export is genuine
or that an upstream `complete` assertion is true. Trusted acquisition, review of
the export, and provider-price verification remain required.

## `prices.yaml` profile and exact charges

The file must be named `prices.yaml`. To avoid an additional YAML dependency it
must use **JSON syntax**, which is a YAML 1.2 subset. Arbitrary YAML syntax is not
parsed. It has exactly `schema_version` (1), `data_kind`, `currency` (`USD`), and
`models` (a nonempty object).

`models` maps exact provider-prefixed model IDs to objects with exactly the same
four keys as request usage: `uncached_input`, `cache_write_input`,
`cache_read_input`, and `output`. Each value is the independently verified finite
nonnegative **USD price per million tokens** for that category. This document
intentionally supplies no example prices. Every rate, even an unused one, is
validated; all agents share this single price snapshot.

For each run, cost is the sum over every exported request and category of
`token_count * category_price / 1_000_000`. JSON decimal values are parsed exactly
and rational arithmetic is used for verification. The declared `cost_usd` must
equal the recomputed amount exactly: no rounding tolerance or silent truncation.
Round only in human presentation. JSON summary values use finite binary numbers;
overflow or nonzero monetary underflow is rejected rather than written as a false
zero. An explicit zero request list or zero-priced usage is a measured zero, not
missing cost evidence.

## Statistical rules

- Pass rate is solved runs / completed-or-unsolved recorded runs, by dataset,
  agent, and run number, then averaged over the complete equal-repeat grid.
- Within each task, average Crocodile and mini outcomes over their paired run
  numbers. The reported difference is the mean task difference (Crocodile minus
  mini), in proportions. W/L/T counts compare these task averages, not individual
  stochastic runs. Thus opposing outcomes in different repeats can be a task tie.
- Bootstrap paired **whole tasks** with replacement, retaining each task's run
  cluster, 10,000 times. The 95% interval uses the 2.5th and 97.5th percentiles
  with linear interpolation at `(10000 - 1) * p`. Each dataset/metric gets a
  deterministic `random.Random` stream from SHA-256 of `seed:label:metric`;
  Python version, seed, resample count, and interpolation rule are recorded.
- Non-inferiority uses the pre-registered -10 percentage-point margin. Only a
  lower bound **strictly above -0.10** yields the corresponding result; otherwise
  it is inconclusive. No significance language or automatic savings headline is
  generated.
- CPST sums **every** solved and unsolved run's verified cost and divides by solved
  runs. Zero solved runs yield null/inconclusive, even if a total cost was measured.
- For cost ratios, select run numbers within a task that **both** agents solved.
  Sum each agent's costs on exactly those runs, form one ratio per task, and take
  the geometric mean of task ratios. Bootstrap eligible tasks with replacement,
  exponentiate their mean log-ratio in each sample, then take percentile bounds.
  This resolves the repeated-run ambiguity without giving tasks with more jointly
  solved repeats extra weight. Excluded task IDs and eligible paired run numbers
  are recorded; these are a defined outcome subset, not missing input records.
- No jointly solved runs, a measured zero numerator/denominator in any eligible
  task, or an unrepresentable ratio makes that ratio inconclusive without dropping
  that task. Fewer than two eligible tasks permit a point estimate but no interval.
- Dataset results remain separate; overall figures pool tasks with equal task
  weight and are labelled supplementary. Small samples, degenerate bootstrap
  intervals, contamination, task selection, environment differences, and test-edit
  red flags limit interpretation.

## Outputs and remaining integration

The summary records metadata (model, datasets, task/run counts, per-agent repeat
counts, measurement dates, gateway version), bootstrap settings, all four input
hashes, cost verification status, dataset/overall metrics, test-edit counts, and
unavailable metrics. Inconclusive values carry explicit status/reasons and null
intervals or undefined estimands. Measured zero pass rates/costs remain numeric
zero. Per-run pass rates, task-level paired outcomes/costs labelled by run number,
and eligible/excluded cost-comparison tasks are in JSON.
No token savings, race/reservation overshoot, or red-team scores are fabricated.

Synthetic inputs may be calculated by the API for tests and rendered with an
unmistakable test-data heading, but `write_reports` and the CLI reject synthetic
publication. The checked-in `report.json` / `report.md` contain only an incomplete
status because no real verified data exists. They are not synthetic scorecards.

The future harness must join independent grader outputs with planned identity,
dates and versions, and reconciled Bifrost evidence. It must also agree this
normalized export and price profile with Part 2, pin datasets/dependencies,
enforce execution fairness, and review measurement scope before replacing the
status artifacts with real reports. No other part's code or shared contracts are
changed by this module.
