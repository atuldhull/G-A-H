# Crocodile 🐊 — a coding agent that snaps up wasted tokens

**Crocodile** is a Python terminal coding agent built for Global AI Hackathon PS-01. It fixes code until the
tests pass, while spending as few tokens as possible, and it never runs code, sends private code to the
cloud or overspends without a visible decision.

It runs every model call through the **Bifrost** gateway (virtual keys, routing, failover, budgets, per-request
cost logs) and uses **Tavily** for documentation search.

## Pilot result

Development pilot on 3 Polyglot tasks (affine-cipher, beer-song, book-store), 15 slots, Gemini 3.5
Flash-Lite through Bifrost, graded independently by the original tests:

| Agent | Solved | Avg. tokens per run |
|---|---:|---:|
| **Crocodile** (all levers on) | **6 / 6** | **8.1K** |
| Crocodile all-off twin (same agent, levers off) | 3 / 3 | 23.4K |
| mini-swe-agent 2.4.6 (baseline) | 6 / 6 | 63.2K |

Same solve rate at roughly **7.8× fewer tokens than mini-swe-agent** and **2.9× fewer than its own
levers-off twin**, so the savings come from the design rather than the model.

> **Scope:** this is a small, non-comparative development pilot (`bench.pilot`), not the full benchmark.
> Three slots first hit a Gemini free-tier quota (HTTP 429) and were retried; the original attempts are kept.
> The 54-task / 270-slot comparable benchmark is planned and validated (`bench/configs/gemini-benchmark-v5.json`)
> and is reported in [bench/report.md](bench/report.md) only once every evidence gate passes.
> Per-request costs reconcile exactly with Bifrost's logs and Google's published Flash-Lite price.

## How it saves tokens

Each lever is a flag (`--flags all | none | -lever`), so its effect can be measured on its own:

| Lever | What it does |
|---|---|
| `cache` | Stable prompt prefix so the provider's prompt cache hits |
| `gate` | Compacts tool output (pytest summaries, head + tail) before the model sees it, and scans it for secrets |
| `readcache` | Never re-sends a file the model has already seen unchanged |
| `mask` | Collapses old tool output to short stubs once it stops being useful |
| `preload` | Pre-loads only files the task and failing tests point to |
| `stop_green` | Stops the moment the oracle tests go green |
| `thrash` | Detects edit/undo loops and breaks them |
| `rewind` | Rolls back to the last good checkpoint when progress stalls, keeping a memory of failed attempts |
| `ladder` | Verifies cheapest-first: syntax check, then lint, then oracle tests, then the full suite |
| `escalate` | Starts on the cheap model and moves up only when stuck (disabled in the benchmark) |

Every run ends with a **savings receipt**: tokens used, cost, and a counterfactual estimate of what the
levers saved.

## Control and safety

- **Approvals:** running tests or commands, network access and file writes need explicit consent; refused
  consent is reported as `TESTS NOT RUN (no consent)`, never as a fake pass.
- **Confidential mode:** private repositories route only to an allow-listed local model (Ollama); cloud
  fallbacks and web search are refused.
- **Budgets:** each call reserves its cost up front against per-user daily limits; Bifrost enforces a
  second, independent cap.
- **Tamper-evident state:** the local state database and event journal are sealed with an HMAC chain.
- **Static quote:** `crocodile quote` estimates cost before anything runs.
- **Red-team suite:** 15 architecture attack groups, all passing on Windows CI ([redteam/](redteam/README.md)).

## Quick start

Requires Python 3.12, a running Bifrost gateway and a Bifrost virtual key.

```powershell
python -m venv D:\venvs\crocodile          # keep the venv outside the repo
D:\venvs\crocodile\Scripts\pip install -e .
crocodile init                             # creates and seals local state + default settings
crocodile doctor                           # checks gateway, keys, prices and policy
crocodile quote "fix the failing test in tests/test_parser.py"
crocodile run   "fix the failing test in tests/test_parser.py" --test tests/test_parser.py
```

Gateway settings live in `%APPDATA%\crocodile\config.yaml` (`bifrost_url`, model chains). Virtual keys are
read from Windows Credential Manager (`crocodile` / `vk-public`), with `CROCODILE_VK_PUBLIC` as a fallback.
An example Bifrost configuration is in [bifrost/config.json](bifrost/config.json); all secrets in it are
environment references.

## Architecture

| Part | Area | Code |
|---|---|---|
| 1 | Agent loop, tools, token levers, receipts | [crocodile/](crocodile/) (`loop.py`, `engine/`, `tools/`) |
| 2 | Gateway: Bifrost egress, failover, budgets, local routing, Tavily | [crocodile/gateway/](crocodile/gateway/) |
| 3 | Security: approvals, confidential detection, sealed state | [crocodile/security/](crocodile/security/) |
| 4 | Benchmark harness, red-team suite, terminal UI | [bench/](bench/), [redteam/](redteam/), [crocodile/ui/](crocodile/ui/) |

## Evidence and reproducibility

- Benchmark design, pinned inputs and gates: [bench/gemini-54-v5.md](bench/gemini-54-v5.md),
  [bench/runner.md](bench/runner.md)
- Cost export rules: [bench/bifrost-export.md](bench/bifrost-export.md)
- Submission pack (demo script, checklist, status): [docs/submission/](docs/submission/README.md)

## Limitations

- Not an OS sandbox: approved tests run repository code as the current user.
- Public benchmark tasks may appear in model training data.
- The comparable 54-task benchmark is still gated; only the pilot above is reported.

## License

MIT, see [LICENSE](LICENSE). Third-party credits are in [NOTICE](NOTICE).
