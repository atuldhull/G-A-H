# Gemini 54 v6: current agent runtime

Published 2026-11-17. The [v6 config](configs/gemini-benchmark-v6.json) pins the
agent runtime from main `a366329` (plus the validator change that registers v6,
`45b3974`). Everything else is the same as [v5](gemini-54-v5.md): same LF inputs,
dataset commits, prices, 54 tasks / 270 runs, four shards, 2+2+1 run order,
30-step / 600-second policy, independent grading and the four accepted limitations.

```text
v6 config ID   098247dad4c155113ad574621d088918de212bd7019d8a48816ae3c4716caf1b
v6 raw LF SHA  ba95d195946049c9ce200ae029f13d1bbf8d242ecff972d50e84ebc40bd6b396
v5 config ID   93c2acc67e2dfe9229b05c142296361b95de36d042876a4991100f2fd9a78c83 (unchanged)
```

## What changed in the runtime

Seven agent files changed after the 15 Nov shard runs (`a366329`):

- **Session lock** on the state database: two runs on one machine wait for each
  other instead of tripping false integrity violations.
- **Thrash detection** counts a strike only when tests did not improve; the run
  stops after 3 strikes.
- **Rewind** only undoes an attempt that passed fewer tests.
- **Gateway** retries rate-limit and transient errors with backoff, honours short
  provider waits and fails fast when the daily quota is used up.
- **`edit` and `run_tests`** accept string arguments instead of failing or splitting
  test IDs into characters.

Mini runtime pins are unchanged. Native (Crocodile and twin) results from v5 or
earlier must not be pooled with v6 native results.

## Status

The validator still cannot authorize paid runs or cross-shard comparability, and
the single post-restart per-machine cost-inventory gate is kept. The 18-attempt
inventory has been supplied, and approval relayed from Tharun through Atul on
17 Nov is recorded in the change record only. **v6 results are reported as a limited
run.**

## Running on v6

```powershell
git fetch origin; git checkout --detach <v6 publication commit>
powershell -ExecutionPolicy Bypass -File run-shard.ps1 -Shards <yours> -Agents native `
  -Repo D:\gah-run -Data D:\bench-data2 -ExpectCommit <v6 publication commit> -OutRoot D:\bench-results-v6
```
