# Demo outline and video script — recording pending

Target **2:55**, subject to Atul confirming the event's actual time limit.
All clips below **need recording**; no video is supplied by this pack. Use an
owner-reviewed disposable demo exercise, not a benchmark task. Never show keys,
prompts containing private data, raw gateway payloads or personal files.

## Six slides maximum

| Slide | Content and allowed evidence | Recording owner / status |
|---|---|---|
| 1 | Crocodile: terminal coding with approval and spending controls. No savings headline. | Person 4: title/edit pending |
| 2 | Working agent: static estimated quote, approved edit, real test outcome and receipt. Unsatisfied tests remain unsolved. | Atul: live recording pending; no model call made for this pack |
| 3 | Approval refusal: deny initial test consent, retain zero test runs and `TESTS NOT RUN (no consent)`. README-steered network action is denied before prompting; renewed test consent is red. | Ritika / Atul: recording pending; real-API tests available |
| 4 | Confidential routing: `.crocodile/confidential`, local allowlist, empty fallback chain and refused forced web tool. Label transport-injected proof explicitly. | Vivek / Ritika: deterministic proof clip pending; live gateway clip separately pending |
| 5 | Budget: reserve/reconcile and exhaustion denial in disposable SQLite unit fixtures; live stop/banner only if actually recorded. No race/overspend number. | Vivek: recording pending; two focused budget tests passed locally |
| 6 | Proof and honesty: Windows CI 15/15 groups, Ubuntu 13 plus two explained skips; v4 54/270 plans validated, comparable results incomplete. Limitations, licences and AI disclosure. | Person 4: CI/status screen recording pending |

## Concise script and shot list

| Time | Screen / spoken script |
|---|---|
| 0:00–0:15 | Title. “Crocodile combines a coding agent with explicit approval, verification and spending controls. Here is what we can demonstrate today.” |
| 0:15–0:50 | **LIVE CLIP NEEDED — Atul.** Static quote, a harmless task in the reviewed demo repo, approval, edit and actual visible test outcome. “The quote is a heuristic estimate. Actions and test runs use the real approval path; the receipt distinguishes verified results from unverified work.” Do not narrate a solve unless the shown tests verify it. |
| 0:50–1:20 | **CLIP NEEDED — Ritika/Atul.** Record group 2's actual Agent/refusal test with visible assertions or a reviewed interactive reproduction. “Refusing consent means zero tests run. The receipt says TESTS NOT RUN, not solved.” Caption deterministic replay when using tests. Separately show README network denial before prompting; do not manufacture a red curl prompt. |
| 1:20–1:50 | **CLIP NEEDED — Vivek/Ritika.** Record groups 5/6, label `REAL POLICIES / IN-MEMORY HTTP TRANSPORT / NO MODEL CALLS`. “The private marker selects local routing. Cloud tags and forced web search are refused. We check the complete disposable session evidence and empty fallback chain.” Do not label this live Bifrost or claim it proves all machine traffic stays local. |
| 1:50–2:15 | **CLIP NEEDED — Vivek.** Record the two actual budget unit tests below, label `SYNTHETIC LEDGER TESTS`. “These isolated tests exercise reservation, reconciliation, and denial when the reservation exceeds the remaining budget.” A live budget-stop recording is still pending; no zero-overspend or race result is claimed. |
| 2:15–2:55 | **CLIP NEEDED — Person 4.** Open the linked CI logs showing all 15 Windows groups and Ubuntu platform skips. Show benchmark status. “The v4 plan validates 54 tasks and 270 slots. Comparable measurements are incomplete, so there are no savings or cost-per-solved-task claims. Approved code can execute; this is not an OS sandbox.” End with repo URL, licences and truthful AI-use disclosure. |

Commands for deterministic proof clips (no paid services):

```powershell
& $Python -m pytest -v -ra -p no:cacheprovider 'redteam/tests/test_security_cases.py::test_security_case[02-rt_ladder_requires_consent]'
& $Python -m pytest -v -ra -p no:cacheprovider redteam/tests/test_security_cases.py -k '05- or 06-'
& $Python -m pytest -v -p no:cacheprovider tests/gateway/test_budget.py::test_budget_reservation_and_reconcile tests/gateway/test_budget.py::test_budget_exhaustion_raises_denied
```

The working-agent clip is a separate, manually authorized recording. Prep prints
the actual CLI shape after the operator supplies reviewed repo/task/oracle/output
paths. Do not use `--yes`, benchmark `--execute`, a fabricated test file or a
synthetic model transcript presented as a live model response. Preserve native
receipts and actual test evidence; cut no refusal/error so as to imply success.

Before release, owners must review captions, screen every frame for secrets,
confirm the event duration and supply a public video URL. Do not substitute a
mocked clip for an unrecorded live requirement. Failover/takeover and live Tavily
integration recordings, if required by the event, remain Vivek/Atul deliverables.
