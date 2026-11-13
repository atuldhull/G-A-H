# 02 · Build plan, 12–15 Nov 2026

Status 12 Nov morning: design v5 frozen, 0 lines of code, builder likely solo on Windows 11, token-metered Claude plan. Build closes **15 Nov 12:00** (we submit by 11:00). Source: review 08 §3, adjusted for the v5 fixes.

**Token rule for building with Claude Code:** give it this file plus the one architecture section the task needs. Never paste the whole doc set.

## 1. Tiers

**P0 (must ship by 14 Nov evening)**
- Own ~400-line loop: `read`, `search`, `list`, `edit` (staged SEARCH/REPLACE), `run_tests`, `run_cmd` (argv), git read templates, step cap 30, pinned task state.
- Token/accuracy: cache-stable prefix; output gate (head + tail + failures + spill + secret scan); read cache; batched masking; verification ladder (syntax → ruff isolated → affected → full); stop-on-green with oracle freeze and id-set baseline; simple thrash detector; cheap-first escalation.
- R1: prefixed chain + explicit fallbacks, MODEL TAKEOVER banner with error class, journal + idempotent resume.
- R2: reservation at chain max + tier, lease, hold on timeout, never above remaining; admin-only `limits.yaml`; ladder strong → cheap → local → pause; race demo + invariant test.
- R3: marker/registry via realpaths (up + bounded down), local-only VK, prefixed ids, `fallbacks: []`, local model allowlist (reject `:cloud`/`-cloud`, non-loopback `OLLAMA_HOST`), fit to `OLLAMA_CONTEXT_LENGTH`, Tavily off, egress log, canary audit.
- R4: console-only approvals, argv-only commands, test consent (repo code execution), exec-surface re-prompt, hardened git with per-call config check and rev validation, Windows paths/exe, provenance-lite red prompt naming `file:line`, file-edit undo via shadow git, state integrity (HMAC + watch-set).
- Tavily `web_docs` gated. User `doctor`, `audit`, static `quote`, status line, receipt.
- Bench (Polyglot 34 + QuixBugs 20, paired vs mini-swe-agent + all-off twin) and red-team MVP (15 cases).

**P1 (only after P0 is green, in this order)**
1. Undo of command side effects. 2. Hash-chained journal/egress. 3. Waste breakdown. 4. Tree-sitter bash explainer. 5. Compaction. 6. Quote refinement from traces. 7. Early termination. 8. More RT cases (TOCTOU swap, planted `git.bat`, ANSI argv). 9. Admin doctor + signed attestation, `admin set-limit` via the Bifrost API. 10. Breaker + local last-resort tail. 11. Localisation funnel + agent-written repro test. 12. Tavily via Bifrost Relay.

**P2 (roadmap slide only, never claimed as built)**
Full taint wallet (FIDES-lite), restricted-token / Low-IL sandbox or separate OS user, team dashboard, VS Code extension, Postgres team ledger, hostile model stub.

## 2. Hard cut list (do not start before 15 Nov)

PowerShell explainer · PageRank repo map · cache-break blame · `pytest-testmon` · per-layer ablation grid · Sonnet grid · `experience` TF-IDF · three-column race with real Bifrost (unless time) · branding/logo work · website · slides beyond 6.

## 3. 12 Nov, hour by hour

Shift the whole day if the start is late; the go/no-go decisions keep their order.

| Time | Task | Done when | Go/no-go |
|---|---|---|---|
| 09:00–09:30 | Scope frozen (v5). Package skeleton in GaH, `.gitignore` with `.env`, MIT licence. Commit at least hourly | First commit | — |
| 09:30–10:45 | Day-0 installs and checks 1–5 (§6) | Bifrost answers with usage incl. cached tokens; bogus primary → `is-fallback: true` | **10:45:** if Bifrost fallback/VK fails, client-side retry on the next model with the same banner, disclosed |
| 10:45–11:45 | Baseline smoke: mini-swe-agent 2.4.6 in WSL2 → Bifrost, 1 Polyglot task | Its tokens appear in Bifrost logs | **11:45:** no-go → baseline = all-off twin only; drop the mini-swe-agent claim |
| 11:45–12:15 | Break | — | — |
| 12:15–15:00 | Core loop: `egress` (reservation stub, socket guard), journal, tools, staged matcher, `run_tests` with consent, pinned state, stop-on-green, output gate + spill | One Polyglot task fixed end-to-end; commit | — |
| 15:00–16:30 | Bench harness: task copy without `.meta/`, identical task text, caps, restore tests + grade, JSONL, cost from Bifrost logs × `prices.yaml` | `bench --set polyglot --limit 3` runs both agents | — |
| 16:30–17:00 | Break; start `bench --limit 10 --runs 1` in the background | Running | — |
| 17:00–19:00 | R4: CONIN$ approvals, escaping, argv-only `run_cmd`, hardened git + per-call check + rev validation, provenance-lite, exec surface | Red "suggested by README.md:40" on a fixture; RT 1–3, 8, 9, 11 pass | — |
| 19:00–20:30 | R3: `mode_for` (realpaths up + down), local-only client, allowlist, Tavily unregistered, egress asserts, `audit` | Confidential fixture: "send to GPT" → only `ollama/*` rows; RT 5–7 pass | Ollama too slow → `qwen2.5-coder:3b` for the demo |
| 20:30–21:00 | Read the 10-task smoke; write the numbers down | First comparison | **>2× baseline cost** → fix the cause first on 13 Nov AM |
| 21:00–22:30 | R2: reservation (tiers, lease, clamp to remaining), reconcile, 80% warning, ladder → pause | `test_concurrency_50` + `test_tier_reserve` pass | — |
| 22:30 | Commit, 5-line progress note, stop | — | — |

## 4. 13–15 Nov

| Block | Build | Done when |
|---|---|---|
| **13 Nov AM** (09–13) | `bench race` (8 procs, ours vs naive); integrity (HMAC key, watch-set, scratch profile, job object); failover banner with error class; `tool_started` + resume | Race ours $0.0000 vs naive > 0; RT 4 passes; bogus-key banner shows `auth`; `crash_resume_mid_cmd` passes |
| 13 Nov PM (14–18) | Levers behind flags: masking, cache prefix, read cache, verification ladder, thrash + escalation banner; oracle freeze + id-set green; Tavily `web_docs` | Each flag toggles; RT 13–14 pass; 5-task smoke not worse than 12 Nov |
| 13 Nov eve (18–22) | Static `quote`, status line, receipt; shadow-git file undo; user `doctor`; remaining RT cases; CI (windows + ubuntu). **22:00: start bench run 1** (54 tasks × ours + mini) | CI green; RT 15/15; run 1 running |
| **14 Nov AM** (08–12) | Read run 1, fix crash bugs only (behaviour change → rerun). Start run 2 + all-off twin (parallel 4). **12:00 feature freeze** | Run 2 + twin running |
| 14 Nov PM (12–18) | `report.py` (paired diff, bootstrap CI, CPST, cost ratio, Pareto); P1 items 1–3 only if the bench runs cleanly; `scripts\prep.ps1`, demo repos | `bench/report.md` |
| 14 Nov eve (18–23) | **18:00 numbers frozen.** Record every video segment (the backup = the video). README from frozen numbers; description, problem, tech, AI-use text; fresh-clone test | Clips recorded; README draft |
| **15 Nov** | 07:00–09:30 video edit + captions. 09:30–10:30 README polish, secret scan, make the submission repo public. 10:30–11:00 submit. 11:00–12:00 buffer | Submitted ≤ 11:00 |

Team of 4: see [04-team-split.md](04-team-split.md) for parts, interfaces and milestones.

## 5. Go/no-go checkpoints

| When | Check | If no |
|---|---|---|
| 12 Nov 10:45 | Bifrost fallback + VK enforcement work | Client-side failover, disclosed |
| 12 Nov 11:45 | mini-swe-agent runs one task in WSL2 via Bifrost | All-off twin as the only baseline; pitch says so |
| 12 Nov 21:00 | 10-task smoke cost ≤ 2× baseline | Fix the top waste cause before new features |
| 13 Nov 13:00 | Race demo + integrity done | Drop P1 entirely; protect bench time |
| 13 Nov 22:00 | Bench run 1 started | Cut QuixBugs to 10 tasks; 1 run for the twin |
| 14 Nov 12:00 | Feature freeze | Anything unfinished → roadmap slide |
| 14 Nov 18:00 | Numbers frozen | Ship what exists; never edit numbers by hand |

## 6. Day-0 checklist (Atul runs installs)

Installs:
- [ ] `py -3.12 -m venv D:\global_ai_hackathon\.venv`; `pip install -e .[dev]` (httpx, typer, rich, pyyaml, pydantic, keyring, tiktoken, pytest, ruff, matplotlib).
- [ ] Bifrost, pinned: `npx -y @maximhq/bifrost --transport-version v2.5.1 -app-dir D:\bifrost -host 127.0.0.1 -port 8080`, with `bifrost\config.json` copied to `D:\bifrost\` (schema: [04 §7](architecture/04-data-model.md)). Admin auth on.
- [ ] Ollama: `setx OLLAMA_CONTEXT_LENGTH 32768`, `setx OLLAMA_NO_CLOUD 1`, restart Ollama, then `ollama pull qwen2.5-coder:7b` (in the background).
- [ ] Git for Windows, ripgrep, ruff on PATH (outside any repo).
- [ ] WSL2 Ubuntu with Python 3.12 and `pip install mini-swe-agent==2.4.6`; `.wslconfig` `networkingMode=mirrored`.
- [ ] VKs created in the Bifrost UI: `atul-public`, `atul-local`, `bob-public` ($0.05), `bench` ($15); `crocodile init` stores them in Credential Manager.

Checks (record results in [09 §6](architecture/09-bifrost-and-tavily.md), then remove the UNVERIFIED tags):
1. `/v1/chat/completions` with a prefixed model + `fallbacks` → routing headers; bogus primary key → `is-fallback: true`; which error class is logged.
2. Second identical call → `cached_read_tokens > 0`, and `prompt_tokens` includes them.
3. `fallbacks: []` + `ollama/…` on the local VK → Bifrost log shows only Ollama; local VK asking for `anthropic/…` → refused.
4. `$0.001` VK budget → 402 `policy_budget_exceeded`; does the fallback also get refused?
5. `POST /anthropic/v1/messages/count_tokens` with a VK works.
6. Ollama tool call through Bifrost with `qwen2.5-coder:7b` at 32k context.
7. `/api/logs`: fields, filters by request id, requires auth?
8. `GIT_CONFIG_GLOBAL=NUL` and `-c core.hooksPath=<empty dir>` work on Git for Windows; fsmonitor fixture does not fire.
9. Haiku 5.5 via Bifrost: thinking tokens in `completion_tokens`; empty reply on `max_tokens` (#9888) handled.
10. mini-swe-agent in WSL2 reaches `127.0.0.1:8080` (mirrored networking) and solves or fails one task with usage logged.

Also today: check Discord for video length, deadline time zone and the track/problem ID for the form.
