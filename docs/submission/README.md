# Crocodile: terminal coding agent with approval and spending controls

Reviewable submission copy, prepared 2026-11-15. This is the Person 4 submission
README; publishing changes to the shared root README requires a separate focused
PR and owner review. Nothing in this pack has been submitted externally.

Crocodile combines an agent loop, test verification, console approvals and a
Bifrost gateway adapter. The repository includes static quotes, status/receipt
rendering, confidential-routing checks and independent benchmark grading.
Implemented token-management features are experimental: this pack makes no
measured efficiency claim.

## Verified evidence

[Person 4 CI run 43714693880](https://github.com/atuldhull/G-A-H/actions/runs/43714693880)
tested commit `3f26769b15ac9583f3b5a3a3dd27928453828b35` on Python 3.12,
2026-11-15. Both jobs passed:

| Checks | Windows CI | Ubuntu CI |
|---|---:|---:|
| Reviewed architecture red-team groups | **15 passed / 0 failed / 0 skipped** | **13 passed / 0 failed / 2 skipped** |
| Supplemental security tests (separate) | 5 passed | 5 passed |
| Fixture/inventory framework (separate) | 48 passed | 48 passed |
| Synthetic bench/UI tests | 463 passed / 2 skipped | 464 passed / 1 skipped |

Ubuntu skips group 9 because the required available/pinned Windows `cmd` ASK
subcase cannot execute there, and group 12 because it requires the Windows
filesystem, genuine junction and 8.3 alias. These are unexecuted groups, not
security passes. Windows CI executed all 15 groups; the local desktop separately
skipped group 12 when junction creation was unavailable. Bench/UI skips are
platform-specific FIFO or junction checks. Ruff passed the workflow's explicit
correctness rules. See [reviewed cases](../../redteam/README.md) and
[Ritika's expectations](../../redteam/review.md).

The tests demonstrate bounded, observable behaviors:

- Real Agent approval tests refuse test execution and retain an unsolved receipt
  saying `TESTS NOT RUN (no consent)`; canaries and process counters check refusal.
- Confidential-mode tests use `.crocodile/confidential`, actual owner policies and
  an in-memory HTTP transport. They check local-only routes, empty fallback
  chains, forced web-tool refusal, session-bound egress records and no Tavily
  sends. This is deterministic integration evidence, not live gateway proof.
- Budget unit tests exercise reservation/reconciliation and exhaustion denial
  with a disposable SQLite ledger. Both focused tests passed locally on
  2026-11-15. This is not a measured budget-race or production overspend result.
- Static quote generation has no model/code-execution side effects in the
  reviewed canary case. Quotes and receipt estimates must remain labeled as
  estimates; independent test outcomes determine verified benchmark solves.

## Benchmark status: incomplete

Immutable **gemini-54-v4 plans are validated: 54 tasks / 270 planned slots**,
with shard counts **70 / 70 / 65 / 65** and a prepared **3-task / 15-slot smoke**.
These are plan counts, not completed runs. Comparable results remain
**incomplete**. Strict validation exits 0 with no runtime/price drift;
`--require-comparable` exits 1. No official shard is authorized by this pack.

Pass rates, CPST, savings, paired cost ratios and benchmark completion are
unavailable, not zero. No dollar results or accuracy comparison are published.
See [benchmark status and gates](benchmark-status.md), the
[unchanged incomplete report](../../bench/report.md) and
[v4 handoff](../../bench/team-handoff-v4.md).

## Review and reproduce without model calls

```powershell
$Python = 'C:\Users\gunda\venvs\crocodile\Scripts\python.exe'
& .\scripts\prep.ps1 -Python $Python
& $Python -m pytest -v -ra -p no:cacheprovider redteam/tests/test_security_cases.py
& $Python -m pytest -q -ra -p no:cacheprovider redteam/tests/test_framework.py
& $Python -m ruff check --isolated --target-version py312 --select E4,E7,E9,F --no-cache bench crocodile/ui redteam
```

Prep checks prerequisites and prints commands; missing demo inputs or live
evidence produce `INCOMPLETE` / exit 1. It installs nothing, starts no service,
reads no credentials and changes no ledger, workspace or Bifrost logs.
Live recording needs separate owner preparation and authorization.

## Demo and submission review

- [Short form text and AI-use disclosure](description.md)
- [Six-slide outline and under-three-minute script](demo.md)
- [Evidence checklist, owners and missing recordings](checklist.md)

No OS sandbox is claimed: approved tests execute repository code. A determined
same-user process can bypass local checks; the gateway budget is the independent
cap. Public benchmark tasks may be contaminated by training data. V4 retains
accepted hard-stop-containment, mini output-cap, cache and sampling limitations.
See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) for licensing/attribution.
