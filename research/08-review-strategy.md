# 08 · Strategy review: skeptical judge + engineering manager (12 Nov 2026)

*Inputs: TEAM-BRIEF, PLAYBOOK, DESIGN §1/§8–§13, RESEARCH §9, web/GitHub check on 12 Nov. Situation: 0 lines of code, 3.5 days left (12 Nov → 15 Nov 12:00), most likely solo, on Windows, with a token-metered Claude plan.*

---

## 0. Verdict in five lines

1. **The plan as written cannot ship solo.** DESIGN has ~20 modules, 45 red-team cases, taint, a shadow-git undo, hash chains, tree-sitter explainers and a 360-run bench. That is 4 people × 6 days, and the schedule already assumed 2 build days that went to research. About 25–30% of it is achievable.
2. **The bench is the product, and it is the riskiest thing in the plan.** mini-swe-agent on Windows has not been verified (D0 check #10), Polyglot tasks don't exercise our main levers (localise/reproduce-first), n=30 × 2 seeds can't separate pass rates, and mini-swe-agent is a *lean* baseline, so our savings could be small.
3. **The pitch is security-heavy for a "fewest tokens" problem**, and it claims proofs (45 CVEs, canary audit, undo of side effects) that we will not have time to build. Over-claiming is now the biggest reputational risk.
4. **A new peer raises the bar on UX and polish:** `Ani07-05/slendertoken` (created 8 Nov, pushed 12 Nov) has a one-line installer, a website, a TUI with mascots, Bifrost VK budgets, a `--private` Ollama-only key, Tavily, and a "54% fewer tokens at 4/4 pass" badge. Our edge is still the **measured CPST vs a real baseline** and **enforced budget/approval guarantees**, but only if they actually exist on 15 Nov.
5. **Fix:** freeze the design today. Build a **minimum winning slice** (§3): an own ~400-line loop, the 4 rules in their simplest *correct* form, 4 token levers, a paired bench, one race demo. Everything else is a cut or a "roadmap" slide.

---

## 1. Loopholes found (impact → fix → doc to change)

### A. Scope and process

| # | Loophole | Impact | Fix | Change in |
|---|---|---|---|---|
| A1 | The day plan starts on 10 Nov and is now 2 days behind with nothing built. "Never cut" contains ~18 items, so in practice the never-cut list is the whole plan | Nothing finishes; a half-built 20-module agent with no numbers loses to a simple, finished one | Adopt the re-plan in §3; "never cut" shrinks to the **slice** | DESIGN §10.2/§10.3, TEAM-BRIEF §6 |
| A2 | DESIGN.md is 124 KB (~30K tokens). Feeding it to Claude Code while building burns the metered plan | Token budget gone by 13 Nov | Write a 1-page `BUILD.md` (slice + interfaces) and give Claude only that plus the one DESIGN subsection a task needs. Never paste the whole DESIGN | New `BUILD.md`; TEAM-BRIEF §9 |
| A3 | Windows-only primitives (CONIN$, `msvcrt`, `creationflags`, `%APPDATA%`) | Judges on macOS/Linux can't run the "working demo" | Use cross-platform Python (`/dev/tty` vs `CON` behind one `ask()` function; `platformdirs`); GitHub Actions CI on ubuntu + windows | DESIGN §3/§5.7 |
| A4 | No public repo or commit history yet | "Core built during the hackathon" is easiest to prove with dated commits | Create the public repo **today** and commit at least hourly; README "Built 12–15 Nov" (research 10–11 Nov) | PLAYBOOK §5 row 1 (dates), §6 |
| A5 | The fixed times (bench 14 Nov 14:00, freeze 18:00) assume a working agent by 13 Nov midday | The bench starts late and gives no time to fix bugs it surfaces | Bench harness on **day 1** (12 Nov), seed 1 overnight on 13 Nov | PLAYBOOK §9 |

### B. "Boilerplate" rule: build on mini-swe-agent or not?

The rule (RESEARCH §9): *"existing libraries, frameworks, boilerplate may be used, but the core project should be created during the hackathon."*

- **Forking mini-swe-agent as our loop is a bad trade.**
  - For a coding agent, the loop *is* the core. A judge diffing our repo against mini-swe-agent would read it as "a fork plus wrappers".
  - It would also make us the **same agent as our baseline**, so the comparison becomes "mini-swe-agent vs mini-swe-agent + patches". That is credible as an ablation but weak as innovation.
  - Its bash-only design conflicts with our approval model, because every action is a model-written shell string, which DESIGN forbids auto-approving.
- **Write our own loop, ~300–400 lines.** With Claude Code this takes about 2–3 h. mini-swe-agent proves a minimal loop is ~100 lines, so this is cheap.
- **What is fine to use:**
  - Libraries: `httpx`/`openai` SDK pointed at Bifrost, `rich`, `typer`, `pytest`, `ruff`.
  - Bifrost's own VK budgets and fallbacks as the gateway layer.
  - mini-swe-agent **only as the baseline** (separate venv).
  - Its *idea* of a linear message history, credited in NOTICE.
- **Disclose clearly in the README:** "Loop, budget reservation, approvals, confidential router, token levers and bench harness written 12–15 Nov. Bifrost, mini-swe-agent (baseline only) and listed libraries used unmodified."

→ Change: TEAM-BRIEF §7 and DESIGN §12 get a row "mini-swe-agent: baseline only, not imported by the agent".

### C. Benchmark validity

| # | Hole a judge can poke | Impact | Fix |
|---|---|---|---|
| C1 | **mini-swe-agent on Windows is unverified.** Its local environment runs model-written bash-style commands via `subprocess` (shell = cmd.exe on Windows; *verify*) | No baseline, so there is no headline | **Go/no-go check at 11:00–11:45 today.** Options in order: (1) a small env subclass that runs `bash.exe -lc` from Git for Windows, disclosed as "only change: shell"; (2) run both agents in WSL2 if it is already installed; (3) fallback baseline = our loop with all layers off (state clearly that it is weaker evidence) |
| C2 | **Polyglot Python exercises are greenfield "implement this stub" tasks.** There is no bug to localise and the test already exists | Localise-first, reproduce-first and repo map can't show value. The ablation may even show them as **cost** | Don't claim those levers on Polyglot. Measure only what Polyglot exercises: stop-on-green, output trimming, thrash detection, cache-stable prefix, edit matcher. Optional secondary set: 8–10 **mutation bugs** injected into a small pure-Python MIT repo (flip an operator, verify one test fails). That one does exercise localisation. Only if time allows on 14 Nov |
| C3 | **Statistical power.** At n=30, a Wilson 95% CI on a 60% pass rate is about ±17 pp, so pass rates can't be separated. 2 seeds don't fix that | "Same or better accuracy" is unprovable; a judge asks "is that significant?" | Use a **paired design**: same task for both agents. Report (a) the pass-rate **difference with a paired bootstrap CI** and win/loss/tie counts, framed as *non-inferiority* ("not worse by more than X pp"); (b) **cost ratio on tasks both solved**, which is paired and low-variance, so it is detectable at n=30; (c) CPST as the summary. Drop "significance" language entirely |
| C4 | **Fairness traps:** different instructions (we pass the test command, the baseline doesn't); the baseline's prompt template is tuned for SWE-bench; prompt caching on for us and off for it; model price table missing for the Bifrost model name in mini-swe-agent (cost = 0 or a crash); a step/cost limit hit by one agent only | "You crippled the baseline" kills the headline | Give both the **identical task text including the test command**. Use mini-swe-agent's default template plus that text. Enable its Anthropic cache-control option if it has one, or disclose that it is off. Compute **both agents' cost from Bifrost's logged usage** with one price table, not from each agent's own accounting. Use the same step cap (e.g. 30) and wall-clock cap. Publish the configs |
| C5 | **Test tampering.** The agent can edit `*_test.py` to pass | False "solved" | Grade in a clean copy: restore the original test files and run pytest. Count a test-file edit as failed |
| C6 | **Contamination.** Exercism tasks are memorised by models | Pass rates inflated for both | Mention it under Limitations. It affects both agents equally, so it is fine for a *relative* claim |
| C7 | **Bench cost/time.** 360 runs is unrealistic. 30 tasks × 2 agents × 2 seeds = 120 runs × 1–3 min ≈ 2–6 h sequential; Haiku-class at ~$0.01–0.05/run ≈ $2–6 | OK if it runs in parallel (4 workers) and starts by 13 Nov evening | Grid: **main 30 × 2 agents × 2 seeds** + **one ablation only: all-levers-off vs on** (30 × 1 seed). Drop the Sonnet seed and per-layer ablations, or label them "1 seed, indicative" if time is left. VK cap $15 |
| C8 | **The race demo is half-synthetic** (mock Bifrost for columns 1–2) | A judge may call it a toy | Fine if labelled: "8 processes, mock latency; property: overshoot ≤ 0 by construction". Add a unit test asserting the invariant |

**Cheaper credible alternative (recommended):** Aider Polyglot **Python** subset (34 exercises exist; take 30 with a fixed seed-chosen list), paired, 2 seeds, Bifrost-logged costs, plus an "all-off" ablation. Headline = **cost per task on commonly solved tasks + CPST, with pass-rate non-inferiority**. This needs no Docker and runs on Windows with pytest.

→ Change: DESIGN §10.4 (grid, paired stats, grading in a clean copy, unified cost source), PLAYBOOK §7 Q7 (fairness answer lists the controls above), TEAM-BRIEF §8 risk 7.

### D. Metric risk: what if we lose?

- **mini-swe-agent is already lean.**
  - It has a tiny prompt and no tool schemas.
  - Its cost grows with full history, so our wins come from output trimming, masking old observations, stop-on-green and thrash cutoffs.
  - Realistic outcome: **−10% to −35% cost at similar pass rate**, or worse if our extra verification turns cost tokens. Don't promise "solve more".
- **Pre-agree the narrative tree now**, so numbers can't bend the story late:

| Outcome | Headline |
|---|---|
| Cheaper, pass rate within noise | "X% lower cost per solved task than mini-swe-agent, pass rate not worse (paired CI)" |
| Cheaper, pass rate lower | "Pareto trade-off: −X% cost for −Y pp; our 'all-off' config matches the baseline's accuracy at Z cost". Show both dots honestly |
| Same cost | "Matches the leanest open baseline on cost **while** enforcing pre-call budgets, local-only privacy and approvals, which the baseline doesn't have." The ablation (all-off → on) shows our levers cut −X% within our own agent |
| More expensive | Lead with the internal ablation and the waste breakdown. Disclose the baseline result in the report. Never hide it |

- **Second comparison point:** our own loop with all levers off ("naive twin"). It is the comparison peers use (slendertoken: "54% fewer than naive"), so we can match their framing *and* add the real baseline on top.
- **Remove "we solve more"** from the one-liner until the data supports it (PLAYBOOK §1, §10).

### E. Demo risk

| Dependency | Risk | Fix |
|---|---|---|
| Ollama on the laptop | `qwen3-coder:30b` needs about 24 GB, so it will be slow or OOM. Unknown hardware | Use `qwen2.5-coder:7b` (or 3b) for the confidential segment. Confidential task = "explain/rename in one small file". Pull it **today in the background** |
| Failover needs 2 providers/keys | Only an Anthropic key, or no OpenAI credit | Failover across two Anthropic models, or primary = bogus key → fallback = real key. A "provider" can be the same vendor with a broken key. Also show a 429 failover if one happens |
| Bifrost via `npx` | Version drift, cold start | Pin the version, use a `prep.ps1` warm-up, and save the config in the repo (`bifrost/config.json` with env-var keys) |
| Live model wandering | High | Temperature 0, a deterministic tiny demo repo, **pre-record every segment on 14 Nov**. The video is the demo. Judging is 29 Nov, so a live run isn't required |
| Unicode/emoji in the Windows console | Medium | Windows Terminal, an ASCII fallback, and no 🐊 in the CLI output itself |
| A judge tries to install | Fails on macOS (A3) | Cross-platform + CI badge + a 60-s "fresh clone" clip |

→ Change: PLAYBOOK §8 (add the rows above), DESIGN §10.1 (Ollama model).

### F. Judge perception and pitch

| # | Issue | Fix |
|---|---|---|
| F1 | **Too security-heavy.** 5 of 7 video segments are about rules/security. PS-01 is "fewest tokens without compromising correctness"; the 4 rules are a pass/fail gate | Re-weight the video. **0:00–1:30 is about tokens:** Pareto/paired chart, a live task with a status line, trimmed output, a thrash cutoff, stop-on-green, the receipt. **1:30–2:45 covers the 4 rules, ~18 s each**, each with one concrete proof. 2:45 close |
| F2 | **Over-claiming.** "45 public bypasses/CVEs, none got through", "undo that reverts shell side effects", "canary-verified egress proof", "hash-chained", "taint wallet" are all unbuilt and mostly cut in §3 | Claim **only what is in the repo on 15 Nov**. Rewrite DESIGN §13 rows "Competitors" and PLAYBOOK §2 "Innovation" after the build, not before. Unbuilt items → a "Roadmap" slide |
| F3 | **Not explainable in 10 s.** "CPST", "reserve-max at the chain ceiling", "FIDES-lite", "provenance-named approvals" are jargon | 10-second version: **"Crocodile is a coding agent that charges you for fixed bugs, not for tokens: on the same tasks and model it costs X% less per solved task than mini-swe-agent, and its budget, privacy and approval rules are enforced in code, so a prompt can't talk its way past them."** Say "cost per solved task" in words; define CPST once |
| F4 | **Negative tagline.** "Others claim… we prove them" invites the judge to find what we haven't proved | Use: *"Pay for fixed bugs, not wasted tokens."* Keep "measured, not claimed" as a secondary line |
| F5 | **Crocodile branding.** Memorable and harmless; "snaps up wasted tokens" is good. But branding work (pun scripts, jaw imagery, the `crock` alias, PyPI name checks) costs hours | Keep the name and one line. Skip the logo work and use a single emoji/ASCII banner. 0 hours on branding before 15 Nov morning |
| F6 | **The peer with the best UX** (slendertoken: installer, website, mascots, energy/carbon) makes our CLI look plain | Don't compete on cuteness. Compete on **trustworthy numbers on screen**: a quote before the run, a live `$ / budget / tokens avoided` line, and a receipt with "solved by tests". One clean `rich` status line + 3 banners is enough |

### G. Use of AI criterion

- Today's story is mostly deterministic code (policy, budget, ladder, test parsing). A judge may score "Use of AI" low ("where is the AI?").
- **Make the AI decisions visible and measured:**
  1. **Evidence-based model routing.** The cheap model first; escalation to the strong model is triggered by test failures or thrash, and printed as `▲ ESCALATE: same failure twice → sonnet`. This is a real AI-routing decision with a logged reason. Optional: show the routing paper's trace-based-routing result (DESIGN §13 wording only).
  2. **Local model as a first-class worker** (confidential repos, and the last budget rung). It is a capability, not just a fallback.
  3. **AI hand-off capsule on thrash:** the cheap model writes a 150-token summary of what failed. Shown on screen.
  4. **Tavily used by the agent, not just wired in:** on `ImportError`/`AttributeError` for a third-party API, the agent may call `web_docs` (≤ 3 results, snippets only). It is blocked in confidential mode. Show it once in the video; count its tokens in the receipt.
- **Frame it as a thesis:** "AI where it earns its tokens, code where it doesn't. Each LLM call is justified by evidence, and each deterministic check saved an LLM call."
- Report "LLM calls avoided by deterministic checks" in the receipt.

→ Change: PLAYBOOK §2 "Use of AI" row, README §7 outline.

### H. Scalability criterion: a concrete story

- **Identity and money:**
  - One Bifrost virtual key per user. Our ledger's principal is the VK.
  - Reservations are atomic in SQLite (`BEGIN IMMEDIATE`); the same code moves to Postgres `SELECT … FOR UPDATE` for a shared team ledger.
  - The gateway VK budget is a second wall (402).
- **Proof:** the race demo *is* a scale test (8 concurrent sessions, 1 budget, overshoot 0). Show the "1 user → team" diagram.
- **Statelessness:** the agent holds no server state. Bifrost scales horizontally, and prompt-prefix caching means repeated tasks on the same repo get cheaper.
- **Unit economics slide:** "At CPST $X, 1,000 fixed bugs/month = $Y vs $Z for the baseline." This turns the metric into impact.
- **Not claimed:** multi-tenant SaaS, Postgres implemented (it is roadmap).

→ Change: PLAYBOOK §2 row and slide 6, DESIGN §8 row "Scalability".

### I. Submission requirements: gaps

| Gap | Fix |
|---|---|
| Video length limit, deadline time zone, track/problem ID in the form are **not verified** (PLAYBOOK assumes 3:00 and "noon") | Check Discord/form **today**. Peer repos label themselves "Track A, Problem 04", so there is a track/problem ID to fill in |
| "Working demo": unclear whether judges run it | Ship a pre-recorded video + reproducible quickstart + CI. Possibly a 2-min "fresh clone → doctor → run" clip |
| Licence not chosen | MIT. Pick it today (repo creation) |
| AI-tools disclosure | README §8: Claude Code (Opus/Sonnet) for research, code, tests; Atul reviewed. List any others |
| Tavily integration must be visible (sponsor) | Currently a cut item → move the minimal gated `web_docs` into the **slice** (§3) |
| Secrets in history | `.env` in `.gitignore` from the first commit; secret scan before going public |
| Description ≤ 150 words, problem, tech, how AI is used | Draft 14 Nov evening from the frozen numbers |

### J. Web/peer check (12 Nov)

- **No public judging guidance found** for "Geek Room Global AI Hackathon 2026" + Bifrost/Tavily. The rules we have (RESEARCH §9) remain the only source, so check Discord.
- **New or changed peers since 10 Nov (GitHub search):**
  - **`Ani07-05/slendertoken`** (Go, no licence, created 8 Nov, pushed 12 Nov). Features: one-line installer, a Vercel site, a TUI, small-model-first with escalation on a failed step, VK budget, a `--private` Ollama-only key, Tavily off in private mode, an approval prompt for non-read-only shell, an energy/carbon report. Benchmark: "54% fewer tokens than naive, 4/4 pass".
    - *Holes:* 4 tasks vs a naive twin; the budget is gateway-only (no pre-call reservation); `--private` is a per-run flag (PX-3 class); there is a "read-only shell" allowlist (PX-2 class).
  - **`nemo-MV33/thrift-agent`** is now **MIT** (DESIGN §14 says "no licence") and was pushed 12 Nov. Update §14.
  - `pinch` (AGPL), `gidorah`, `bifrost-leancoder`, `TokenWise` show no new activity found beyond what research/06 covered (pinch last pushed 8 Nov).
  - Many Bifrost+Tavily repos are freshness/meeting-research entries (other problems), not PS-01.
- **Implication:** at least 2 PS-01 peers compare against a "naive" agent on ≤ 10 tasks. **A paired 30-task comparison against mini-swe-agent with a published config is still a clear differentiator**, provided it exists.

→ Change: DESIGN §14 (add slendertoken PX mapping; thrift-agent licence), re-check on 14 Nov.

---

## 2. Must-have / nice-to-have / hard cut

### Must-have: the minimum winning slice (≈ 30 build hours)

| Area | What exactly (simplest correct form) |
|---|---|
| Loop | Own loop (~400 lines): tools `read(path, range)`, `search(rg)`, `list`, `edit(exact SEARCH/REPLACE)`, `run_tests` (fixed argv), `run_cmd` (argv, approval); pinned task state in the system tail; **stop-on-green**; step cap |
| Egress | One `call_model()` through Bifrost; every call written to SQLite (`calls`: user, model, tokens, $, is_fallback, confidential) |
| R1 Failover | Provider-prefixed model + explicit `fallbacks`; parse `routing_info`/headers; yellow **MODEL TAKEOVER** banner; session continues |
| R2 Budget | Per-user VK. **Atomic reservation** in SQLite at max fallback price × `max_tokens` before every call, reconcile after. 80% warning; at the limit → cheap → local → **pause** with a clear message. `bench race` (8 procs) + an invariant test |
| R3 Confidential | `.crocodile/confidential` marker found by walking up parent dirs; sticky. In that mode: a client built with the **local VK only** (cloud key never loaded), `ollama/…` model, `fallbacks: []`, Tavily tool not registered. `crocodile audit` = query of the calls table: every confidential call went to `ollama/*` + canary-string grep of the logged public payloads |
| R4 Approvals | Reads free (in-process). Writes / `run_cmd` / git mutations → console prompt read from the TTY (not stdin, not the model); argv only, never `shell=True`; git env hardening (`-c core.hooksPath=…`, `core.fsmonitor=false`, `GIT_CONFIG_GLOBAL`); a **red label "suggested by <file>:<line>"** when the argv string appears in text read this session (simple substring provenance, ~40 lines) |
| Token levers (each behind a flag) | (1) output gate: keep failing assertion + frames, spill full output to disk; (2) mask old observations; (3) cache-stable prefix with `cache_control`; (4) thrash detector (same error signature ×2 → escalate; ×4 → stop with a report); (5) verification: `ruff` + targeted tests before the full suite |
| Tavily | Gated `web_docs` (basic, 3 results, snippets), off when confidential, tokens counted |
| UX | `quote` (heuristic), a `rich` status line ($, budget, tokens, cache %), 3 banners (takeover, ladder, red approval), a receipt |
| Bench | Polyglot-Python 30, paired, ours vs mini-swe-agent, 2 seeds, + all-off ablation; grading in a clean copy; costs from the Bifrost log; `report.md` + one chart |
| Tests | ~15 pytest cases: the 4 rules + the reservation invariant + the stop-on-green turn count + test-file tamper grading |
| Ship | Public repo (MIT), README (results first), video ≤ limit, form |

### Nice-to-have (only after the slice is green, in this order)

1. Mutation-bug secondary task set (8–10 tasks)
2. Mini red-team: 10 cases from RT/PX (`;`/`&`/newline chaining, `git -c`/`--output`, path escape `..`/symlink, prompt asks for cloud in a confidential repo, piped `yes`)
3. Undo of **file edits** (snapshot before each write; `crocodile undo`)
4. Waste breakdown (3 categories: post-green, repeated-error, oversized output)
5. Repo map (simple: file list + top-level defs via `ast`, no tree-sitter)
6. `crocodile doctor`
7. Second-seed Sonnet point on the chart

### Hard cut (do not start; roadmap slide only)

- Shadow-git undo of **shell side effects**; hash-chained journal/ledger; `--resume`
- FIDES-lite taint lattice, taint-attributed wallet
- tree-sitter bash/PowerShell explainers; `mslex`; nonce-typed red approvals bound to an argv hash (keep plain typed `yes` for red)
- Full 45-case RT suite, hostile model stub
- Localisation stages 2–3, Agentless funnel, PageRank repo map, compaction, cache-break blame, read-cache diffs
- `pytest-testmon`; Bifrost routing-rule (CEL) half of the two-key check; `admin add-user` API (create VKs in the Bifrost UI and document it)
- Per-layer ablations, the Sonnet grid, 360-run plan; quote refinement from traces
- Branding work, slides beyond 6, a website

---

## 3. Re-plan, 12–15 Nov

### 12 Nov (today): hour by hour

| Time | Task | Done when | Go/no-go |
|---|---|---|---|
| 09:00–09:30 | Freeze scope (this doc). Create the public GitHub repo (MIT, `.gitignore` with `.env`), package skeleton, first commit. Write a 1-page `BUILD.md` from §2 | Repo URL exists | — |
| 09:30–10:45 | Installs (Atul runs them): venv, `httpx rich typer pytest ruff`; Bifrost pinned via npx with a config file; Anthropic key (+ second key or a bogus primary for failover); 2 VKs (cloud user, local-only). Start `ollama pull qwen2.5-coder:7b` **in the background** | `curl` through Bifrost returns usage incl. cached tokens; bogus primary → `is_fallback: true` | If Bifrost fallback/VK doesn't work by 10:45: failover = our client-side retry on the next model, with the banner still shown; disclose it |
| 10:45–11:45 | **Baseline smoke:** mini-swe-agent in a separate venv, model via Bifrost, 1 Polyglot Python exercise, shell = Git Bash | mini-swe-agent solves or fails one task and its tokens appear in the Bifrost log | **No-go at 11:45** → use the WSL2 path if WSL exists, else the "all-off twin" baseline and drop the mini-swe-agent claim from the pitch |
| 11:45–12:15 | Break | — | — |
| 12:15–15:00 | Core loop: `call_model` + SQLite calls table, tools, exact-match edit, `run_tests`, pinned task state, stop-on-green, output gate + spill | Fixes 1 Polyglot task end-to-end; commit | — |
| 15:00–16:30 | Bench harness: task list (seeded 30), temp copy, identical prompt for both agents, step/time caps, clean-copy grading (restore tests), JSONL results, cost from the Bifrost log/our ledger with one price table | `bench --tasks 3` runs both agents and writes JSONL | — |
| 16:30–17:00 | Break; commit; start `bench --tasks 10 --seeds 1` in the background | Running | — |
| 17:00–19:00 | R4 approvals: TTY prompt, argv-only `run_cmd`, hardened git env, substring provenance → red label. 4 pytest cases | Red "suggested by README.md:40" shows on a fixture | — |
| 19:00–20:30 | R3 confidential: marker walk-up, local-only client, `fallbacks: []`, Tavily unregistered, `audit` query + canary grep. 3 pytest cases | Confidential fixture: "send to GPT" → only `ollama/*` rows | Ollama too slow → use a 3b model for the demo |
| 20:30–21:00 | Read the 10-task smoke: our pass/cost vs baseline. **Write the numbers down** | First real comparison | If we are >2× more expensive, fix the cause first on 13 Nov AM |
| 21:00–22:30 | R2 budget: reservation (`BEGIN IMMEDIATE`, max fallback price × `max_tokens`), reconcile, 80% warning, ladder → pause | Unit test: 8 procs, overshoot = 0 | — |
| 22:30 | Commit, 5-line progress note, stop | — | — |

### 13–15 Nov

| Day / block | Build | Done when |
|---|---|---|
| **13 Nov AM** (09–13) | `bench race` (8 procs, naive vs ours); R1 takeover banner from headers; ladder demo for "Bob $0.05" | Race table ours $0.0000 vs naive > 0; banner on a bogus primary |
| 13 Nov PM (14–18) | Token levers behind flags: masking, `cache_control` prefix, thrash detector + escalation banner, ruff + targeted-tests verification; gated Tavily `web_docs` | Each flag toggles; 5-task smoke not worse than the 12 Nov smoke |
| 13 Nov eve (18–22) | `quote`, status line, receipt; ~15 pytest; CI (ubuntu + windows). **22:00: start the full bench seed 1** (30 × ours + baseline) overnight | CI green; seed 1 running |
| **14 Nov AM** (08–12) | Read seed 1, fix only crash bugs (any behaviour change → rerun). Run seed 2 + all-off ablation (parallel 4 workers). **12:00 feature freeze** | Seed 2 + ablation running |
| 14 Nov PM (12–18) | `report.py` (paired diff, bootstrap CI, CPST, chart); nice-to-have #2 (mini red-team) and #3 (undo of edits) only if the bench is running cleanly; `prep.ps1` + demo repos | `bench/report.md` |
| 14 Nov eve (18–23) | **18:00 numbers frozen.** Record all video segments (backup = the video). README from the frozen numbers; description/problem/tech/AI-use text; fresh-clone test | Clips recorded; README draft |
| **15 Nov** | 07:00–09:30 video edit + captions (re-record a segment only if broken). 09:30–10:30 README polish, secret scan, repo public. 10:30–11:00 submit form. 11:00–12:00 buffer | Submitted ≤ 11:00 |

**If teammates join:** person 2 owns the bench + report from 12 Nov 15:00. Person 3 owns R3/R4 + tests. Person 4 owns the README/video/submission from 14 Nov. Atul keeps the loop, budget and levers.

---

## 4. Doc edits to make (in order, ~45 min, today after 22:30 or tomorrow 08:30)

| Doc | Edit |
|---|---|
| **TEAM-BRIEF** §3, §6, §7, §8 | Replace the "We add, and show live" table with the slice. Replace the timeline with §3 here. Add the mini-swe-agent "baseline only" rule. Add risks C1 (Windows baseline), C2 (Polyglot ≠ bug-fix), D (lean baseline) |
| **DESIGN** §1 | Remove the claims for cut items (taint wallet, shadow-git side-effect undo, hash chains, 45-case suite, tree-sitter); move them to "Roadmap" |
| DESIGN §8 | Matrix rows point only to slice tests |
| DESIGN §10.2–10.4 | New plan; the "never cut" list = the slice; bench = paired 30 × 2 seeds + all-off ablation; grading in a clean copy; one cost source |
| DESIGN §13 | Delete/park "canary-verified", "undo that reverts command side effects" and the 45-bypass wording until built; add "paired non-inferiority" wording; no "solve more" |
| DESIGN §14 | Add slendertoken; thrift-agent licence = MIT |
| **PLAYBOOK** §1, §10 | New 10-s one-liner (F3) and tagline (F4) |
| PLAYBOOK §2 | Re-write the Innovation / Use of AI / Scalability rows per F2, G, H |
| PLAYBOOK §3 | Re-time the video: tokens 0:00–1:30, rules 1:30–2:45; drop the red-team segment unless nice-to-have #2 exists |
| PLAYBOOK §6, §8, §9 | Add the submission gaps (I) and demo risks (E); fixed times from §3 here |
| PLAYBOOK §7 | Q7 fairness controls (C4); new Q: "Why Polyglot, not SWE-bench?" (no Docker on Windows in 3 days; paired design; mutation set if built) |

---

## 5. Answers to have ready

- **"Isn't this just mini-swe-agent with extras?"**
  - No. We use it only as the baseline. Our loop is written from scratch and has structured tools rather than bash-only. That is *why* approvals can be enforced in code.
- **"30 tasks is tiny."**
  - Yes, so we use a paired design: per-task cost ratio on commonly solved tasks plus pass-rate non-inferiority, with a bootstrap CI, raw logs and one command to rerun. We make no significance claims on pass rate.
- **"Your savings are only X%."**
  - That is against the leanest open baseline, not a straw man. Against our own all-off twin (the comparison other entries use) it is Y%. And we get it while enforcing four guarantees the baseline doesn't have.
