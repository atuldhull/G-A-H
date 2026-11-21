# Benchmark status: 54-task run complete, reported as a limited run

## Results (20–21 Nov 2026)

54 tasks (34 Aider Polyglot + 20 QuixBugs), the same model for every agent (Gemini 3.5 Flash-Lite through
Bifrost v2.5.1), 30 steps and 600 seconds per run, each result re-tested in a fresh copy with the original
tests restored.

| Agent | Runs | Solved | Avg. tokens per run |
|---|---:|---:|---:|
| Crocodile (all levers on) | 108 | 104 (96%) | 16.6K |
| Crocodile all-off twin | 54 | 54 (100%) | 42.8K |
| mini-swe-agent 2.4.6 | 108 | 108 (100%) | 76.4K |

- Crocodile: 4.6× fewer tokens than mini-swe-agent, 2.6× fewer than its twin; about $0.0051 per run against
  $0.0103 for the twin.
- Unsolved Crocodile runs: bowling run 2, paasio run 1, scale-generator run 1, wordy run 2. Each task was
  solved in its other Crocodile run.
- On the same shards, the post-benchmark fixes raised Crocodile's solve rate from 84% (15 Nov code) to 96%.

## How it was run

| Item | Value |
|---|---|
| Release config | [gemini-54-v6](../../bench/gemini-54-v6.md), reviewed and merged as PR #1 |
| Crocodile and twin | commit `75b8a7e`, shards 1–2 by Vivek and 3–4 by Ritika (both confirmed the commit) |
| mini-swe-agent | commit `d906adf` (mini's code is unchanged), shards 1–2 by Tharun and 3–4 by Atul |
| Plan | 270 slots: 2 Crocodile, 1 twin and 2 mini runs per task; 4 shards of 14, 14, 13 and 13 tasks |
| Pooling | No v5 or earlier native runs are pooled with the v6 runs |

## Why "limited"

- Our own comparability gate (a reviewed per-machine cost inventory) is still open; the validator does not
  authorize cross-shard comparability.
- mini-swe-agent's token counts come from its own receipts, and its served model is not independently
  proven from gateway logs.
- The mini runs for shards 1–2 used three free-tier Gemini keys from three separate Google projects,
  switched as each reached its daily limit. This is recorded in the run evidence.
- No statistical significance is claimed. The tasks are small exercises, so the results do not show savings
  on large real repositories.

The formal statistical report ([bench/report.md](../../bench/report.md)) stays unpublished until the gate is
closed.
