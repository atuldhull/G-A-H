# Person 4 handoff — v4 remains blocked

Checked 2026-11-15 on `person-4`, incorporating current main
`af6974a3efb4977364f3a572509c41a9752e8ba4`. Immutable v4 fingerprint:
`026d0a1b238f4675011c268619c051b1ffd3102a264a85e712bf7721f49b1bb4`.
Runtime checkpoint is `deaf328ab72c5149ba8e67a511a606b912aa4b1e`;
approved price SHA is
`8469236260572f0b68d405514d435db06183196269faaf5c429593ceaf18f21e`.
See [v4 release details](gemini-54-v4.md) for input hashes and accepted limitations.
This handoff changes no immutable config, price, plan or evidence.

## Commands and existing evidence

Run from the repository root. Paths below are verified on this machine;
other operators must generate and attest their own local paths/settings.

```powershell
$Repo = (Get-Location).Path
$Python = 'C:\Users\gunda\venvs\crocodile\Scripts\python.exe'
$Base = 'C:\Users\gunda\crocodile-benchmark-inputs\verify-20261114-b9b10132'
$Data = "$Base\generated-lf-v2-20261115-31f9cef"
$Bundle = "$Base\release-gemini-54-v4-20261115"
$Config = "$Repo\bench\configs\gemini-benchmark-v4.json"
& $Python -m bench.canonical --config $Config --data-root $Data --plans "$Bundle/full.json" "$Bundle/shard-1.json" "$Bundle/shard-2.json" "$Bundle/shard-3.json" "$Bundle/shard-4.json"
& $Python -m bench.canonical --config $Config --data-root $Data --require-comparable
```

Observed: strict validation **exit 0**, all five manifests valid, no runtime/price
drift; comparability **exit 1**, paid authorization false. Existing smoke files
are `$Bundle/smoke.json`, `smoke-oracles.json`, `smoke-attestation.json` and
key-free `mini-settings.json`. The smoke contains **3 tasks / 15 slots**;
full/shards contain **54/270**, **14/70, 14/70, 13/65, 13/65**.
Per-task order is Crocodile 1, Crocodile 2, mini 1, mini 2, all-off 1.

Only after evidence review, a supported authorization revision/mechanism and an
authorized working machine, the reviewed runner command shape is:

```powershell
# NOT AUTHORIZED NOW. Do not drop canonical flags to bypass the gate.
& $Python -m bench.run --plan "$Bundle/smoke.json" --oracles "$Bundle/smoke-oracles.json" --mini-settings "$Bundle/mini-settings.json" --canonical-config $Config --canonical-data-root $Data --output "$Bundle/smoke-results" --execute
```

Validate the new authorization's actual CLI/config before running that command.
Audit all 15 slots, restored-original grades, complete request/session/VK/model
joins and authoritative log-derived costs before considering any official shard.
Quota, setup and interrupted runs remain incomplete, never solved-task failures.

## Remaining gates and owners

Missing artifact: Atul/Vivek's sanitized **v4 served-model/routing proof and reviewed closed/flushed complete session inventory** has not been supplied.

| Gate | Owner and smallest acceptance evidence |
|---|---|
| Historical `3a111322` | Atul / Person 4 / reviewer: explicit historical-attempt and rerun-cohort disposition, retry/cost lineage; retain original ungraded preparation failure and unknown exact cause. |
| Native policy binding | Persons 1/2 / operator: actual native request/log correlation proving Flash-Lite, endpoint 18080, stable same bench VK and no fallback. Source settings alone are insufficient. |
| Per-machine execution/cost | Person 2 / operators / Person 4: actual served-model proof (current nulls still reject), reviewed close/flush/retention/quiescence/origin/VK evidence, valid sealed state and machine/config/header attestations. |

[Twenty-request audit](evidence/mini-kheapsort-v4-audit.json) preserves the accepted
usage/price checks; all 20 null served-model identities and session completeness
remain unresolved. No complete cost export or dollar claim follows from those
checks. Original inventories/token evidence remain unchanged. Current v4 has no
supported ready-flag override; new evidence alone does not rewrite its pins.

Red-team groups 5/6 now use real owner policies and journals with an in-memory
transport, not live gateway evidence. See [red-team checks](../redteam/README.md).
No paid request, smoke or official shard was started during this handoff.
