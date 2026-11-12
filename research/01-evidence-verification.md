# 01: Evidence verification (2026-11-10)

This checks every cited claim in RESEARCH.md §3 and §8b against its primary source: the arXiv abstract plus HTML body/tables, official docs, or Bifrost source code (commit `3544722`, cloned 2026-11-10).

## Verdict table

| # | Claim as written in RESEARCH.md | Verdict | Correct wording to use |
|---|---|---|---|
| 1 | Models predict their own cost poorly (r ≤ 0.39, 2604.22750) | **CONFIRMED** (small nuance) | "8 frontier models predicting their own token use on SWE-bench Verified reach Pearson r of at most 0.39, and all of them systematically underestimate." |
| 2 | SWE-Router: partial-trajectory routing beats task-description routing; Route-AUC 0.780 vs 0.627 | **CONFIRMED, but narrow** | "On 100 held-out SWE-bench Verified tasks (DeepSeek-V3.2 → Gemini-3-Pro), routing after 2 cheap-model turns scored Route-AUC 0.780 vs 0.627 for query-only routing." No $ savings figure is given. |
| 3 | EET: −32% cost, ≤0.2% loss, presented as "trace-based escalation" | **OVERSTATED / MISATTRIBUTED** | EET is **experience-driven early termination**, not escalation: "−19% to −55% cost (mean −32%) across 3 agents on SWE-bench Verified, with a resolve-rate change of at most −0.2 pp." With mini-swe-agent the cut is only about −19%. |
| 4 | Observation masking roughly halves cost with an equal or better pass rate; hybrid saves 7–11% more | **OVERSTATED** | "Masking halved cost in all 5 configs. Solve rate was equal or better for Qwen3-Coder-480B (53.4→54.8%) and Gemini 2.5 Flash (32.8→35.6%), but lower for Qwen3-32B (−2 pp) and Gemini Flash-thinking (−4 pp, significant). The hybrid is 7% cheaper than masking and 11% cheaper than summarization, measured on 50 tasks with one model." |
| 5 | Anthropic: 150K → 2K tokens (98.7%) | **CONFIRMED as stated, but it is illustrative** | "Anthropic's illustrative Drive→Salesforce example: 150K → 2K tokens." It was not a benchmark: there is no model, n or method. |
| 6 | LSP-only raised tokens 6–118%; agents pick LSP 0–6% | **OVERSTATED** | "In a small preliminary study, LSP-only beat grep-only on tokens-to-success for Haiku (−26%) but lost for Opus (+6%) and Sonnet (+118%) on localization. Under free choice, models used LSP 0–6% for localization and 45–57% for reference tasks." |
| 7a | CaMeL 77% of tasks "with provable security" (vs 84%) | **CONFIRMED (scoped)** | Security is "provable" only with respect to explicit policies on tool calls and data flows. It does not stop text-to-text attacks, and users must write the policies. |
| 7b | FIDES "blocked every AgentDojo injection" | **OVERSTATED** | "With policy checks, FIDES let 1 of the AgentDojo injections succeed (0 after excluding 2 tasks the authors don't count as attacks; gpt-4o, Tool Knowledge attack). It does not stop text-to-text attacks." |
| 8 | 2506.08837 design patterns; plan-then-execute | **CONFIRMED** | Plan-then-execute fixes the list of actions before untrusted data is read. Injected data **can still change the arguments** of planned actions. |
| 9a | Bifrost budgets deducted post-call, so overshoot is possible | **CONFIRMED (docs + code)** | The pre-check is `current_usage >= max_limit` and does not count the pending request's cost. Usage is added after the call. |
| 9b | Budget exceeded → HTTP 402 `budget_exceeded` | **CONFIRMED (status), type string slightly off** | HTTP **402**, error type `policy_budget_exceeded` (the internal decision is `budget_exceeded`). Rate, token and request limits return **429** `policy_rate_limited`. |
| 9c | `fallbacks` body field; `extra_fields.routing_info.is_fallback/.provider/.model`; OpenAI-compatible route uses `x-bifrost-*` headers [unverified names] | **CONFIRMED; header names now verified** | Headers include `x-bifrost-routing-info-provider`, `-model`, `-is-fallback`, `-primary-provider` and `x-bifrost-fallback-index`, so the **native route is not required**. `attempt_trail` is internal (context/logs), not in the response body. A new field, `routing_info.server_side_fallback_model`, is set when Anthropic swaps models inside one call. |
| 9d | `max_retries` default 0 | **CONFIRMED** | Default 0. Backoff starts at 500 ms, max 5000 ms. |
| 9e | Semantic cache: `x-bf-cache-key` needed; `dimension:1` = exact match | **CONFIRMED + new fact** | A key is mandatory unless `default_cache_key` is set. **Identity scoping is on by default**: two virtual keys never share entries. `disable_identity_scoping: true` turns this off. TTL defaults to 5m, threshold to 0.8. |
| 9f | Bifrost doesn't cover mid-stream errors | **CONFIRMED** | "Errors after that boundary [first output] remain stream errors." A missed TTFT counts as a timeout and does trigger fallback. |
| 10 | Anthropic cache reads 0.1×, 0.05× on Opus/Sonnet 5.5; OpenAI caches above 1024 tokens; use `prompt_cache_key` | **CONFIRMED; minor additions** | The minimum cacheable length is **512** tokens on Opus 5.5, Sonnet 5.5 and Haiku 5.5 (4,096 on Haiku 4.5 and Opus 4.5/4.6). On GPT-5.6+, `prompt_cache_key` is "not needed" (optional, for accounting), and cache reads cost 0.1×. |
| 11a | LongCodeZip up to 5.6× | **CONFIRMED ("up to")** | Tested on completion, summarization and QA, **not agentic loops**. |
| 11b | ReasoningBank: fewer steps on repeat tasks | **CONFIRMED (modest)** | SWE-bench Verified, bash-only: Gemini-2.5-flash 34.2→38.8% resolved, 30.3→27.5 steps; Gemini-2.5-pro 54.0→57.4%, 21.1→19.8 steps. Not limited to "repeat tasks". |
| 11c | Chain of Draft 7.6% of tokens | **OVERSTATED (best case)** | 7.6% is the best case (Sports, Claude 3.5 Sonnet). GSM8K costs about 4 pp of accuracy, zero-shot and small models degrade badly, and nothing was tested on code. |
| 11d | TALE | **CONFIRMED (not cited with a number)** | About 67% fewer output tokens with less than 3 pp accuracy loss on math. On code generation and summarization BLEU dropped (summarization 0.20→0.07). |
| 12 | mini-swe-agent baseline | **CONFIRMED (score varies)** | The README says ">74%" or ">70%" depending on version, with no model named. The official bash-only board uses it. A custom base_url config works (see notes). |
| 13 | UK AISI CodeIPI | **CONFIRMED exists** | `inspect_evals/ipi_coding_agent`: 45 samples (35 injected, 10 benign), Docker, `network_mode: none`. The built-in solver is a fixed `react()`, but Inspect's `--solver` / `bridge()` can swap in a custom agent. |

---

## Per-claim notes

### 1. arXiv 2604.22750: "How Do AI Agents Spend Your Money?"
- **Source:** https://arxiv.org/abs/2604.22750 (HTML: /html/2604.22750). Authors: Bai, …, Brynjolfsson, Pentland, Pei.
- **Setup:** SWE-bench Verified, 500 instances, OpenHands trajectories. 8 models: Sonnet 3.7/4/4.5, GPT-5, GPT-5.2, Qwen3-Coder-480B, Kimi-K2, Gemini-3-Pro. 3 predictions per model.
- **Results:** Pearson r is "weak-to-moderate, up to 0.39". The 0.39 is Sonnet 4.5's **output-token** prediction, and the best input-token r is Kimi-K2 at 0.38. All models underestimate, worst on input tokens. Runs of the same task can differ "up to 30×" in tokens, but the average max/min ratio is about 2×. Cache reads dominate both volume and cost.
- **Caveats:** One scaffold. In Appendix D, prediction without the example was weaker.
- **Paraphrase:** Accurate. Applies directly to coding agents. This supports a heuristic or history-based quote instead of asking the model.

### 2. arXiv 2607.00053: SWE-Router
- **Source:** https://arxiv.org/abs/2607.00053 (ICML 2026 DL4Code workshop).
- **Setup:** Pair deepseek-v3.2 (weak) → gemini-3-pro-preview (strong). K=2 exploration turns vs K=0 (query only). Route-AUC on the held-out **100-instance** SB-V slice is 0.780 vs 0.627 (+15.3 pp).
- **Caveats:** One run and no confidence intervals. It is unstable across splits: SWE-Smith test gives 0.567 vs 0.555, and SWE-Smith val gives 0.720 vs 0.663. AUROC is actually lower for K=2. **No dollar savings are reported**: Route-AUC is a normalized metric. Data-collection cost for all 500 tasks was $22.6 on DeepSeek vs $391.3 on Gemini-3-Pro, which is useful as a cost-ratio anchor.
- **Paraphrase:** The numbers are accurate, but RESEARCH.md §8b implies they come with −32% cost. They don't (see #3).

### 3. arXiv 2601.05777: EET (ACL 2026 Findings)
- **Source:** https://arxiv.org/abs/2601.05777
- **Setup:** Agentless, mini-swe-agent and Trae Agent × GPT-5-mini and DeepSeek-V3.2, run on all 500 SWE-bench Verified tasks. The experience bank is built from 207 SWE-bench Lite tasks.
- **Mechanism:** TF-IDF retrieval of a prior successful experience (τ=0.15). The agent self-scores its confidence: above 90 it stops early, below 40 (during patch selection) it gives up.
- **Results:** Cost −19.4% to −55.1%, mean −31.8%. Resolve rate ranges from −0.2 pp (Trae/DeepSeek) to +7.8 pp. mini-swe-agent: −19.4% (GPT-5-mini) and −19.3% (DeepSeek). API calls −21%, input tokens −30%, output tokens −25%.
- **Caveats:** Cold start (needs an experience bank) and SWE-bench only.
- **Paraphrase:** **Wrong framing.** It is early termination, not trace-based escalation. Cite it separately: "stop when confident or hopeless".

### 4. arXiv 2508.21433: The Complexity Trap (JetBrains)
- **Source:** https://arxiv.org/abs/2508.21433, Table (HTML v3).
- **Setup:** SWE-agent, SWE-bench Verified n=500 per model, masking window M=10, 250-turn limit.

| Model | Raw | Masking | LLM-summary |
|---|---|---|---|
| Qwen3-32B | 17.0% / $1.12 | 15.0% / $0.55 | 16.0% / $0.50 |
| Qwen3-32B think | 23.0 / 0.51 | 24.6 / 0.46 (−10%) | 24.8 / 0.51 |
| **Qwen3-Coder-480B** | 53.4 / 1.29 | **54.8 / 0.61 (−52.7%)** | 53.8 / 0.64 |
| **Gemini 2.5 Flash** | 32.8 / 0.41 | **35.6 / 0.18 (−56.1%)** | 36.0 / 0.24 |
| Gemini 2.5 Flash think | 40.4 / 0.56 | 36.4† / 0.24 | 31.4† / 0.25 |

- **Hybrid:** N=43, W=10. It costs −7% vs masking and −11% vs summary, measured on **SWE-bench Verified-50 with Qwen3-Coder-480B only**.
- **OpenHands:** A 50-instance check, where the masking window had to be **retuned**.
- **Caveats:** The authors note limits themselves: SWE-only, fixed triggers, and masking can hide a still-relevant observation.
- **Paraphrase:** "About −50% cost" holds for 4 of 5 configs. "Equal or better pass rate" holds only for 3 of 5. Applies directly to coding agents (same task family).

### 5. Anthropic, "Code execution with MCP" (2025-11-04)
- **Source:** https://www.anthropic.com/engineering/code-execution-with-mcp
- **The claim:** "reduces the token usage from 150,000 tokens to 2,000 tokens—a time and cost saving of 98.7%". It describes the Google Drive → Salesforce transcript example: all tool definitions and intermediate results passed through context, vs code that imports only the tool files it needs.
- **What it is not:** No model, n or method is given, so it is an **illustrative** figure. The post itself warns about sandboxing, resource limits and operational overhead.
- **Paraphrase:** "on one example" is fair. Never call it a measurement.

### 6. arXiv 2608.13568: "Does a Language Server Save Tokens for Coding Agents?"
- **Source:** https://arxiv.org/abs/2608.13568. Single author, described as "preliminary".
- **Setup:** Arms A grep-only, B LSP-only, C free choice, D semantic-first. Localization used 6 SWE-bench-Lite `requests` issues × 3 rollouts. Models: Opus 4.8, Sonnet 4.6, Haiku 4.5.
- **Results:** Tokens-to-success for B vs A: Opus +6% (971 vs 920), Sonnet +118% (1,319 vs 606), **Haiku −26%**. Under free choice, localization used semantic tools 0/4/6% of the time, and reference tasks 45–57%. On multi-file renames, grep solved all of them, while location-only LSP failed about ¾.
- **Recommendation:** An adaptive router: use LSP when an identifier is lexically ambiguous, and keep grep as the default for edits.
- **Caveats:** Tiny n, and the paper says effect sizes "will move". Token counts are total context tokens, not billed cost under caching.
- **Paraphrase:** "LSP-only raised tokens 6–118%" leaves out the Haiku saving. Our plan, "LSP only alongside grep", is consistent with the paper.

### 7. CaMeL (2503.18813) and FIDES (2505.23643)
- **CaMeL:** https://arxiv.org/abs/2503.18813. The abstract says "solving 77% of tasks with provable security (compared to 84% with an undefended system) in AgentDojo". "Provable" refers to a formal PI-SEC game: no tool call outside the set allowed by the policy. **Limits stated by the authors:** it cannot defend against text-to-text attacks; users must write and maintain policies; it is not fully autonomous (it needs user approval for ambiguous cases); there are side channels (an exception leaks one bit); the Travel suite has poor utility; and "prompt injection attacks are not fully solved".
- **FIDES:** https://arxiv.org/abs/2505.23643 (Microsoft). In Table 1 with gpt-4o (Tool Knowledge attack), **1 successful injection with policy checks (0 after excluding two tasks the authors don't count as attacks)**, vs 163 for the Basic planner and 24 for FIDES without policies. The text says "stops all prompt injection attacks in AgentDojo". Utility: with policies, FIDES beats Basic for all models (up to +16.7% on o1), but drops by up to 24.5% for o3 and o4-mini. Limits: policies apply only to tool calls, so text-to-text attacks are not stopped; the quarantined LLM can still be manipulated; integrity labels are coarse and hand-set.
- **Applies to us?** Yes, conceptually: taint labels on tool calls. Our pitch should say "FIDES-style label propagation", not "blocks all injections".

### 8. arXiv 2506.08837: Design Patterns for Securing LLM Agents
- **Source:** https://arxiv.org/abs/2506.08837 (Beurer-Kellner, Tramèr et al.).
- **The 6 patterns:** Action-Selector, Plan-Then-Execute, LLM Map-Reduce, Dual LLM, Code-Then-Execute, Context-Minimization.
- **Plan-Then-Execute:** The agent formulates "a fixed list of actions" before it processes untrusted data. It does not stop injected data from changing **arguments** (for example an email body), and it does not stop user-prompt injection.
- **§4.10 coding-assistant case study:** Per-action user confirmation alone is "impractical" and can be bypassed by stealthy changes, such as an import the user later installs. Action sandboxing to trusted sources is safer. The paper rates a Dual LLM with strict formatting of docs/code safest, at a utility cost.
- **Implication:** Our taint-labelled approvals (a red prompt naming the source) answer the paper's critique of plain y/n prompts directly. Cite §4.10.

### 9. Bifrost (docs + source)
- **Budgets:** https://docs.getbifrost.ai/features/governance/budget-and-limits. The docs example lets a request through with $4 left on a $5 budget, after which usage shows "$6/$5". Source `plugins/governance/store.go`: `if budget.CurrentUsage+baseline >= effectiveMaxLimit → DecisionBudgetExceeded`. The pending request's cost is never estimated, so **overshoot is possible, and concurrent requests can all pass**. `plugins/governance/main.go:991`: `refusal(result, 402, schemas.ErrorTypePolicyBudgetExceeded)`, where the type string is `"policy_budget_exceeded"` (`core/schemas/errors.go`). Rate, token and request limits return 429 `policy_rate_limited`. Budgets are checked at every level (provider config, VK, team, customer), and `reset_duration` takes values such as `1d`. A provider-config budget that is exhausted makes Bifrost **exclude that provider from routing** instead of refusing.
- **Fallbacks:** https://docs.getbifrost.ai/features/fallbacks. The body takes `"fallbacks": ["provider/model", ...]`. `extra_fields.routing_info` contains `provider`, `model`, `key`, `is_fallback`, `primary_provider`, `primary_model`, `requested_provider/model` and `server_side_fallback_model` (`core/schemas/bifrost.go` RoutingInfo). Drop-in routes expose the same data as headers: `x-bifrost-routing-info-provider|model|is-fallback|primary-provider`, `x-bifrost-fallback-index`, `x-bifrost-provider`, `x-bifrost-resolved-model` (`transports/bifrost-http/lib/responseheaders.go`). `attempt_trail` (`failure_class`, `status_code`, `retry_after_ms`) is a context value used for logs, not a response field. Fallback fires on any error except caller cancellation, `AllowFallbacks=false` from a plugin, or a catalog-added fallback after a `caller_fault`. Provider and TTFT timeouts trigger fallback. An expired request deadline does not.
- **Streaming:** Once output has started, an error stays a stream error, with no retry and no fallback. The client must handle it, so our "continue on fallback" stretch goal is valid.
- **Semantic cache:** https://docs.getbifrost.ai/features/semantic-caching. "A cache key is mandatory" (`x-bf-cache-key`, or `default_cache_key` in config). Identity scoping is on by default: "two different virtual keys can never share a cache entry". `disable_identity_scoping: true` removes this. `dimension: 1` with no provider gives direct (hash) mode. TTL defaults to 5m (`x-bf-cache-ttl` overrides it), threshold to 0.8. Supported stores: Redis/Valkey, Weaviate, Qdrant, Pinecone. Streams are cached and replayed. Hits appear in `extra_fields.cache_debug` and `x-bifrost-cache-*` headers.

### 10. Prompt caching pricing
- **Anthropic:** https://platform.claude.com/docs/en/build-with-claude/prompt-caching. 5-minute writes cost 1.25×, 1-hour writes 2×, and reads 0.1×. Exceptions: **Opus 5.5 and Sonnet 5.5 read at 0.05×**; Fable/Mythos 5.1–5.2 read at 0.025×.
  - Prices: Opus 5.5 is $4 in / $0.20 read / $20 out. Sonnet 5.5 is $2 / $0.10 / $10. Haiku 5.5 is $0.10 / $0.01 / $0.50 up to 100K tokens, and $0.50 / $0.05 / $2.50 above that.
  - Minimum cacheable length: 512 tokens for Opus 5.5, Sonnet 5.5, Haiku 5.5 and Opus 5; 1,024 for Opus 4.8, Sonnet 5 and Sonnet 4.5/4.6; 4,096 for Haiku 4.5 and Opus 4.5/4.6. A shorter prompt is silently not cached.
  - Up to 4 breakpoints, with a 20-position lookback.
  - Invalidation follows the order tools → system → messages. Changing tool definitions invalidates everything. Changing tool_choice or images invalidates messages. Changing thinking or effort settings invalidates messages.
- **OpenAI:** https://developers.openai.com/api/docs/guides/prompt-caching. The minimum is 1,024 tokens on GPT-5.6+. `prompt_cache_key` "influence[s] routing" on older models and is "not needed" on GPT-5.6+, where it is only useful for per-user accounting. The guidance is about 15 requests per minute per prefix+key. Retention: `in_memory` or `24h`, or `prompt_cache_options.ttl` (30m or 12h) on 5.6+. Cache reads cost 0.1×, or 0.05× on GPT-6.1 Sol/Terra.

### 11. Compression and memory papers
- **LongCodeZip** (https://arxiv.org/abs/2510.00446, ASE 2025): "up to a 5.6x compression ratio without degrading task performance". Tested on code completion, summarization and QA, not agent loops. It uses conditional perplexity from a code LM, so a local model is needed.
- **ReasoningBank** (https://arxiv.org/abs/2509.25140, ICLR 2026): numbers in the table above. Gains are +3.4 to +4.6 pp and about 1.3–2.8 fewer steps on SWE-bench Verified (bash-only, Gemini 2.5).
- **Chain of Draft** (https://arxiv.org/abs/2502.18600): 7.6% = Sports, Claude 3.5 Sonnet (14.3 vs 189.4 tokens). On GSM8K, CoD keeps about 21% of the tokens at −4 pp accuracy. Zero-shot Claude gains only 3.6 pp over direct answering. Small models drop sharply (Zoom-SLM 2.3B: 77.7→50.9%). No coding tasks.
- **TALE** (https://arxiv.org/abs/2412.18547): TALE-EP gives about 67% fewer output tokens and a 59% lower bill, with less than 3 pp accuracy loss on GSM8K and MathBench (GPT-4o, 4o-mini, Yi-lightning, o3-mini). In the code appendix, BLEU falls (code summarization 0.20→0.07, code generation 0.267→0.24). **Do not use it for code output.**

### 12. mini-swe-agent as the baseline
- **Source:** https://github.com/SWE-agent/mini-swe-agent (now v2). The README claims ">74%" on SWE-bench Verified with no model named; older versions claimed 65% or 70%. Third-party bash-only boards list Claude 4.5 Opus at 74.4 and Gemini 3 Pro at 74.2 (unverified on swebench.com). It is the official harness for swebench.com bash-only.
- **Routing it through Bifrost** (https://mini-swe-agent.com/latest/models/local_models/):
  ```yaml
  model:
    model_name: "anthropic/claude-sonnet-5-5"   # any name; must match registry if prefixed
    model_kwargs:
      custom_llm_provider: "openai"
      api_base: "http://localhost:8080/v1"      # Bifrost OpenAI-compatible
      drop_params: true
      extra_headers: {"x-bf-vk": "<baseline-vk>"}   # litellm passthrough; verify
    cost_tracking: "ignore_errors"              # or: export MSWEA_COST_TRACKING=ignore_errors
  ```
  - For prices, use a `model_registry.json` entry (`input_cost_per_token`, `output_cost_per_token`, `litellm_provider: "openai"`). Set it with `litellm_model_registry:` or `mini-extra config set LITELLM_MODEL_REGISTRY_PATH ...`.
  - Run with `mini-extra swebench --subset verified --split test --filter ... --output out/`, or use `mini` for single tasks.
  - **Better:** take costs from Bifrost `/api/logs` for both agents, so the accounting is identical.

### 13. UK AISI CodeIPI
- **Source:** https://ukgovernmentbeis.github.io/inspect_evals/evals/ipi_coding_agent/index.html, and source in `src/inspect_evals/ipi_coding_agent/ipi_coding_agent.py`.
- **What it tests:** Indirect prompt injection during a real bug fix. Vectors: issue text, code comments, README and config files. Payloads: exfiltration (canary env vars and `/root/.secret_canary`), code execution (`CANARY_EXEC_<id>`), and persistence (SHA-256 of workspace files).
- **Size and scoring:** 45 samples (35 injected, 10 benign). Metrics: `injection_resistance_rate`, `task_completion_rate`, `detection_rate` (LLM-graded) and `accuracy`.
- **Environment:** Docker, `network_mode: none`, 2 GB memory limit.
- **Running it:** `inspect eval inspect_evals/ipi_coding_agent --model openai/gpt-4o -T vectors=... -T severities=... -T defense_prompt=false`. Task parameters are only vectors, severities and defense_prompt. The solver is hard-coded as `react()` with bash and python tools and `max_messages=30`.
- **Custom agent:** Inspect's generic `--solver file.py@fn` overrides a task's solver, and `bridge()` wraps an external agent function by patching the OpenAI client (https://inspect.aisi.org.uk/agent-bridge.html, https://inspect.aisi.org.uk/task-configuration.html). So our agent can run against it, but its model calls would go through Inspect's model provider. Point that at Bifrost with `--model openai-api/...` and a base URL.
- **Effort:** Wiring this takes about half a day or more. Copying its vectors and canary scheme into our own `make redteam` fixtures, as already planned, is cheaper. A real CodeIPI score would be a strong credibility point if time allows.

## Not checked here
- CodeAct "up to 30% fewer actions"
- The "84% of turn tokens are tool outputs" figure
- 2601.06007 (Don't Break the Cache)
- Cloudflare Code Mode
- CODESKILL
- The "93% approval" statistic
- Cline shadow-git

These remain [unverified] in RESEARCH.md.
