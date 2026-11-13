# Status and receipt interface (Person 4 milestone 6)

These are **pure value-to-text functions**. They do not read or parse a journal,
open/stat repository files, execute code/tests, collect plugins, query a gateway,
look up the clock, or contact a model/service. They return strings rather than
printing or mutating caller state. Inputs must be already-normalized snapshots
provided by Person 1 and Part 2; no live integration is implemented here.

## Public imports and signatures

```python
from crocodile.ui import (
    SavingsEstimate, SessionMoney, SessionReceipt, SessionSnapshot, TestOutcome,
    TokenUsage, VerificationState, render_receipt, render_status,
)

session = SessionSnapshot(model="caller-reported-model", phase="fix", mode="public")
status_text = render_status(session, ascii_only=True, max_width=240)
receipt_text = render_receipt(SessionReceipt(outcome="stopped", session=session),
                              ascii_only=True, max_width=240)
```

Both functions accept `ascii_only: bool = False` and `max_width: int = 240`.
`max_width` is a per-line **character bound**, from 80 to 1000. It is not a Unicode
terminal-cell-width measurement. Narrow displays explicitly truncate with an
ellipsis (`...` for ASCII); trailing status fields can be omitted by truncation.
The public/confidential mode is pinned at the start of the status. Receipt lines
have formatter-owned labels/newlines and independent bounds. Print these strings
literally, with Rich markup/highlighting disabled; styling can be added to trusted
labels by the eventual CLI adapter, not by interpreting caller text as markup.

## Typed caller values

All input classes are frozen dataclasses. Every field below defaults to `None`
unless noted; unknown is never silently converted to zero. Text fields accept
plain strings, not path objects or arbitrary objects with executable conversion
hooks. Counters accept nonnegative 64-bit integers, never bools or floats.
Malformed enums, counts, money, or incompatible counts raise `ValueError`.

| Type | Fields and semantics |
|---|---|
| `VerificationState` | `syntax`, `lint`: `passed`, `failed`, `not_run`, `pending`, or None. `affected_passed`, `affected_total`, `failing_oracles`: optional observed counters. Passed cannot exceed a known total. These checkpoints do not establish a final solved outcome. |
| `TokenUsage` | `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`; `estimated=True` by default. Input is the normalized total of disjoint uncached input, cache-write input, and cache-read input, not a provider counter that may double-count caching. Known cache counts cannot exceed a known input total. |
| `SessionMoney` | `session_usd`, `quote_usd`, `today_spent_usd`, `today_limit_usd`; `cost_estimated=True` and `budget_estimated=True` by default. Values accept decimal strings, Decimal, finite float, or integer, and must be nonnegative. Set estimate flags false only for explicitly reported/reconciled facts. The quote is always labelled estimated. |
| `SavingsEstimate` | `total_tokens`, `spilled_tokens`, `unchanged_tokens`, `masked_tokens`, `calls_avoided`. Token savings are always labelled **estimated, first-order**. The renderer never sums components, which can overlap, and never infers avoided calls from the number of green tests. |
| `SessionSnapshot` | `model`, `rung` (`cheap`, `strong`, `local`), `turn`, `phase` (`reproduce`, `fix`, `verify`, `done`), `mode` (`public`, `confidential`), `task`, `repository`, `session_id`, `escalations`. Nested `verification`, `tokens`, `money`, and `savings` default to their empty value objects. |
| `TestOutcome` | `source` (`test_runner`, `grader`, `controller`, `model`), `verified`, `scope` (`full`, `partial`, `agent`), `tests_run`, `oracle_frozen`, `pytest_exit_code`, `timed_out`, `error`, `passed`, `failed`, `regressions`, `oracle`, `consent_granted`. Booleans are optional and distinguish unknown from false. Exit code is a signed 64-bit integer or None; error/oracle are strings or None. |
| `SessionReceipt` | `outcome` (`solved`, `partial`, `stopped`, `tests_not_run`), default `stopped`; `session` defaults to an empty `SessionSnapshot`; `test_outcome`, `reason`, and `handoff` are optional. Requested outcome is not proof. |

Unknown counts, cache percentage, costs, budgets, model, turn, and phase remain
`unknown` in the status or receipt. Optional task/path/handoff/savings lines can be
omitted when unavailable. Explicit zero counts or amounts render as zero. A cache
percentage is calculated only with a known positive normalized input total and a
known cache-read count; zero divided by zero stays unknown. Display counters are
abbreviated (K/M/B), not invented precision. Monetary presentation rounds to six
significant digits but never supplies an absent amount.

The budget marker `WARN >=80%` appears only when both spent and a **positive**
limit are supplied and spent is at least 80% of the limit. Spent may exceed a
limit: an observed overrun is displayed rather than rejected or hidden. Zero
limits display explicitly without a meaningless percentage. The eventual Rich
adapter may color this trusted warning amber. These displays do not enforce or
reserve budget.

`LOCKED confidential` reflects the caller's explicit policy snapshot. The UI does
not detect confidentiality, verify a local-model allowlist, route a request, or
prove zero egress. The caller must obtain mode from Part 3 and routing/model state
from Part 2, rather than a model or repository assertion. Unknown mode is explicit.

## Evidence-gated receipt outcomes

A full `SOLVED` heading requires **all** of:

- Requested `solved`; source `test_runner` or `grader`; `verified=True`.
- `scope="full"`, `tests_run=True`, and `oracle_frozen=True` for the verified
  existing/restored oracle, not an agent-authored or edited oracle.
- `pytest_exit_code=0`, `timed_out=False`, and `error=None`.
- No explicitly denied consent, reported failures/regressions, or reported zero
  passed tests. Missing counts remain unknown rather than being printed as zero.

`scope="partial"` can yield only `SOLVED (partial suite)`, with an explicit note
that full task completion is not asserted. A requested `partial` also stays
partial even if the supplied verified scope is full. A requested `stopped` never
upgrades to success, even when prior tests passed.

`TESTS NOT RUN` requires an explicit `tests_run=False` attestation from a controller,
runner, or grader. The `(no consent)` suffix additionally requires
`consent_granted=False`; a missing consent field cannot manufacture that reason.
A missing execution state, model assertion, or known executed tests cannot be
rendered as tests-not-run merely because that outcome was requested. A completed
exit code, positive test counts, or timeout contradict a non-invocation and block
that heading even if `tests_run=False` was also supplied.

Requests lacking acceptable success evidence become `STOPPED`, or `TESTS NOT RUN`
when that fact is explicitly attested. A model statement, `phase="done"`, a
`verified=True` flag on a model/controller source, syntax/lint success, an
agent-authored oracle, timeout/error, or a bare exit code cannot produce SOLVED.
The receipt displays supplied evidence and counts, including oracle integrity,
to explain the outcome. These checks verify consistency of caller attestations;
they cannot authenticate a forged Python object. Only trusted runner/grader
adapters may set verified outcome fields, and they must handle skipped/no-test
suites, oracle identity, consent, and regression policy before attesting a pass.

## Proposed journal-to-snapshot fields for Person 1 / Part 2

This table defines the **UI adapter's required projection**, not an assertion
that these payload fields already exist. It adds no events to the journal and
does not modify `contracts.py`. Agree the mapping before the later integration;
preserve original event sequence/run identity and deduplicate replayed events.
Do not fabricate missing totals by treating absent counters as zero.

| Existing event / trusted source | Fields the adapter must supply |
|---|---|
| `model_call` (Part 2) | Actual `model_used`, `rung`, loop `turn`/`phase`, normalized `usage.input_total`, `usage.output`, `usage.cache_read`, `usage.cache_write`, usage provenance/estimate flag, and session cost/provenance. Map to snapshot model/rung/tokens/money; account for failed/fallback calls and replay deduplication before supplying aggregates. |
| `tool_started` / `tool_done` (Parts 1/3) | Turn/phase, verification stage, observed check status, affected passed/total, and failing frozen-oracle count. Supply counts only when available; source paths/test IDs remain untrusted display text. |
| Trusted test result in `tool_done`, or independent grader output | `source`, `verified`, `scope`, `tests_run`, `oracle_frozen`, `pytest_exit_code`, `timed_out`, `error`, optional passed/failed/regressions counts, oracle ID/path, and consent bound to that invocation. Adapt these into `TestOutcome`; never copy a model's solved claim into this attestation. Independent grader exit/cost artifacts still need the source/scope/oracle attestation mapping. |
| `approval` / controller consent state (Parts 1/3) | Decision/source for test consent, plus actual invocation state. Refusal alone does not prove no earlier test ran. For a non-invocation, use controller-sourced `tests_run=False`, and set consent false only when explicitly denied. |
| `budget_warn` / `budget_stop` and coherent Part 2 ledger snapshot | Session cost, quote estimate if available, today spent/limit, and estimate/reconciliation flags. A missing limit remains unknown; do not query a service from the renderer. |
| `takeover` and loop state (Parts 1/2) | Update actual current model/rung; supply loop escalation count separately. Provider failover and a strategy escalation are different counters. No failover banner is implemented by this milestone. |
| Engine/journal lever counters (Part 1) | First-order estimated total/spilled/unchanged/masked tokens and explicitly counted deterministic calls avoided. Supply total only if independently defined; do not assume components are additive. |
| Session state / stop capsule (Parts 1/2/3) | Task, repository label, session ID, requested final outcome, stop reason, handoff capsule, and Part 3/2 operating mode. Feed already-aggregated values directly to the UI. No journal parsing or resume is implemented here. |

Costs default to estimated until the caller explicitly identifies reported facts.
Budget/time snapshots may be stale; changing presentation flags does not verify
accounting. Model output and repository text must never set the attestation,
consent, mode, or provenance flags. All controller/runner observations must refer
to the correct session and latest relevant invocation, not an earlier green test
or an unrelated approval. The UI has no authority to repair journal state.

## Untrusted text and purity

Model, task, repository, session ID, test/oracle, reason, handoff, and error strings
are escaped and field-truncated before display. Terminal controls (ESC, CSI, OSC,
CR/LF, backspace), Unicode line/paragraph separators, bidi/format controls, square
brackets, pipes, and literal backslashes cannot inject terminal actions, Rich tags,
new receipt rows, or extra status columns. ASCII mode escapes all other non-ASCII
characters. These are literal display strings, not paths/commands to execute or
Rich markup to interpret; escaped test IDs should not be copied as raw commands.

Only formatter-owned newlines exist in a receipt, and status is one line. Field
limits and the configurable line bound keep very long inputs bounded; mode and
final outcome headings remain visible. No filesystem object, gateway/journal
client, command callback, or model client is accepted. Existing quote inspection
is separate and is never called by either session formatter.

Tests use synthetic snapshots, block filesystem/process/network/dynamic-import
APIs, and verify deterministic output and unchanged input objects. They cover
each outcome, proof gaps, unknown/zero values, confidentiality, budget thresholds,
huge text, malicious terminal/Rich strings, and ASCII/length bounds.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider crocodile/ui/tests
python -m ruff check --no-cache crocodile/ui
```
