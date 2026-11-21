# Crocodile 🐊 — a coding agent that snaps up wasted tokens

**Crocodile** is a Python terminal coding agent built for Global AI Hackathon PS-01. It fixes code until the
tests pass, while spending as few tokens as possible, and it never runs code, sends private code to the
cloud or overspends without a visible decision.

It runs every model call through the **Bifrost** gateway (virtual keys, routing, failover, budgets, per-request
cost logs) and uses **Tavily** for documentation search.

## Results: 54-task run (limited)

54 tasks (34 Aider Polyglot + 20 QuixBugs), 20–21 Nov 2026. Every agent used the same model (Gemini 3.5
Flash-Lite through Bifrost v2.5.1), 30 steps and 600 seconds per run, and every result was re-tested in a
fresh copy with the original tests restored:

| Agent | Runs | Solved | Avg. tokens per run |
|---|---:|---:|---:|
| **Crocodile** (all levers on) | 108 | **104 (96%)** | **16.6K** |
| Crocodile all-off twin (same agent, levers off) | 54 | 54 (100%) | 42.8K |
| mini-swe-agent 2.4.6 (baseline) | 108 | 108 (100%) | 76.4K |

Crocodile used **4.6× fewer tokens than mini-swe-agent** and **2.6× fewer than its own levers-off twin**,
at about half the twin's cost per run ($0.0051 vs $0.0103). The trade-off: it missed 4 of 108 runs
(bowling, paasio, scale-generator and wordy, each solved in its other run), while the twin and mini solved
all of theirs.

> **Scope: a limited run, not a comparable benchmark.** The release config is
> [gemini-54-v6](bench/gemini-54-v6.md); Crocodile and twin runs used commit `75b8a7e`, mini runs `d906adf`
> (mini's code is unchanged between them). Our own comparability gate (a reviewed per-machine cost
> inventory) is still open, mini-swe-agent's token counts come from its own receipts, and its served model
> is not independently proven from gateway logs. The mini runs for shards 1–2 used three free-tier Gemini
> keys from three separate Google projects, switched as each hit its daily limit; this is recorded in the
> run evidence. No statistical significance is claimed.

Live demo check (20 Nov): on a 3-bug demo project Crocodile was solved in one step with 1,588 input and
147 output tokens; its receipt cost, $0.0008439, equals the cost Bifrost logged for that request.

### Earlier development pilot

3 Polyglot tasks (affine-cipher, beer-song, book-store), 15 slots, same model and grading:

| Agent | Solved | Avg. tokens per run |
|---|---:|---:|
| **Crocodile** (all levers on) | **6 / 6** | **8.1K** |
| Crocodile all-off twin (same agent, levers off) | 3 / 3 | 23.4K |
| mini-swe-agent 2.4.6 (baseline) | 6 / 6 | 63.2K |

A small, non-comparative pilot (`bench.pilot`); three slots first hit a free-tier quota (HTTP 429) and
were retried, with the original attempts kept.

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
| `thrash` | Detects repeated failures and edit loops; switches strategy, and stops after 3 strikes without test progress |
| `rewind` | Rolls back an attempt that made tests worse, keeping a memory of failed attempts |
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
- **Red-team suite:** 15 architecture attack groups, all passing on the current code on Windows
  ([redteam/](redteam/README.md)), including `pipe_yes`: piped "yes" input can never approve anything.
- **Resilient gateway calls:** rate-limit and transient errors are retried for about two minutes (provider
  overload bursts last 1–2 minutes); an exhausted daily quota fails fast with a clear message.

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

- Benchmark release used for the results: [bench/gemini-54-v6.md](bench/gemini-54-v6.md) (pins the exact
  runtime files); earlier releases: [v5](bench/gemini-54-v5.md); runner: [bench/runner.md](bench/runner.md)
- Cost export rules: [bench/bifrost-export.md](bench/bifrost-export.md)
- Submission pack (demo script, checklist, status): [docs/submission/](docs/submission/README.md)

## Limitations

- Benchmark tasks are small single-file exercises; the results do not show savings on large real
  repositories.
- The savings cost some accuracy: 96% solved against 100% for the twin and mini-swe-agent.
- The 54-task run is a limited run: the comparability gate is still open (see the scope note above).
- Not an OS sandbox: approved tests run repository code as the current user.
- Public benchmark tasks may appear in model training data. Windows-first.

## License

MIT, see [LICENSE](LICENSE). Third-party credits are in [NOTICE](NOTICE).
