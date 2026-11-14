# Benchmark report: incomplete

No verified benchmark run results, Bifrost session export, or `prices.yaml`
snapshot have been supplied. No benchmark calculations have been published.
The companion `report.json` records unavailable measurements as null, not zero.

| Metadata | Measured value |
|---|---|
| Model | Unavailable |
| Dataset/task sets | Unavailable; intended Polyglot and QuixBugs sets are not measured |
| Task count | Unavailable |
| Independent runs | Unavailable |
| Measurement date | Unavailable |
| Gateway version | Unavailable |

Pass rates, paired differences, win/loss/tie counts, CPST, and jointly solved cost
ratios are **inconclusive: verified input data is missing**. Token savings,
budget-race/reservation overshoot, and red-team results are also not supplied.
None of these statuses is a measured zero. Synthetic fixtures exist only in tests
and are not evidence for benchmark claims.

The reporting utility verifies a complete planned run grid, joins by task ID and
run number, checks local evidence hashes, and recomputes costs from Bifrost token
usage and a prices snapshot. CPST includes solved and unsolved costs. Paired
statistics first average repeats within tasks; confidence intervals use 10,000
whole-task bootstrap resamples and an explicitly recorded statistical random seed.
No model-run seeds are implied.

Joint-cost ratios use the same jointly solved run numbers within each task,
then a geometric mean across eligible tasks. Zero joint costs or fewer than two
eligible tasks prevent an interval. Non-inferiority requires the pass-difference
interval's lower bound strictly above -10 percentage points.

Local hashes establish evidence consistency, not upstream authenticity. Small
samples, contamination, selected task scope, environment differences, and test
edits remain limitations. Whole-task resampling preserves paired repeats but does
not remove these limitations. No significance or savings claims are made.

See [README.md](README.md) for exact schemas, calculation rules, and the offline
report CLI. Replace these status artifacts only with a reviewed report generated
from complete measured inputs; `--overwrite` is required.
