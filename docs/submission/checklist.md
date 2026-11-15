# Submission checklist — prepared, not submitted

Prepared 2026-11-15; Person 4 owns this pack and `scripts/prep.ps1`. Checked source
baseline: `3f26769b15ac9583f3b5a3a3dd27928453828b35`. The pack's own revision is
its subsequent Git commit. Items marked pending have no supplied completion
evidence. No final upload, public video or external submission is implied.

## Exact evidence locations

| State | Item / exact path or URL | Owner / next action |
|---|---|---|
| Verified | [CI run 43714693880](https://github.com/atuldhull/G-A-H/actions/runs/43714693880), commit `3f26769b15ac9583f3b5a3a3dd27928453828b35` | Person 4: Windows 15/0/0 architecture groups, Ubuntu 13/0/2; supplemental 5 and framework 48 on each. Preserve platform qualification. |
| Verified | `redteam/tests/test_security_cases.py`, `redteam/tests/gateway_cases.py`, `redteam/review.md`, `redteam/README.md` | Ritika / Person 4: real-policy, injected-transport evidence is explicitly not live gateway evidence. |
| Verified locally | `tests/gateway/test_budget.py::test_budget_reservation_and_reconcile` and `::test_budget_exhaustion_raises_denied` | Vivek / Person 4: 2 passed on Windows Python 3.12.10; synthetic ledger only, no budget-race number. |
| Prepared | `docs/submission/README.md`, `description.md`, `demo.md`, `benchmark-status.md`; `scripts/prep.ps1` | Person 4: final language/video assembly; owners review their claims. |
| Static/runtime checked | `scripts/prep.ps1`; 120-word short description; six-slide outline; valid local Markdown links | Person 4: prep ran in PowerShell 7.6.9 and reported expected incomplete prerequisites. Windows PowerShell 5.1 refused file execution (`AuthorizationManager check failed`); policy was not changed, so its runtime remains unverified. |
| Verified plan, not execution | `bench/configs/gemini-benchmark-v4.json`, `bench/team-handoff-v4.md`, `bench/gemini-54-v4.md` | Person 4: fingerprint and input/runtime pins unchanged; strict exit 0 / comparable exit 1. |
| Incomplete measurement | `bench/report.md`, `bench/report.json` | Person 4: retain null/unavailable statistics; replace only after complete measured grid and reviewed evidence. |
| Conditional evidence only | `bench/evidence/mini-kheapsort-v4-audit.json`, `bench/evidence/mini-kheapsort-replacement-review.json` | Vivek / Atul: served model and complete-session proof still missing. Preserve historical token evidence; no dollar claims. |
| Missing | Sanitized v4 native request/routing proof and closed/flushed complete-session inventory; **no supplied file path** | Atul / Vivek: provide authorized key-free artifacts, exact request/session/VK/model joins, origin and completeness review. |
| Pending review | Historical `3a111322` / unattested rerun-cohort disposition and retry/cost lineage | Atul / reviewer / Person 4: preserve original ungraded failure and unknown cause. |

The verified local external bundle is:

```text
C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\release-gemini-54-v4-20261115
```

Its exact artifact names are `full.json`, `shard-1.json` … `shard-4.json`,
`smoke.json`; matching `*-oracles.json` and `*-attestation.json` files;
`mini-settings.json`, `prices.yaml`, `price-snapshot.json` and
`release-preparation.json`. Real data root:
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\generated-lf-v2-20261115-31f9cef`.
These paths are machine-specific. Historical attestations are not this pack's
new attestation and do not grant execution permission.

## Recordings and release work still required

All paths below are **proposed output names**, not supplied recordings. Set
`$DemoEvidence` to a new owner-approved directory outside the repository; no
directory or recording has been created by this pack.

| Pending item | Proposed evidence path | Owner / acceptance |
|---|---|---|
| Working agent live take | `$DemoEvidence/agent-live.mp4`, `agent-receipt.json`, `agent-test-evidence.txt` | Atul: reviewed harmless demo task, genuine model/gateway, actual consent and test outcome; no benchmark task. |
| Approval refusal | `$DemoEvidence/approval-refusal.mp4`, `approval-proof.txt` | Ritika / Atul: zero tests after refused consent, unsolved receipt; label deterministic replay if used. |
| Confidential proof | `$DemoEvidence/confidential-proof.mp4`, `confidential-proof.txt` | Vivek / Ritika: label transport-injected proof. Separate live clip needs actual local-route/session egress evidence; never claim no system-wide traffic. |
| Budget behavior | `$DemoEvidence/budget-proof.mp4`, `budget-proof.txt` | Vivek: synthetic test proof can be recorded now; any live warning/stop needs its actual sanitized journal/receipt. No invented race or overspend figure. |
| Gateway/Tavily requirements | `$DemoEvidence/gateway-live.mp4`, reviewed sanitized request/event evidence | Vivek / Atul: confirm event requirements; record actual takeover/search if required. Never introduce benchmark fallbacks to stage a demo. |
| Final video | `$DemoEvidence/submission-final.mp4` plus approved public URL | Person 4: owners review captions; frame review for secrets; duration confirmed; uploaded link tested logged-out. |
| AI disclosure / credits | `docs/submission/description.md`, `NOTICE`, `LICENSE` | All owners: confirm tools actually used and third-party attribution. Codex use by Person 4 is confirmed; team-wide declarations pending. |
| Shared root README | Separate focused PR, **not edited in this pack** | Atul / Person 4: use the verified submission copy as the proposed source, review diff/CI; do not copy stale benchmark placeholders or numerical claims. |
| External submission | No confirmation artifact supplied | Atul: verify track, deadline/time zone, form and video limits; approve final text and submit only when separately authorized. |

Comparable benchmark release additionally requires per-machine secure settings,
header/log evidence, valid sealed state and a supported reviewed authorization.
Only then consider the reviewed 3-task/15-slot smoke, audit all evidence, and
decide separately whether official shards may start. Quota/setup/interrupted
attempts stay incomplete; never count them as task failures or zero cost.
