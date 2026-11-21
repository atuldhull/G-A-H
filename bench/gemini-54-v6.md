# Gemini 54 v6: current agent runtime

Published 2026-11-17, re-pinned 2026-11-19 before any run used it. The [v6 config](configs/gemini-benchmark-v6.json) pins the
agent runtime from main `a366329`, the validator change that registers v6
(`45b3974`) and the gateway retry budget (`5e43fa8`). Everything else is the same as [v5](gemini-54-v5.md): same LF inputs,
dataset commits, prices, 54 tasks / 270 runs, four shards, 2+2+1 run order,
30-step / 600-second policy, independent grading and the four accepted limitations.

```text
v6 config ID   710079567c1807405a75f51d7bf4c69f2cd38fe8d40e6cecc1c7f744ff966273
v6 raw LF SHA  4719f746840d1dca9b505636e683997e5b02cef67fc59db1d0393d8b24b0e646
v5 config ID   93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83 (unchanged)
```

## What changed in the runtime

Seven agent files changed after the 15 Nov shard runs (`a366329`), plus one later
gateway fix:

- **Session lock** on the state database: two runs on one machine wait for each
  other instead of tripping false integrity violations.
- **Thrash detection** counts a strike only when tests did not improve; the run
  stops after 3 strikes.
- **Rewind** only undoes an attempt that passed fewer tests.
- **Gateway** retries rate-limit and transient errors with backoff, honours short
  provider waits and fails fast when the daily quota is used up.
- **`edit` and `run_tests`** accept string arguments instead of failing or splitting
  test IDs into characters.
- **Retry budget** (`5e43fa8`, 19 Nov): about 2 minutes instead of 23 seconds, because
  Gemini 503 "high demand" bursts last 1-2 minutes. It affects only infrastructure
  errors, not how tasks are solved.

Mini runtime pins are unchanged. Native (Crocodile and twin) results from v5 or
earlier must not be pooled with v6 native results.

## Status

The validator still cannot authorize paid runs or cross-shard comparability, and
the single post-restart per-machine cost-inventory gate is kept. The 18-attempt
inventory has been supplied (Tharun's audit:
[pilot-v4-post-restart-review.md](pilot-v4-post-restart-review.md)). The config's change record notes an
approval relayed through Atul on 17 Nov; Tharun then reviewed this release himself and merged it into
`main` as PR #1 on 21 Nov 2026 (fast-forward, commit IDs unchanged). Neither step authorizes
comparability: **v6 results are reported as a limited run.**

## Running on v6

The v6 publication commit is `75b8a7e`. Use PowerShell 7 (`pwsh`): under Windows PowerShell 5.1 the
runner's `.pyc` check ignores `-Include` and fails even when no `.pyc` files exist.

```powershell
git fetch origin; git checkout --detach 75b8a7e
pwsh -ExecutionPolicy Bypass -File run-shard.ps1 -Shards <yours> -Agents native `
  -Repo D:\gah-run -Data D:\bench-data2 -ExpectCommit 75b8a7e -OutRoot D:\bench-results-v6
```

## Runs on v6 (20–21 Nov 2026)

Crocodile and twin, all 54 tasks on `75b8a7e` (shards 1–2 Vivek, 3–4 Ritika; both confirmed the commit):
Crocodile 104 of 108 runs solved, 16.6K average tokens per run; twin 54 of 54, 42.8K. No v5 or earlier
native runs are pooled with these. mini-swe-agent ran on `d906adf` (its code is unchanged): 108 of 108,
76.4K average tokens per run from its own receipts. Shards 1–2 of the mini runs used three free-tier
Gemini keys from three separate Google projects, switched at each daily limit.
