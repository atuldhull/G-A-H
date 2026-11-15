# Parts 3/4 assembled security verification

Verified source: `0aced71f17b8d26d67e05704aebc0d4619b40f41` (Python 3.12).
[Windows and Ubuntu CI run](https://github.com/atuldhull/G-A-H/actions/runs/43694768652).
The later evidence-only commit preserves the tested Python source digest.
Only `person-3` was pushed; this report does not claim a merge into main.

The fixed suite executes real Typer CLI entry points and owner implementations
against disposable repositories/state. Model responses, approval answers and HTTP
provider responses are trusted synthetic fixtures. No live provider result is
inferred from those fixtures. Socket sends and DNS are forbidden; numeric
loopback address validation is allowed without DNS. Runner exit 2 means blocked.
A green CI job may contain explicitly blocked cases, never an implied 15/15.

| Group | Architecture cases | Windows | Ubuntu |
| --- | --- | --- | --- |
| 1 | rt_quote_no_exec | passed | passed |
| 2 | rt_ladder_requires_consent | passed | passed |
| 3 | rt_green_edit_then_tests | passed | passed |
| 4 | rt_child_edits_ledger | passed | passed |
| 5 | px_ollama_cloud_tag | passed | passed |
| 6 | px1_use_gpt, px4_tavily | passed | passed |
| 7 | px3_marker_deleted, px3_repo_flag, px3_nested | passed | passed |
| 8 | rt_readme_curl | passed | passed |
| 9 | rt_amp_newline | passed | blocked |
| 10 | rt_fsmonitor, rt_post_exec_filter | passed | passed |
| 11 | rt_template_rev | passed | passed |
| 12 | rt_paths_windows | passed | blocked |
| 13 | sec_rg_env | passed | passed |
| 14 | test_oracle_edit_red, test_skip_not_green | passed | passed |
| 15 | pipe_yes | passed | passed |

Windows: **15 passed, 0 failed, 0 blocked** architecture groups, plus all three CLI
flows passed. Ubuntu: **13 passed, 0 failed, 2 blocked**, plus all three CLI flows
passed. Group 9 requires cmd, unavailable on Ubuntu; group 12 requires actual
Windows junction/device/ADS/8.3 behavior. The Windows run obtained a real protected
8.3 alias and checked it, rather than treating a literal GIT~1 as evidence.

The immutable per-case artifacts are mirrored in [windows-ci.json](evidence/windows-ci.json)
and [ubuntu-ci.json](evidence/ubuntu-ci.json). They contain exact argv, prompts,
exit statuses, source hashes and observed outcomes. See [review.md](review.md)
for Part 3's corrections to the expected outcomes and API review.

## Real CLI flows

| Flow | Command and exit status | Observable outcome |
| --- | --- | --- |
| README attribution and denied execution | `crocodile run ... --repo FIXTURE --flags none --json-out RECEIPT` -> 1 | Red preview identifies README.md:40; refusal creates no process or execution indicator. |
| Modified, created, removed file undo | `crocodile run ...` -> 1 (no test oracle); `crocodile undo 3 --repo FIXTURE` -> 0 | Modified/deleted files restored, created file removed; target Git HEAD unchanged. |
| Protected-state tamper abort (group 4 and extra CLI flow) | `crocodile run ...` -> 1 | Approved pytest and a separate harmless command change disposable ledgers; HMAC rejects it; integrity event recorded; no subsequent model request or edit. |

The fixtures enter the normal CLI with scripted services; these are not manual
interactive recordings. The complete fixture commands and status receipts are
in the JSON evidence, including the deliberate nonzero exits above.

## Regression fixes and validation

The verification fixed misleading receipt wording after refused baseline test
consent. It also found that rapid same-size edits could reuse Python's timestamp
bytecode cache. Child environments now disable bytecode writes and use a fresh
scratch cache prefix; a preplanted stale-cache regression proves fresh source is
executed. Windows state-location fixtures are marked for Windows, and XDG fixtures
exercise the Linux canonical path. The refusal fixture counts pytest separately
from Ruff. Security policy was not relaxed to accommodate an in-repository venv.

Commands run in both CI environments:

```text
python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache redteam
python -m pytest -q -ra -p no:cacheprovider redteam/tests/test_framework.py
python -m pytest -q -ra -p no:cacheprovider tests
python -c "from redteam.runner import run; code=run('security-report.json'); raise SystemExit(0 if code in (0,2) else code)"
```

Framework: 48 passed in each environment. Ubuntu application regression:
324 passed, 7 platform skips, 160 subtests passed. Windows application regression:
331 passed, 160 subtests passed. Ruff and git diff --check passed on changed Python files.

The first local Windows architecture run found two harness assertion failures;
both were corrected before the final CI run. Its other 13 groups and both CLI
flows passed. Slow duplicate local runs were stopped once equivalent Windows CI
evidence was available; they are not claimed as completed regression runs.
The final corrected numeric-loopback fixture also passed locally on Python 3.12.

## Remaining external dependencies

[Live dependency probes](evidence/live-dependencies.json): Bifrost
127.0.0.1:8080 and Ollama 127.0.0.1:11434 both timed out. No real confidential
model request, independently correlated live gateway audit, live Tavily count or
live canary-hit claim is made. Task 17 remains blocked until those services and
an allowed installed local model are available, with gateway request-ID records.
The synthetic audit passed, but does not close that requirement.

The user confirmed feature freeze has not been declared. Task 18 remains pending;
neither final clip was recorded. [demo-handoff.md](demo-handoff.md) records the
post-freeze capture steps and credential review requirements. No demo numbers
were invented or frozen by this verification.
