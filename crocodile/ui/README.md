# Static task quote: Person 4 / Person 1 interface

This milestone supplies reusable static quote data and a literal terminal
rendering. It does not register `crocodile quote`, modify Person 1's `cli.py`, or
change `contracts.py`. No agent or gateway implementation is imported. Python
3.12+ and the standard library are sufficient. The parent `crocodile/` package
and CLI packaging remain Person 1's ownership; the UI works as a namespace package
in the current repository without creating a parent `__init__.py`.

## Function contract (v1)

```python
from crocodile.ui import (
    BudgetSnapshot, RungPrice, StaticQuote, UsageEstimate, quote_task, render_quote,
)

quote_task(
    task: str,
    repository: str | os.PathLike[str],
    *,
    pricing: Mapping[str, RungPrice | None] | None = None,
    budget: BudgetSnapshot | None = None,
    usage: UsageEstimate | None = None,
    permitted_text: Sequence[str | os.PathLike[str]] = (),
    rungs: Sequence[str] = ("cheap", "strong", "local"),
    ascii_only: bool = False,
    max_entries: int = 2000,
    max_text_bytes: int = 131_072,
) -> StaticQuote
```

The snippet describes the signature; `os`, `Mapping`, and `Sequence` are type
names, not additional CLI parameters. Inputs are explicit, and unknown values
are represented by `None`, never by substituted zeros:

- `RungPrice(model, input_usd_per_million, output_usd_per_million)` binds one model
  to its caller-supplied **uncached input** and output USD-per-million rates. Money
  accepts a decimal string, `Decimal`, integer, or finite float. A missing rate
  is `None`; omit a rung or pass `None` when its price is unknown. Prices are not
  loaded from the target repository, a gateway, an environment variable, or a
  model. The UI supplies no default provider prices and does not assume local
  inference is free.
- `UsageEstimate(input_tokens, output_tokens)` is the caller's **total task-level
  estimate**, shared across the displayed rungs. Counts must be nonnegative
  integers. It is not actual usage or an inference from the task's output needs.
- `BudgetSnapshot(remaining_usd, limit_usd=None, as_of=None)` is an explicit local
  snapshot. Unknown remaining budget stays unknown even if its limit is known.
  Zero remaining budget is a known zero. Negative/non-finite amounts and remaining
  amounts above a supplied limit are rejected. The optional `as_of` is a caller
  label; the quote does not fetch, refresh, or reserve budget.
- `permitted_text` is an explicit allowlist of at most 32 repository-relative text
  paths. No repository file contents are read by default. Native backslashes and
  forward slashes are accepted in this allowlist.
- `rungs` can restrict the display, for example `("local",)` after the caller's
  confidential-mode policy has determined what is permitted. This is display
  selection, not routing or a security-mode detector.

An empty/whitespace task, missing path argument, malformed inputs, negative or
non-finite amounts, invalid rungs, and invalid limits raise `ValueError`. Missing
or unreadable repository directories and missing/blocked permitted files return
structured warnings and unavailable/partial inspection instead of inventing a
successful inspection. A file or symlink/junction cannot be the repository root.
Explicit UNC/network paths are refused without inspecting them.

`StaticQuote.data` is a JSON-compatible dictionary with `schema_version: 1`:

- `method: "heuristic v1"`, `estimated: true`, repository, inspection status,
  permitted filename observations, text read statuses, and warnings.
- Matched, missing, and ambiguous task filename references. Relative references
  with common source/text extensions are recognized, with native Windows case
  handling. A bare basename is ambiguous if several allowed files share it.
- An `observed_input_token_proxy`, its exact character-based rule, and the
  separate caller usage estimate (or null).
- Explicit budget amounts/as-of label and per-rung model, supplied rates,
  estimated cost, reason for an unavailable cost, and a tri-state
  `estimated_within_remaining` (true, false, or null).
- `estimated_range_usd: null` for every rung, and explicit limitations.

Money in structured output is an exact decimal **string**, or null when unknown;
no `Decimal` or non-finite float leaks into JSON. `StaticQuote.rendering` is the
readable literal terminal string. `render_quote(result.data, ascii_only=True)`
can re-render existing data without scanning the repository again. Text renderings
escape terminal controls and Unicode formatting/bidi controls. ASCII mode also
escapes every non-ASCII character. No emoji, terminal actions, or Rich markup are
emitted. Rich callers must print this string **literally, with markup disabled**.

## What is estimated, and what is unknown

The observed token proxy is:

```text
ceil((task characters + matched relative-filename characters + permitted-text characters) / 4)
```

It is a rough size of inspected text, not a model tokenizer, prompt-size promise,
or prediction of session length. It never fills in missing `UsageEstimate` data.
Test declarations are regex matches of `def test_*` / `async def test_*` in permitted
text, not pytest collection. Strings can produce false positives and dynamic tests
are not discovered. No text read means a null count, not a measured zero tests.

Only with complete permitted inspection, no recognized missing/ambiguous filename,
an explicit usage estimate, and both explicit rung rates does cost become:

```text
(estimated_input_tokens * input_rate + estimated_output_tokens * output_rate) / 1_000_000
```

The calculation uses exact rational arithmetic; the terminal labels it estimated
and displays approximately two significant digits. An uncalibrated "80% range"
would imply evidence this milestone does not have, so no probability interval is
invented. Cache savings, retries, extra turns, tool output, fallback chains,
provider/gateway fees, and local compute expenses are not inferred.

Budget comparison additionally requires an explicit remaining amount. It means
only that this supplied estimate is within or above that supplied snapshot. It
does **not** guarantee a whole task fits, recommend a cloud rung, or enforce a
budget. Missing usage, price, budget, or inspection evidence produces an unknown
comparison, including on the local rung. The Part 2 reservation layer remains
the authority before any actual model call.

## Static inspection boundaries

Only local, stable repository trees are supported. Filename enumeration is bounded
to 2,000 entries by default. `.git`, `.meta`, virtual environments, dependencies,
caches, `.aws`, `.ssh`, `.codex`, `.agents`, obvious credential/secret directories,
`.env` / `.env.*`, and key/certificate names are excluded from the permitted view. Symlinks,
junctions, special entries, unreadable entries, and exceeded limits make inspection
partial. Excluded directories are not traversed and cannot be text-allowlisted.

Allowlisted text must have a `.py`, `.md`, `.rst`, `.txt`, `.toml`, `.ini`, `.cfg`,
or `.json` suffix, stay within the repository, and consist of bounded UTF-8 text
without NUL bytes. Absolute/traversal/drive/ADS paths and sensitive paths are
blocked. The total text byte budget is 128 KiB by default (one extra byte may be
read to detect overflow). Source contents are counted, never echoed, evaluated,
compiled, imported, or executed. Even an explicitly permitted malicious
`conftest.py` is only read as bytes/text; no pytest collection occurs.

Reference recognition is a heuristic for simple relative names, not a full path
parser or dependency analyzer. Absolute names, names containing spaces in task
prose, generated files, and external dependencies are not inferred. A permitted
text path may contain spaces. Inspection completeness refers to the allowed view
and configured bounds, not proof of task feasibility. This does not implement an
OS sandbox or prevent concurrent filesystem changes or transport underneath a
mapped/mounted filesystem; the caller must supply stable local paths and its
approved read policy. It makes no explicit network, Bifrost, model, or tool calls.

## Person 1 wiring checklist (no change to their files here)

1. Register the Typer `crocodile quote TASK --repo PATH --ascii` command and call
   `quote_task` directly, without invoking the agent loop or collecting tests.
2. Obtain model prices and an optional existing budget snapshot from trusted,
   already-local inputs owned by Part 2. If unavailable, pass `None`; quoting must
   not start Bifrost, refresh cloud budgets, load cloud keys, or call a model.
3. Pass a documented static task-usage heuristic as `UsageEstimate` only when
   one exists; otherwise leave it unknown. A character count alone is not total
   usage. Do not silently substitute the architecture's illustrative costs.
4. Apply the existing security/read policy to `permitted_text`, and pass only
   permitted rungs. The UI never grants execution consent or decides confidential
   routing. Pass `--ascii` through as `ascii_only`.
5. Print `result.rendering` literally through the CLI's Rich/plain console.
   If structured output is needed, serialize `result.data` with `json.dumps`.
   Catch invalid-input `ValueError` as a readable CLI usage error. Keep unknown
   values unknown and display inspection warnings.
6. The run command can show the same static quote before spending. Actual
   approvals, journal events, reservations, and receipt accounting stay with
   their owners; this quote has no side effects or enforcement authority.

The interface is deliberately owned here rather than added to shared contracts.
Part 1 can import the public classes/functions from `crocodile.ui` when wiring
the real CLI. No external team message or change to another owner's files is part
of this handoff.

## Validation

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider crocodile/ui/tests/test_quote.py
python -m ruff check --no-cache crocodile/ui
```

Tests use synthetic repositories and synthetic prices. They guard imports,
process execution, and network APIs, check that only permitted files are opened,
exercise a malicious `conftest.py` canary, and check source bytes are unchanged.
They also cover missing data, zero versus unknown, bounds, invalid inputs,
Windows/POSIX path spellings, conditional budget comparisons, and literal ASCII
rendering. No dependencies are installed by the utility or tests.
