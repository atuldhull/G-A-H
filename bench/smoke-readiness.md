# Three-task smoke preparation — execution blocked

Main `18afcdd0b54d6ad1c988763f92231973c4b98a2a` contains both `6167883` and
`5f09a22`. It was integrated into person-4 at
`62842dbf67f99af6dbec534641435a84bbfb99a0`. No person-2 branch was merged directly.
The default runner verifies state integrity and supplies a confidentiality
detector before creating the bench session. Person 4 moved that initialization
inside the protected attempt lifecycle: failure now writes one safe terminal
`incomplete` record, stops the entire queue, and performs no session/copy/model
work. Verification errors are never swallowed. This is synthetic/source evidence,
not verification of a real sealed state DB.

## Prioritized current blockers

The [frozen v1 config](configs/gemini-benchmark-v1.json) remains byte-for-byte
historical, with config ID
`07e9ded30d149ddff5bd3bdccc58e9f691a87b4143072321c84a3c075f6728fe`.
Its original unresolved descriptions are not current status updates. These are:

| Priority | Blocker and exact owner | Smallest observable acceptance check |
|---|---|---|
| P0 | Frozen runtime no longer matches. Person 4: `bench/configs/`, `bench/canonical.py`. | Publish an owner-reviewed successor revision with the accepted runtime hashes and evidence-backed gates. Audit has no unexplained drift; `--require-comparable` succeeds. Never edit v1 to claim it covered newer code. |
| P0 | Native bench profile/VK/sampling and valid sealed state. Person 1: `crocodile/adapters.py::GatewayEgress.chat`, `crocodile/loop.py::Agent.run`; Persons 2/3: shared state initialization. | Approved state verifies read-only; a captured bench request uses Flash-Lite, the actual bench VK identity, no model fallbacks or sampling override. Same state path is bound to gateway/security. Real credentials/state remain uninspected here. |
| P0 | Live gateway/header/schema/cost evidence. Vivek/Person 2: Bifrost service/logs; Person 4: `bench/bifrost_export.py`. | Windows and WSL reach 18080. One separately authorized probe's exact session/VK maps after flush to request ID, actual billed model, terminal status and explicit token categories. Schema matches; complete inventory includes all failed/retried calls. |
| P0 | Hard 600-second deadline and cleanup. Persons 1/3: `crocodile/loop.py`, `crocodile/security/procs.py`, `windows_job.py`; Person 4: `bench/mini_bridge.py`. | A shortened-deadline test with a blocking fake model/tool and spawned descendants terminates the full tree and proves no later requests. Cooperative checks/group watchdog alone do not pass. |
| P1 | Cache/thinking/output-cap/retry parity. Persons 1/2/4: `crocodile/prompt.py`, `loop.py::MAX_OUT`, `bench/mini_bridge.py` and upstream mini query. | Redacted request captures agree with the reviewed policy, including native 4096 versus mini omitted output cap, cache semantics and provider-default thinking; attempt counts reconcile with logs. |
| P1 | Environment and rate evidence. All operators; Person 2: `prices.yaml`; Person 4: canonical/provenance layer. | Each machine supplies matching approved version/dependency profiles and exact native price-snapshot hash, with rate review. Complete costs and all 15 smoke outcomes remain separately required. |

## Person 4 issues resolved in code/tests

- Mini writes the planned task as UTF-8 bytes, and the separate worker reads
  bytes/decodes UTF-8. CRLF, lone CR, LF and Unicode are preserved exactly. It checks
  `task_text_sha256` before readiness/model setup and records the verified digest
  in its sanitized receipt. A mismatch cannot make a model request.
- `bench.attest` records canonical ID/raw hash/publication commit, actual runtime
  Git/source fingerprints, clean status, plan/oracle hashes, full experiment ID,
  exact selected task/run IDs, scope and readiness. Local Git reads disable
  optional locks. Effective mini settings/config/bridge identity are bound and
  checked against the canonical endpoint/profile; no credential value is read.
  Audit/drift records never grant execution or pool eligibility.
- `bench.run --canonical-config ... --canonical-data-root ...` validates that
  attestation before dispatch. Blocked readiness fails before factories/output
  creation. If a future reviewed revision authorizes dispatch, immutable
  `canonical-config.json` and `config-attestation.json` are saved first, and every
  result/lifecycle event binds their ID/hash. Resume rejects changed/dropped or
  retroactively attached provenance. Legacy calls without the flags stay
  explicitly unattested; the flags are mandatory in the canonical protocol.

The normal v1 `--require-comparable` fails source validation after integration.
For a diagnostic JSON report without waiving the source freeze:

```powershell
& $Python -m bench.canonical --audit-current --require-comparable
```

This exits **1**, with `contract_valid: true`, `static_valid: false`, the actual
source drift, and `cross_shard_comparable: false`. `--audit-current` alone exits 2
when runtime drift exists. Neither mode authorizes work. A new reviewed config
revision is required; this milestone does not manufacture one with green gates.

## Exact prepared smoke artifacts (no execution)

All paths are outside the repository. Root:

`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\smoke-gemini54v1-20261115-fe1d911c`

- Plan: `plan.json`; SHA-256 `5a14bfa2f3f337bedd7b716c741bc9298f45bacbac46e8001c6ff2d697043ae2`.
- Original oracle subset: `oracles.json`; SHA-256 `352f9b50c636e288f4a2bdeea4e8928f509f1d2848ac496ba3152c95b309b30a`.
- `smoke-preparation.json`, `canonical-audit.json`, and the eventual runner command
  are recorded there. `config-attestation.json` is generated after publication so
  its runtime SHA/clean status refer to the committed fixes; the earlier
  `attestation-draft.json` deliberately records an uncommitted checkout.

Selection is the first three positions of canonical shard 1/4:
`polyglot/affine-cipher`, `polyglot/beer-song`, `polyglot/book-store`.
It preserves v1's full-plan ID
`014366f0d84d1ff91303c34fbd1d8750b2cdfc009901cecbe0a40e8cf21fb91b`
and exact prompt/source/oracle inputs. Each task keeps Crocodile 1/2, mini 1/2,
then all-off twin 1: **3 tasks, 15 unique slots (6/6/3)**. This partial shard is
development smoke only, with no QuixBugs coverage or pooled-report eligibility.

Set `$Python` to `C:\Users\gunda\venvs\crocodile\Scripts\python.exe`, `$Smoke` to
the root above, `$Data` to the verified assembled input directory
`C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132\generated-20261114-4df7ffd8`,
and `$Repo` to the repository root. The **eventual command below was not run**:

```powershell
& $Python -m bench.run --plan "$Smoke/plan.json" --oracles "$Smoke/oracles.json" --mini-settings "$Repo/bench/configs/mini-settings.ubuntu.json" --canonical-config "$Repo/bench/configs/gemini-benchmark-v1.json" --canonical-data-root "$Data" --output "$Smoke/runs" --execute
```

Do not use `--execute` while the comparability gate fails. After a successor config
and owner evidence are approved, regenerate the attestation and update the config
argument/output directory; never relabel or resume these v1 artifacts as a new
cohort. The remaining live authorization is for an explicit three-task smoke after
those prerequisites, not a 54-task benchmark. No live keys or Bifrost databases
were used here.
