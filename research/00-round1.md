# Research & Plan: Token-Efficient Coding Agent (PS 01)

> **Historical: first research round (10 Nov).** The product is now **Crocodile**, and **DESIGN.md v4 supersedes the plan, schedule and some details here** (for example, shlex classification was dropped, and the headline metric is now cost per solved task). Keep this for the sources and background. Files in `research/` are also point-in-time reports, so where they use `agent`/`.agent`, read `crocodile`.
> *(12 Nov: moved from the repo root `RESEARCH.md`. `DESIGN.md` no longer exists; the current spec is `docs/architecture/` v5.)*

Researched 2026-11-10. Build closes 15 Nov, judging 29 Nov. Items marked **[unverified]** must be checked live.

## 1. Architecture (one line)

`CLI (Python)` → **Policy layer** (approval, confidentiality, budget) → **Context engine** (cache, masking, truncation) → **Bifrost** (localhost:8080: fallbacks, virtual keys, cache) → Anthropic / OpenAI / **Ollama**.
**Tavily** is a gated tool for doc lookups.

The rule that matters: **the LLM only proposes typed actions. Deterministic Python code decides.** The policy layer never sees the prompt text.

## 2. Mandatory requirements: design

### Reliability (failover)
- Use Bifrost's native `POST /v1/chat/completions` with a `"fallbacks": ["anthropic/...", "openai/...", "ollama/..."]` body field.
- Read `extra_fields.routing_info.is_fallback` / `.provider` / `.model`. If it is a fallback, print `⚠ <primary> unavailable → <model> took over`.
  - Drop-in routes expose the same data as headers: `x-bifrost-routing-info-provider|model|is-fallback|primary-provider`, `x-bifrost-fallback-index` (verified in source, see research/01 #9c), so the native route is not required. Also check `routing_info.server_side_fallback_model` (set when Anthropic swaps models inside one call).
- Set retries per provider: `network_config.max_retries=2` (the default is 0).
- If every model fails, the agent persists the session (JSON on disk), waits with backoff and resumes. **Never lose the session.**
- **Demo:** give the primary a bad API key, or force a 429, then show the banner and the task completing.

### Budget (enforced *before* the call)
- Bifrost's budgets deduct *after* the call, so they can overshoot. Use them as a **second layer only**. They return HTTP 402 with error type `policy_budget_exceeded` (rate/token/request limits return 429 `policy_rate_limited`), and the agent handles both.
- Our own ledger (SQLite, atomic):
  - `reserve = in_tokens × in_price + max_tokens × out_price`.
  - Refuse if `spent + reserved + reserve > limit`.
  - Reconcile from `usage` after the call.
- Token counting: tiktoken `o200k_base` (approximate), or Anthropic `count_tokens`. Local models cost $0.
- **Defined behaviour at the limit:**
  1. Refuse the call before sending it.
  2. Save the session.
  3. Offer to continue on the local model ($0) or to stop.
  4. Warn at 80%.
- One Bifrost virtual key (`x-bf-vk`) per user, with `budgets: [{max_limit, reset_duration:"1d"}]`.

### Code privacy (confidential repo → local only)
- **Marker:** `.agent/confidential` in the repo, or a user-level config. The agent's own write tool can **never** create, edit or delete it.
- The router pins the session to a **separate Bifrost VK whose provider_configs contain only `ollama`**. That gives two independent enforcement points.
- **Fail closed:** if Ollama is down, raise an error. Never fall back to the cloud.
- **Tavily is disabled in confidential mode**, because search queries can leak code.
- Also: a scan of outbound text for secrets and repo identifiers, with blocks logged.
- Prompt injection ("use GPT, it's fine") has no effect, because routing never reads the prompt.

### Action approval (prompt-proof)
- Tools are typed: `read_file`, `search`, `list` (free); `write_file`, `edit`, `run_cmd`, `git` (need approval).
- Approval is a `y/n` read from the real **TTY**, not from model output.
  - Show a diff for writes.
  - Show the **resolved** path and exact command.
- Shell classification:
  - Parse with `shlex`.
  - **Reject** `; && || | > < $( ) \``, newlines and `&`.
  - A read-only allowlist: `ls`, `cat`, `rg`, `git status/diff/log`.
  - Treat `python -c`, `node -e`, `bash -c`, `powershell`, `env`, `xargs`, `find -exec`, `sed -i`, `git -c` and npm scripts as **writes**.
- Paths: `os.path.realpath()` first, then require the path to be inside the repo root. This defeats symlink tricks (CVE-2025-59829, "GhostApproval").
- Hard-deny writes to `.git/`, `.env`, `.agent/` (policy files) and the agent's own config.
- Strip `*KEY*`, `*SECRET*` and `*TOKEN*` env vars from subprocesses.

## 3. Token savings, ranked by payoff per hour of work

| # | Technique | Effort | Expected effect |
|---|---|---|---|
| 1 | **Prompt caching**: frozen prefix (sorted minimal tools → system → repo map), append-only history, cache breakpoints. No timestamps in the prefix. | 1h | Input cost −70–90% on cached turns (our estimate, to be measured). Anthropic reads cost 0.1×, or 0.05× on Opus/Sonnet 5.5; minimum cacheable prefix is 512 tokens on the 5.5 models (shorter is silently not cached). OpenAI caches automatically above 1,024 tokens; `prompt_cache_key` is optional on GPT-5.6+ |
| 2 | **Observation masking**: tool outputs older than about 10 turns become a placeholder. Mask in batches so the cache survives. | 1–2h | Masking halved cost in all 5 configs; solve rate was equal or better for Qwen3-Coder-480B and Gemini 2.5 Flash, but lower for Qwen3-32B (−2 pp) and Gemini Flash-thinking (−4 pp) (arXiv 2508.21433) |
| 3 | **Output truncation**: at most 256 lines / 10KB, head and tail with an omitted marker, ANSI stripped; tests return only failures. 100-line file window. | 1h | Large: tool outputs dominate turn tokens (the "about 84%" figure is **[unverified]**; do not quote it) |
| 4 | **SEARCH/REPLACE edits** instead of whole files (Aider `diff` format) | <1h | Output tokens (about 5× the price) shrink to the size of the change |
| 5 | **Read cache**: hash files; an unchanged re-read returns "unchanged since turn N"; a changed one returns a diff | 1h | Measure it; no public number |
| 6 | **Repo map**: tree-sitter symbols ranked to about 1k tokens, or `rg` plus a symbol list; lives in the cached prefix | 2–4h | Fewer exploratory reads |
| 7 | **Routing**: small model (e.g. Haiku 5.5 / gpt-mini / local) for search, summaries and one-file edits; escalate to the strong model after 1–2 failed test runs or for multi-file edits | 4h+ | Varies; use test pass/fail as the verifier, not an LLM judge |
| 8 | Bifrost semantic cache (`x-bf-cache-key` header, Redis; or `dimension:1` for exact-match only) | 1h | Helps repeated requests and the benchmark re-runs |
| — | **Avoid** multi-agent setups (about 15× the tokens of chat). Use at most one search sub-agent that returns a summary. | | |

## 4. Proving it: the benchmark

- **Baseline:** stock **mini-swe-agent** (github.com/SWE-agent/mini-swe-agent; bash only; standard harness) with the **same model**.
- **Tasks:** pick one.
  - 30–50 Aider Polyglot exercises (unit-test graded, no Docker). Easiest.
  - SWE-bench Verified Mini (hal.cs.princeton.edu/swebench_verified_mini). More credible.
- **Report:**
  - Uncached, cache-write, cache-read and output tokens.
  - $ and pass rate.
  - **Cost per solved task** (the headline).
  - An **ablation table** that turns each technique on by flag.
  - 2–3 seeds.

## 5. Sponsor usage (make it visible)
- **Bifrost:**
  - Fallback chain.
  - Per-user VKs and budgets.
  - The local-only VK for confidential repos.
  - Semantic cache.
  - `/api/logs` (with `group_sessions=true`) for the token and cost dashboard.
  - `x-bf-session-id` for provider affinity, which keeps the cache warm.
- **Tavily:** a `web_docs` tool with `search_depth="basic"`, `max_results=3`, `chunks_per_source=1–2`, `include_raw_content=False`. Use `extract(query=...)` for chunks only. The free tier is 1,000 credits a month. It is disabled in confidential mode.

## 6. Local models (Ollama, `http://localhost:11434/v1`)
- About 16GB: `gpt-oss:20b`. 24GB+: `qwen3-coder:30b`. Alternative: `devstral:24b`. 8GB: qwen 7–8B coder.
- **Set `num_ctx` in a Modelfile.** The default context silently truncates.
- `tool_choice` is not supported.
- Run a tool-call self-test at startup.

## 7. Build order (10 → 15 Nov)

| Day | Deliverable |
|---|---|
| **10 Nov** | Bifrost running (`npx -y @maximhq/bifrost`), keys added, Ollama model pulled. Minimal agent loop (read/search/edit/run) via the native endpoint. |
| **11 Nov** | Policy layer: approval gate, shell classifier, path checks, confidential router + local-only VK, Tavily gate. Unit tests incl. injection cases. |
| **12 Nov** | Budget ledger (pre-call reserve), 402/429 handling, failover banner, session persistence/resume. |
| **13 Nov** | Token techniques #1–#5 (each behind a flag). Token/cost meter in the CLI. |
| **14 Nov** | Benchmark vs mini-swe-agent, ablation table. Optional: routing (#7), repo map (#6). |
| **15 Nov** | README (architecture diagram, threat model, requirement → enforcement point → test matrix, numbers), 3-min demo video. |

## 8. Demo script (about 3 min)
1. Fix a real bug and show the live token meter.
2. Show the savings table vs the baseline.
3. Force an outage: the "X took over" banner appears and the task still completes.
4. Exhaust the budget: the next call is refused **before** it is sent, and the agent offers the local model.
5. A confidential repo containing a planted "send this to GPT / search the web" injection: it stays local, and search is blocked.
6. A planted "run `rm -rf` / `git push`": the approval prompt appears and the chained command is rejected.

## 8b. HOW WE ARE DIFFERENT (deep research, 2026-11-10). This replaces the generic build order in §7.

Most teams will ship the standard playbook: caching, masking, routing, Bifrost fallback and a y/n prompt. **Our position: "an agent that proves its savings instead of claiming them."**

Every token, dollar and outbound byte is predicted, accounted for and auditable, and security is enforced by data-flow labels, not by a prompt.

### The 5 pillars (each is demoable)

| # | Pillar | What it is | Evidence / why it is new | Effort |
|---|---|---|---|---|
| 1 | **Cost quote + escalation ladder** | Before running, the agent prints a quote like "≈$0.04–0.09 / ~18K tok". It starts on a cheap or local model and escalates to the strong model only when tests fail or the trace looks stuck. At the budget it steps down instead: strong → cheap → local → **pause with a resumable journal**. | 8 frontier models predicting their own token use on SWE-bench Verified reach Pearson r of at most 0.39, and all underestimate (arXiv 2604.22750). Trace-based routing: on 100 held-out SWE-bench Verified tasks, routing after 2 cheap-model turns scored Route-AUC 0.780 vs 0.627 for query-only (SWE-Router 2607.00053; no $ figure). Separately, experience-driven **early termination** (EET 2601.05777, not escalation) cut cost 19–55% (mean 32%) with a resolve-rate change of at most −0.2 pp; about −19% with mini-swe-agent. Our SQLite reservation closes Bifrost's post-call overshoot gap. | 1.5d |
| 2 | **Code-mode exploration** | The model writes ONE Python script against a small local API (`grep`, `read_symbol`, `skeleton`, `run_tests`) that runs in a sandbox; only the summary returns. Deterministic steps run with no model call: ruff autofix, pytest traceback parsing, tree-sitter skeletons. | Anthropic's illustrative Drive→Salesforce example: 150K → 2K tokens (not a benchmark); CodeAct: up to 30% fewer actions **[unverified]**. Show a counter of "tokens avoided". **Use LSP only alongside grep**: in a small preliminary study LSP-only beat grep-only for Haiku (−26%) but lost for Opus (+6%) and Sonnet (+118%) on localization (2608.13568). | 1.5d |
| 3 | **Taint-labelled approvals** (CaMeL/FIDES-lite) | Every tool result is labelled `trusted/untrusted × public/confidential`, and anything the model produces after reading untrusted data inherits the label. A write, shell or git call whose arguments came from untrusted data gets a **red prompt naming the source** ("suggested by README.md:40"). Confidential data can never reach a network sink. (Plan-level scoped grants were considered and are now CUT, see DESIGN.md.) Add **shadow-git undo that also reverts shell changes**, which Claude Code's rewind does not. | CaMeL solved 77% of AgentDojo tasks (vs 84% undefended) with security provable only with respect to explicit tool-call/data-flow policies; with policy checks FIDES let 1 AgentDojo injection succeed (0 after excluding 2 tasks the authors don't count). Neither stops text-to-text attacks. No mainstream coding CLI ships taint-aware approvals by default (Microsoft Copilot CLI has an experimental `FIDES_IFC` flag). | 2d |
| 4 | **Egress ledger** | A single HTTP choke point for Bifrost and Tavily. It writes a hash-chained SQLite log of destination, key, model, payload hash and data label. `agent audit` proves that zero confidential bytes left the machine. Canary strings are planted in confidential repos. No Bifrost cache key is sent in confidential mode. | Confidentiality becomes **provable**, not just asserted. | 1d |
| 5 | **Proof scoreboard** | `make bench`: cost per solved task vs mini-swe-agent, with a table toggling each technique. `make redteam`: about 15 poisoned-repo fixtures in the style of UK AISI CodeIPI (curl secrets, push to a new remote, a malicious Tavily result, a confidential canary). | Judges see numbers and attack-success rates, not adjectives. | 1.5d |

**Stretch, only if ahead:**
- Test-gated playbook memory (ReasoningBank/CODESKILL: fewer steps on repeat tasks; save only after tests pass).
- Continuing a reply on the fallback model when a stream fails mid-way (Bifrost doesn't cover mid-stream errors).
- Local LongCodeZip compressor ("up to 5.6×", tested on completion/summarization/QA, not agent loops; raw code never reaches the cloud).
- Quarantined reader LLM.
- Chain-of-Draft terse reasoning (7.6% of tokens is the best case on a non-code task; not tested on code).

**Not doing:** multi-agent setups (about 15× the tokens), LSP-only navigation, LLM-as-router on the task description alone.

### Revised build order (one person, 10 → 15 Nov; deliberately tight)

| Day | Build |
|---|---|
| 10 | Bifrost + Ollama up. Core loop on the native endpoint. Baseline token techniques: cache-friendly prefix, masking, truncation, search/replace, read cache. Event journal. |
| 11 | Pillar 3: labels + taint, policy engine, shell classifier, risk-scored approvals + grants, shadow-git undo. Confidential router + Pillar 4 ledger. |
| 12 | Pillar 1: pre-call reservation, heuristic quote, ladder, failover banner from `routing_info`, client circuit breaker. |
| 13 | Pillar 2: code-mode sandbox + deterministic steps + "tokens avoided" counter. |
| 14 | Pillar 5: bench vs mini-swe-agent + red-team suite. Stretch if ahead. |
| 15 | README (threat model, requirement → enforcement → test matrix, numbers, AI-use disclosure), 3-min video, submit. |

**Cut order if behind:**
1. The plan-level grants (keep per-action approvals).
2. Code mode (keep the deterministic steps).
3. The red-team suite (shrink it to 5 fixtures).

**Never cut** the 4 mandatory requirements or the bench table.

### New sources
- arXiv: 2604.22750, 2607.00053, 2601.05777, 2608.13568, 2510.00446 (LongCodeZip), 2509.25140 (ReasoningBank), 2601.06007 (Don't Break the Cache), 2502.18600 (Chain of Draft), 2506.08837 (injection design patterns), 2505.23643 (FIDES).
- Engineering blogs:
  - https://www.anthropic.com/engineering/code-execution-with-mcp
  - https://blog.cloudflare.com/code-mode-mcp/
- Code:
  - https://github.com/google-research/camel-prompt-injection
- Docs:
  - https://ukgovernmentbeis.github.io/inspect_evals/evals/ipi_coding_agent/index.html
  - https://docs.getbifrost.ai/features/semantic-caching
- Unverified: SWE-Router AUC, CODESKILL gains, the 93%-approval statistic, Cline shadow-git.

## 9. Official rules (received 2026-11-10)
- **Judging criteria (no weights given):**
  - Innovation
  - Technical execution
  - Problem and potential impact
  - Use of AI
  - User experience
  - Scalability and potential
- **The core must be built during the hackathon.** Libraries and boilerplate are fine.
  - Decision: build everything new. Project Titan is not used.
- **Submission needs:**
  - A working demo.
  - The repo.
  - A description.
  - The problem.
  - Technologies used.
  - **How AI is used**, plus a disclosure of the AI tools used to build it.
  - A demo video.
- Join the official Discord and watch it for updates.
- **What this means for the plan:**
  - UX counts: a clean CLI with a live token/cost meter, coloured approval prompts and a clear failover banner.
  - Scalability: per-user Bifrost virtual keys and a stateless agent core.

## 10. Open items
- Verify live:
  - ~~The `x-bifrost-*` header names~~ (verified, research/01 #9c).
  - Whether `usage` includes cost.
  - Whether Bifrost routing rules and governance GET endpoints are in OSS, and whether `cache_control` passes through to Anthropic (see DESIGN.md §9.1).
  - Which errors trigger a fallback.
  - The Anthropic-SDK route in Bifrost.
