# 02 · Competitor teardown (researched 2026-11-10)

Scope: 12 coding agents × the 6 dimensions that map to our mandatory requirements, plus peer hackathon projects.
Evidence comes from official docs, GitHub issues and advisories, and security write-ups. Items marked **[unverified]** come from secondary sources only and need checking before we quote them in the README or video.

Legend: ✓ = built in and documented · ◐ = partial (opt-in, enterprise-only, post-hoc, or with caveats) · ✗ = absent / needs an external gateway or plugin

---

## 1. Comparison matrix

| Agent | 1 Token efficiency | 2 Failover + notice | 3 Per-user cap, enforced pre-call | 4 Forced local-only per repo | 5 Approval model (and known bypasses) | 6 Main complaints |
|---|---|---|---|---|---|---|
| **Claude Code** | ✓ caching with cache-hit stats in `/usage`, auto-compact, subagents, deferred MCP tools, Bash output cap ([costs doc](https://code.claude.com/docs/en/costs)) | ◐ `fallbackModel` chain (≤3) with a notice, but **only on overload/unavailable; 429, billing and auth errors never trigger it**; the switch lasts one turn ([model-config](https://code.claude.com/docs/en/model-config)) | ◐ `--max-budget-usd` (print mode only; stops with `error_max_budget_usd`); Team/Enterprise per-member spend limits; per-user caps via the self-hosted "Claude apps gateway" ([costs doc](https://code.claude.com/docs/en/costs)) | ◐ managed `availableModels` allowlist is org-wide, not per repo, and not "local only" ([managed settings](https://code.claude.com/docs/en/managed-settings)) | ✓ modes, allow/deny rules, OS sandbox (−84% prompts, [Anthropic](https://anthropic.com/engineering/claude-code-sandboxing)), `/rewind` **does not track bash changes** ([checkpointing](https://code.claude.com/docs/en/checkpointing)). Bypasses: CVE-2025-59536, CVE-2026-21852 ([THN](https://thehackernews.com/2026/02/claude-code-flaws-allow-remote-code.html)), many deny-rule bypass issues ([#25621](https://github.com/anthropics/claude-code/issues/25621)) | weekly limits / opaque usage ([VentureBeat](https://venturebeat.com/ai/anthropic-throttles-claude-rate-limits-devs-call-foul)); `rm -rf ~` ([Docker blog](https://www.docker.com/blog/coding-agent-horror-stories-the-rm-rf-incident/)) |
| **Codex CLI** | ✓ auto-compaction (server-side for OpenAI models), automatic OpenAI caching ([compaction issue](https://github.com/openai/codex/issues/4106)) | ✗ retries 429s, but no model or provider fallback; switch profiles by hand or use a gateway [unverified, 3rd party](https://codex.danielvaughan.com/2026/04/12/codex-cli-rate-limiting-backoff-retry-quota/) | ✗ no $ cap in the CLI | ◐ per-profile providers, `requirements.toml` for admins; no repo-level fail-closed rule | ✓ strongest sandbox: approval policy × sandbox mode, network off by default in workspace-write ([docs](https://developers.openai.com/codex/agent-approvals-security)). CVE-2025-61260: project `.env` → `CODEX_HOME` → MCP commands ran with no prompt ([Check Point](https://research.checkpoint.com/2025/openai-codex-cli-command-injection-vulnerability/)) | compaction without consent; the agent forgets work after compacting ([#4106](https://github.com/openai/codex/issues/4106)) |
| **Aider** | ✓ tree-sitter repo map (`--map-tokens` 1k default), diff/SEARCH-REPLACE edit formats, `--cache-prompts` ([caching](https://aider.chat/docs/usage/caching.html)) | ✗ retries only [unverified] | ✗ shows $ per message and per session; no cap | ✗ any LiteLLM model, no policy | ◐ confirms shell commands; git auto-commit + `/undo` (edits only). No sandbox | the repo map is a per-request tax on big repos; the cache breaks when the map refreshes ([guide](https://fast.io/resources/aider-token-limit/)) |
| **OpenHands** | ✓ LLMSummarizingCondenser, "up to 2× per-turn cost reduction" ([blog](https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents)) | ◐ SDK fallback profiles ([guide](https://docs.openhands.dev/sdk/guides/llm-fallback)); notice not documented | ◐ **Cloud: per-user monthly budgets enforced at gateway admission** ([budgets](https://docs.openhands.dev/openhands/usage/cloud/organizations/budgets)). OSS: `max_budget_per_task` not enforced in the run loop ([PR #741](https://github.com/OpenHands/benchmarks/pull/741)) | ✗ | ✓ Docker sandbox, LLM risk analyzer + `ConfirmRisky` policy ([security](https://docs.openhands.dev/sdk/guides/security)). The analyzer is **the model rating its own actions**; its own blog calls confirmation mode "a stopgap" ([blog](https://openhands.dev/blog/mitigating-prompt-injection-attacks-in-software-agents)) | the condenser invalidates the cache; costs are unclear ([PR #741](https://github.com/OpenHands/benchmarks/pull/741)) |
| **Cline** | ✓ auto-compact (cached input, so you pay mostly for the summary), cost shown per request ([auto-compact](https://docs.cline.bot/features/auto-compact)) | ✗ native; only through Requesty/OpenRouter | ✗ shows $; no hard cap | ◐ works with Ollama; nothing enforces it | ✓ per-tool approval, auto-approve, **shadow-git checkpoints** after every tool use ([checkpoints](https://docs.cline.bot/core-workflows/checkpoints)). The DSAI-Cline fork's auto-approve was bypassed with a newline, CVE-2026-30313 ([Tenable](https://www.tenable.com/cve/CVE-2026-30313)) | cost surprises with auto-approve; Focus Chain deprecated |
| **Roo Code / Kilo Code** | ✓ intelligent condensing ([Roo](https://docs.roocode.com/features/intelligent-context-condensing)); Kilo auto-compaction, `max_lines`/`max_bytes` tool truncation ([Kilo](https://kilo.ai/docs/getting-started/cost-controls-and-usage-safeguards)) | ◐ **Kilo "Virtual Quota Fallback": switches profile on API error or token/request quota, with an info message** (legacy IDE doc, [link](https://github.com/Kilo-Org/kilocode-legacy/blob/main/docs/legacy-ides/ai-providers/virtual-quota-fallback.md)). Roo: none | ◐ Roo "Max Requests" and "Max Cost" pauses on auto-approve ([v3.25.5](https://docs.roocode.com/update-notes/v3.25.5)). **Kilo orgs: per-user daily $ cap, blocked until 00:00 UTC** ([Kilo](https://kilo.ai/docs/getting-started/cost-controls-and-usage-safeguards)) | ✗ | ✓ per-tool allow/ask/deny, doom-loop pause, checkpoints | condensing cost not always shown in the UI (Roo docs contradict each other) |
| **Goose (Block)** | ◐ auto-summarise; lead/worker removed and replaced by a planner model ([PR #8471](https://github.com/aaif-goose/goose/pull/8471)) | ◐ old `GOOSE_LEAD_FALLBACK_TURNS` (model quality, not outages) | ✗ (`GOOSE_MAX_TURNS` only) | ✗ | ◐ `GOOSE_MODE` auto/approve/smart_approve/chat; docs disagree on the default (`auto` approves everything) ([env vars](https://block.github.io/goose/docs/guides/environment-variables)). Block's own red team got an infostealer running via a poisoned recipe ([Block](https://engineering.block.xyz/blog/how-we-red-teamed-our-own-ai-agent-), [Register](https://www.theregister.com/2026/01/12/block_ai_agent_goose/)). Adversary Mode = a second LLM reviews tool calls ([docs](https://goose-docs.ai/docs/guides/security/adversary-mode)) | pattern-based injection detector, opt-in |
| **OpenCode (sst/anomaly)** | ✓ auto-compact, LSP | ✗ native; long-open request [#7602](https://github.com/anomalyco/opencode/issues/7602), several community fallback plugins | ✗ | ◐ `enabled_providers` config; not fail-closed | ✗ **most permissions default to `allow`** ([docs](https://opencode.ai/docs/permissions)). CVE-2026-22812: unauthenticated local HTTP server → shell execution, also reachable from web pages via CORS ([GHSA](https://github.com/advisories/GHSA-vxw4-wv6m-9hhh)) | silent retries, no failover |
| **Crush (Charm)** | ◐ auto-summarise [unverified], LSP context | ✗ | ✗ | ✗ (`.crushignore` only hides files) | ◐ prompts per tool, `allowed_tools`, `--yolo` with a banned-command list ([permissions](https://next-docs.charm.land/crush/using-crush/permissions.html)) | — |
| **Gemini CLI** | ✓ chat compression, token caching (API key), `/stats` | ◐ **falls back Pro→Flash on quota/server errors; asks consent by default**, with silent fallback for utility calls ([model routing](https://geminicli.com/docs/cli/model-routing/)) | ✗ | ✗ | ◐ allowlist, sandbox (Docker/seatbelt), checkpointing. Tracebit: the allowlist checked only the first command, so `grep …; curl …` ran silently (fixed v0.1.14) ([CSN](https://cybersecuritynews.com/gemini-cli-vulnerability/)); GHSA-wpqr-6v78-jr5g (CVSS 10): `--yolo` ignored the allowlist in CI ([THN](https://thehackernews.com/2026/04/google-fixes-cvss-10-gemini-cli-ci-rce.html)) | **silent downgrade to Flash after one query** ([forum](https://discuss.ai.google.dev/t/bug-gemini-cli-downgrades-from-pro-after-1-query-api-dashboard-delay-22-oct-2025/107992), [#10722](https://github.com/google-gemini/gemini-cli/issues/10722)) |
| **Cursor agent** | ✓ embeddings index, Auto model routing, caching (closed source) | ◐ "Auto" model selection, not a declared failover | ◐ **Team per-member $ limits (docs), but "enforcement is not instant; usage can briefly exceed"**; per-user limits being moved to alerts ([spend limits](https://cursor.com/docs/account/billing/spend-limits), [forum](https://forum.cursor.com/t/team-admins-now-can-control-spend-alerts-and-limits/145259)) | ✗ Privacy Mode = no retention/training, **code still goes to Cursor's servers**; no offline mode ([privacy](https://docs.cursor.sh/settings/privacy-mode)) | ◐ auto-run allowlist. CVE-2025-54135 CurXecute (mcp.json written before approval), CVE-2025-54136 MCPoison (trust tied to the MCP name, not the command), denylist bypass via base64, quotes and scripts → denylist deprecated ([Tenable](https://www.tenable.com/blog/faq-cve-2025-54135-cve-2025-54136-vulnerabilities-in-cursor-curxecute-mcpoison), [Check Point](https://research.checkpoint.com/2025/cursor-vulnerability-mcpoison/)) | June 2025 pricing change → surprise bills, refunds ([TechCrunch](https://techcrunch.com/2025/07/07/cursor-apologizes-for-unclear-pricing-changes-that-upset-users/)) |
| **mini-swe-agent** | ✗ by design (bash only, linear history; ~100 lines) | ✗ | ◐ `cost_limit` / `step_limit` per run → `LimitsExceeded` (checked after each step, not reserved) ([config](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)) | ✗ | ◐ `mode: confirm` (human confirms each command); no sandbox outside Docker benchmarks | — (it is our baseline) |

---

## 2. Per-agent notes (only what matters to us)

**Claude Code.** This is the strongest incumbent on cost visibility.
- `/usage` shows the cache-hit %, misses and their likely causes, warm or cold TTL, and per-subagent/MCP attribution, plus a "fix" shortcut.
- Published numbers: about $13 per developer per active day, $150–250 a month; agent teams use about 7× the tokens.
- Failover exists with a notice, but it deliberately ignores 429s and billing errors, and it lasts only one turn.
- Caps exist at the org/seat level and in headless `--max-budget-usd`. On Max plans that cap is measured against estimated API-equivalent cost [unverified].
- No per-call reservation, and no "at the limit, step down to a local model" behaviour.
- Security is the weak spot:
  - Project-file trust-dialog bypasses (hooks, `ANTHROPIC_BASE_URL` redirect).
  - Dozens of issues on Bash permission matching: first-token-only deny checks, wrappers, `;`/`&&` not split, `$()`.
  - `/rewind` cannot undo shell side effects.

**Codex CLI.** Best-in-class OS sandbox: network off by default and two axes (approval × sandbox). It has no spend cap and no failover. Its 2025 CVE is the classic "config file in the repo becomes code" attack, the same class as Claude Code's.

**Aider.** It invented the techniques everyone copies (repo map, edit formats, prompt-cache warming). It has no caps, no failover and no sandbox; git auto-commits act as the undo.

**OpenHands.**
- Condenser with a published "2×" figure; it is the source of arXiv 2508.21433's comparison of masking vs. summarising.
- **Cloud already has per-user budgets enforced at a gateway before the request is admitted.** The OSS per-task budget is not enforced.
- Its security analyzer is the model scoring its own action risk, which a prompt injection can steer.

**Cline / Roo / Kilo.**
- Cline: shadow-git checkpoints after every tool use, covering file state. That includes files changed by commands *if they are inside the workspace* [verify].
- Roo: Max Requests / Max Cost pauses.
- **Kilo: org per-user daily $ caps, plus a quota/error-based provider fallback with a notice.** This is the closest thing to our reliability + budget combination among the IDE agents.

**Goose.** Block red-teamed it into running an infostealer. Its mitigations are pattern detectors and a second-LLM reviewer, which are probabilistic and not deterministic.

**OpenCode.** Permissive by default. Its critical CVE came from an unauthenticated local server. Failover is the top community request, met by about 5 plugins.

**Crush.** Simple per-tool prompts plus YOLO with a banned list. Nothing on cost or privacy.

**Gemini CLI.**
- The only mainstream CLI with **automatic quota failover**, Pro→Flash, consent-prompted.
- Users hate the *silent/unexpected* downgrade. The UX lesson: a notice alone is not enough; show *why*, *what it costs*, and *how to get back*.
- Its 2025 allowlist bypass (`grep; curl`) is the textbook case for our shell parser.

**Cursor.**
- Team per-member $ limits exist but are admittedly not instant (overshoot), and are drifting towards alerts.
- Privacy Mode is about retention, not transmission.
- Three CVEs in 2025 on MCP and auto-run trust.

**mini-swe-agent.** Our benchmark baseline. It has `cost_limit`, so "our baseline has no budget" is false. Ramp Labs used it to show that **agents ignore budget counters entirely**: 0 calls to `request_more_budget` in 5,000+ turns, and self-approval 79–97% of the time ([Ramp](https://labs.ramp.com/research/coding-agents-ignore-spend/)). This is our best citation for "budgets must be enforced outside the model".

---

## 3. Peer hackathon projects (same Bifrost + Tavily problem statement)

Found on GitHub. All are Geek Room Global AI Hackathon 2026 entries or look like them.

| Project | What overlaps with our plan | What it lacks |
|---|---|---|
| **StaleGuard** ([repo](https://github.com/Shrinu14/staleguard-agent)) | **Almost our entire mandatory design**:<br>• pre-call cost estimate against `USER_BUDGET_USD`, warning at 80%, "continue on local?" at the limit<br>• SQLite ledger + Bifrost VK 402 as a second layer<br>• unpriced models refused<br>• `confidential=true` → Ollama-only VK, chosen before the task text is read<br>• a malformed policy file counts as confidential; the agent can't edit it<br>• y/n diff approvals enforced in Python<br>• failover banner "Switched to X — Y unavailable"<br>• ablation table: repo map, truncation, compaction, routing, stable prefix (86% cached share) | Taint/provenance, shell-parser hardening, undo, egress proof, standard benchmark (12 home-made tasks, 1 seed, 8–50% success) |
| **Gidorah** ([repo](https://github.com/piyushdotcomm/gidorah)) | Per-phase cascade + **takeover banner**; VK budgets with 402 before the request + per-task caps; confidential = local key, Tavily off, network shell denied; **SHA-256 hash-chained sessions + `audit verify`**; per-turn receipts; cache-hit % in the status bar; 4-arm cost benchmark (cascade −47%; but "always cheap" was cheapest) | No taint labels, no undo, no shadow-git, no standard benchmark (12 home-made Node tasks, 1 run) |
| **TokenWise** ([repo](https://github.com/ashutosh9151/TokenWise)) | Bifrost failover, daily budget cap, Ollama for confidential repos, HITL for writes | Thin. No benchmark, no stated enforcement point |
| globhack, StaleBench, AgentBench Arena | Bifrost/Tavily benchmark harnesses | Not agents |

**Takeaway.** The 4 mandatory requirements are table stakes among peers, and two peers already ship our "defined behaviour at limit" and "hash-chained audit". We win only on what follows.

---

## 4. Gaps we can own (mapped to the RESEARCH.md §8b pillars)

| # | Gap (evidence) | Our pillar |
|---|---|---|
| G1 | **No agent reserves cost before a call.** Everyone checks after the call or at admission against what was already spent, so they overshoot: Cursor admits "not instant"; mini-swe-agent and Roo check after each step; OpenHands OSS doesn't enforce at all; Claude Code `--max-budget-usd` is headless only. Ramp shows the model can't self-police. | P1: SQLite **reservation** (in + max_out) with zero overshoot by construction; prove it with a test that fires N concurrent calls at a $0.01 limit |
| G2 | **No one does a budget-driven step-down ladder.** At the limit, everyone blocks, pauses or asks for more money. StaleGuard offers "local?" as a yes/no. | P1: strong → cheap → local → pause with a resumable journal, plus an **up-front quote** (range) that no competitor prints |
| G3 | **Failover ignores 429s in Claude Code, is consent-gated in Gemini, and is absent in Codex, Aider, OpenCode, Cline and Crush.** Gemini users hate silent downgrades. | Banner that says *why* (429 vs 5xx), *the cost delta* and *when we retry the primary*; never fails over **out of** confidential mode |
| G4 | **No mainstream agent enforces local-only per repo, fail-closed.** Cursor sends code to its servers even in Privacy Mode; Claude Code's allowlist is org-wide. | P4: egress ledger + **canary strings** + `agent audit` proving zero confidential bytes left. Peers assert this; we *prove* it with the canary test |
| G5 | **Every allowlist has been bypassed by string matching**: Gemini `grep;curl`, DSAI-Cline newline, Cursor base64/quotes, Claude Code first-token/wrappers/`$()`. | Real shell parsing + reject operators/newlines + wrappers count as writes; ship a **regression suite built from these public bypasses** (`make redteam`) |
| G6 | **Config-file-in-repo attacks are the top CVE class**: Claude Code hooks/BASE_URL, Codex `.env`→CODEX_HOME, Cursor mcp.json, Goose recipes. | Never read executable config or base-URL from the repo; policy files are write-denied and hash-pinned. Red-team fixture for each CVE |
| G7 | **Approvals don't say *who* suggested the action.** Only Microsoft's experimental Copilot CLI `FIDES_IFC` flag ([MS](https://commandline.microsoft.com/information-flow-control-moving-toward-secure-autonomous-agents/)) and small OSS projects (zeptoclaw, safe-chains draft) do taint. | P3: red prompt "suggested by README.md:40" — **our most unique feature among shipped CLIs** |
| G8 | **Undo doesn't cover shell side effects** (Claude Code docs say so explicitly); Aider `/undo` covers commits only. | P3: shadow-git snapshot before *every* approved write **and** shell call |
| G9 | **No one benchmarks cost per solved task against a standard baseline.** Peers use 12 self-written tasks with 1 seed; OpenHands "2×" is vendor-reported. | P5: mini-swe-agent, same model, standard task set, ≥2 seeds, ablation per flag |

---

## 5. Claims we must NOT make

- ❌ "First agent with automatic model failover and a user notice." Claude Code (overload), Gemini CLI (quota), Kilo (quota/error) and two peers already have it.
- ❌ "First with per-user spending limits." Cursor Teams, Kilo orgs, OpenHands Cloud and Claude Code Teams/Enterprise + apps gateway all have them. Say **"pre-call *reservation* with zero overshoot"** instead.
- ❌ "Only agent that stops at the limit and offers a local model." StaleGuard does exactly this.
- ❌ "First with a tamper-evident / hash-chained audit log." Gidorah has `audit verify`. Claim **canary-verified egress proof** instead.
- ❌ "Confidential mode via a local-only Bifrost key" as a novelty. StaleGuard and Gidorah both do it.
- ❌ "First with checkpoints/undo." Cline (shadow git), Claude Code (`/rewind`), Gemini CLI and Aider have them. Claim only **"undo that also reverts shell side effects"**.
- ❌ "First sandboxed agent." Codex and Claude Code have OS-level sandboxes. We are a policy layer; don't over-claim isolation.
- ❌ "Novel token techniques": repo map (Aider), compaction/condensers (all), caching stats (Claude Code shows cache-hit %), output truncation (Kilo, Claude Code). Our novelty is **measured ablation + code-mode "tokens avoided" counter**, not the techniques.
- ❌ "No agent does taint tracking." Microsoft has an experimental `FIDES_IFC` flag in Copilot CLI. Say "no mainstream coding CLI ships taint-aware approvals **by default**".
- ❌ "Our baseline has no budget." mini-swe-agent has `cost_limit`.
- ❌ Quoting Anthropic's "84% fewer prompts" or "93% approvals" as independent facts. They are Anthropic-internal numbers.

---

## 6. Open checks (do before the README)
- Cline checkpoints: do they capture files changed by terminal commands? (Affects the G8 wording.)
- Claude Code `--max-budget-usd`: is it still print-mode only in the current release?
- Goose `GOOSE_MODE` default in the current release.
- Whether StaleGuard or Gidorah add taint or undo before 15 Nov: re-check their repos on 14 Nov.
