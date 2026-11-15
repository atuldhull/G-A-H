# Crocodile 🐊

**A terminal coding agent that snaps up wasted tokens: more correct, test-verified work per token, with budget, privacy and approval rules enforced by code, not by the prompt.**

Built for Global AI Hackathon · Problem Statement 01 ("a coding agent that gets the job done on the fewest tokens") with **Bifrost** (AI gateway) and **Tavily** (web search).
Built 12–15 Nov 2026 (research 10–11 Nov) · MIT licence · Python 3.12 · Windows-first

---

## 1. Results

> Placeholders until `bench/report.md` is frozen. Every number below comes from that file, with model, task set, n, runs and date.

| | Crocodile | mini-swe-agent | Same agent, all levers off |
|---|---|---|---|
| Cost per solved task | $`<x>` | $`<y>` | $`<z>` |
| Pass rate | `<a>`% | `<b>`% | `<c>`% |
| Tasks | `<n>` Aider Polyglot Python + `<m>` QuixBugs (secondary set) | | |
| Model / gateway | `<model>` via Bifrost v2.5.1, `<runs>` independent runs, `<date>` | | |

- **Savings:** "On tasks both agents solved, Crocodile cost `<r>`× as much per task (95% CI `<lo>`–`<hi>`)."
- **Accuracy:** `<non-inferiority or "inconclusive at this sample size" wording from bench/report.md>`
- **Budget race:** 8 processes, one $0.02 daily limit: **overshoot $0.0000** with our reservation vs **$0.022** with check-then-record (`python -m bench.race --procs 8 --calls 10 --limit 0.02`).

Costs are taken from Bifrost's request logs × `prices.yaml`, never from the agent's own estimate. Per-run receipts show "tokens avoided" as **estimated, first-order** figures.

**Video:** `<link>` · **Screenshots:** `<quote>` `<red approval>` `<LOCKED confidential receipt>` `<takeover banner>`

---

## 2. The problem and the four rules

Coding agents spend most of their tokens on things that do not produce a fix: re-reading files, carrying old tool output, failed attempts that stay in the context, and an extra "let me double-check" turn after the tests already pass. Teams also need hard guarantees that a prompt cannot talk its way around. Crocodile enforces all four required rules **in deterministic code, outside the model**:

| Rule | How Crocodile enforces it | Shown in |
|---|---|---|
| **Reliability** | When Bifrost fails over, Crocodile prints which model took over and why (error class), and the session continues | Takeover banner |
| **Budget** | Every model call reserves money atomically **before** it is sent, priced at the most expensive model that could answer; a reservation never exceeds what is left. At the limit the call is not made and the run stops with the reason | `bench.race`, `--user` limits |
| **Confidential code** | In a confidential repo only allowlisted local Ollama models are used, through a local-only virtual key with no fallbacks; web search is not offered, whatever the task text says | `LOCKED confidential` receipt, egress log |
| **Action approval** | Reads are free; writes, commands, test runs and git mutations need a console approval the model cannot answer. Running the repo's tests is treated as running the repo's code (red, typed confirmation) | AMBER / RED prompts |

---

## 3. How it saves tokens and stays correct

Every lever is behind a flag, so the benchmark compares Crocodile with **the same agent with every lever off**.

| Lever | What it does |
|---|---|
| Cache-stable prompt | Static system prompt + frozen tool list first; prompt-cache breakpoints on the latest turns (41% of input tokens served from cache on a 7-call task in our live run) |
| Evidence-based preload | Small files named in the task or imported by the tests go into the first prompt, so most tasks need no search/read turns |
| Output gate | Test/command output is cut to the failing assertions, head and tail; the full output is spilled to disk and can be paged in |
| Read cache | Re-reading an unchanged file returns a one-line "unchanged" note; a changed file returns a diff |
| Batched masking | Old tool output is replaced by stubs in batches, only when the saving beats the cache rewrite |
| Stop on green | The frozen tests are the oracle: the run ends the moment they pass with no regressions; the model never declares success |
| **Progress-gated rewind** | After a failed attempt, if fewer or equal tests pass, the files are restored and the attempt is cut from the conversation (the cached prefix stays valid); a short note keeps the diff and the failing assertion. Progress becomes the new checkpoint |
| Attempt memory | "Already tried and failed" approaches stay pinned in the task state across rewinds |
| Thrash detector + escalation | Repeated failures, repeated calls or idle turns switch strategy, escalate cheap → strong, then stop; the reason is printed |
| Savings receipt | Each run reports tokens avoided per technique (estimated, first-order) |

## 4. How AI is used

AI where it earns its tokens, code where it does not: a cheap model first; escalation only on evidence (printed with its reason); a local Ollama model as a first-class worker for confidential repos; Tavily search (`web_docs`) for third-party API docs, approved per query and never offered in confidential mode; and "LLM calls avoided by deterministic checks" on the receipt.

**AI tools used to build it:** Claude Code (Anthropic) assisted with research, design and code. Every change was reviewed and tested by the team.

## 5. Architecture

```
crocodile run ──► Agent loop (Part 1) ──► Gateway (Part 2) ──► Bifrost v2.5.1 ──► Gemini / Anthropic / OpenAI / Ollama
                   │  tools, levers,         budget reservation,     virtual keys, governance,
                   │  rewind, receipt        failover banner,        fallbacks, request logs
                   │                         journal, egress log  ──► Tavily (web_docs)
                   └──► Security (Part 3): approvals, argv-only runner, hardened git, provenance,
                        secret redaction, confidential detection, undo, sealed state DB
Bench (Part 4): sharded plans, for_bench sessions, independent grading, report
```

Bifrost provides virtual keys per user, model allow-lists, explicit fallbacks and request logs; Tavily provides the documentation search.

## 6. Quickstart (Windows)

```powershell
py -3.12 -m venv D:\venvs\crocodile                     # keep the venv OUTSIDE any repo
D:\venvs\crocodile\Scripts\python -m pip install -e ".[dev]"
# Bifrost v2.5.1 with bifrost/config.json; keys and sk-bf-... virtual keys in your user environment
npx -y @maximhq/bifrost --transport-version v2.5.1 -app-dir D:\bifrost -host 127.0.0.1 -port 18080
D:\venvs\crocodile\Scripts\crocodile.exe init           # one-time: seal the state DB, write settings
crocodile quote "Fix the failing test" --repo C:\path\to\repo
crocodile run   "Fix the failing test" --repo C:\path\to\repo --test tests\test_x.py
```

## 7. Limitations

- No OS sandbox: an approved test run executes the repository's code.
- A determined process running as the same user can bypass local checks; the gateway budget is the independent cap.
- The local Bifrost in the demo binds only an honest user.
- Small samples; we make no significance claims beyond `bench/report.md`.
- Benchmark tasks are public and may be in model training data.
- Windows-first; other platforms are untested.

## 8. Built vs borrowed

Own code: agent loop, token levers, rewind, gateway client, security layer, bench. Ideas re-implemented (not copied) from open-source agents are credited in `NOTICE`. Bifrost (Apache-2.0) is used unmodified as a pinned binary; mini-swe-agent (MIT) only as a baseline.

## 9. Roadmap

Budget step-down ladder (strong → cheap → local before pausing), undo of command side effects, compaction, a repo map for large codebases, a team dashboard and Postgres ledger, an OS-level sandbox.
