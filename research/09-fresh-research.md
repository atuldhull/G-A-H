# 09 · Fresh research pass (2026-11-12)

Scope: what is NEW since `06-oss-budget-routing-peers.md` (10 Nov) and the `[verify D0]` items in DESIGN §10.1/§11. Method: Bifrost and mini-swe-agent **source** read at the commits below (shallow clones in the session scratchpad), plus primary docs. **VERIFIED** = read in source or the vendor's own docs (link given). **SOURCE-READ** = read in code but not run live. **UNVERIFIED** = still needs a live test.

Commits: `maximhq/bifrost@ff2e69f` (11 Nov 2026, HEAD); our earlier pin `@3544722` (10 Nov). `SWE-agent/mini-swe-agent@04d809c` (`__version__ = "2.4.6"`).

---

## TL;DR: what changes the design or plan

1. **The Bifrost pin method is wrong in DESIGN §10.1.** The npm wrapper takes the gateway version as a flag. Use `npx -y @maximhq/bifrost --transport-version v2.5.1 -app-dir D:\bifrost -host 127.0.0.1 -port 8080`, not `@maximhq/bifrost@<ver>`. Windows x64 is supported (`bifrost-http.exe`), and since v2.4.0 the launcher verifies the binary checksum.
2. **Pin v2.5.1 or later.** v2.5.0 (6 Nov) fixed #8712: message-level `cache_control` on chat messages was dropped, so Anthropic caching never triggered. Our per-message breakpoints need ≥ v2.5.0. Our 10 Nov source commit already has the fix.
3. **`enforce_governance_header` is deprecated.** Use `client_config.enforce_auth_on_inference: true`.
4. **VK `provider_configs: []` now means deny-all.** Access is deny-by-default unless `allow_all_providers: true`. This suits the local-only VK, but every cloud VK must list its providers explicitly. Also set `"is_active": true` on every VK in config.json to avoid open bug #9810.
5. **Explicit `fallbacks` fire on any primary error, 4xx included**, except a cancel or a short-circuit with `AllowFallbacks=false`. Governance refusals (402/429) do not set `AllowFallbacks=false`. So a 400 from a bad request also "fails over". The failover banner must say why: classify the primary error, don't assume an outage.
6. **`count_tokens` is reachable through Bifrost.** Use `POST /anthropic/v1/messages/count_tokens` (Anthropic shape) or `POST /v1/responses/input_tokens`. It is free on Anthropic (separate RPM limits). Ollama returns "unsupported", so use the `chars/2.5` fallback there.
7. **Bifrost Relays (OSS, v2.4.0) can carry Tavily** through `/relay/<name>/search` with VK `relay_grants`, VK budgets and Relay Logs. That gives a third, gateway-side Tavily block for confidential mode (the local VK has no relay grant) and puts Tavily spend in the same budget. This is optional and replaces nothing.
8. **Haiku 5.5 pricing is tiered**: $0.10 in / $0.50 out up to 100K prompt tokens, and **$0.50 / $2.50 above 100K**. Cache read $0.01, write $0.125 (5 min) / $0.20 (1 h). `prices.yaml` and `budget.reserve` must pick the tier from the counted prompt, failing closed to the high tier. Haiku 5.5 runs **adaptive thinking ON by default (effort `medium`)**. Thinking tokens bill as output, so the output reserve = `max_tokens`. The bench must give both agents the same thinking/effort settings.
9. **Bench task set: Aider Polyglot Python = 34 Exercism exercises.** They are "implement from spec" tasks, not bug fixes, so reproduce-first and localisation barely matter there. Add **QuixBugs (40 one-line Python bugs, MIT, pytest, no Docker)** as a bug-fix set. SWE-bench-style sets need Docker, so they are out for a 1-day Windows setup.
10. **mini-swe-agent cannot run natively on Windows in a fair way.** `LocalEnvironment` runs `subprocess.Popen(shell=True)` (cmd.exe) with bash-oriented prompts. Run it in **WSL2** against Bifrost on the host. Compute its cost with **our** price table from usage/Bifrost logs, not LiteLLM's.
11. **Peers:** none implements our differentiators. thrift-agent is now MIT, with 17 Node tasks, a naive baseline and "71% fewer tokens"; it has no reservation, undo, taint or egress ledger.

---

## 1. Bifrost (maximhq/bifrost)

### 1.0 Version and changelog since October — VERIFIED
- Latest gateway: **transports v2.5.1** (10 Nov 2026). Fixes: empty `messages` → 400 instead of a crash; streaming panics recovered; no migrations. The npm wrapper defaults to latest, so pin it with `--transport-version`. [releases](https://github.com/maximhq/bifrost/releases), `transports/changelog.md`.
- Relevant OSS changelog items (`docs/changelogs/v2.3.0…v2.5.0.mdx`):

  | Ver (date) | Item | Impact on us |
  |---|---|---|
  | v2.3.0 (13 Oct) | `routing_info.requested_provider/model` + headers `x-bifrost-routing-info-requested-*`; `ttft_timeout_ms` on routing targets (streaming only, 504 `ttft_timeout`); passthrough routes POST-only allowlist; `GET /v1/models/{model}` | Parse the requested-* headers in the banner |
  | v2.3.1 (19 Oct) | `cache_control` on assistant `tool_calls` reaches Anthropic `tool_use`; VK `metadata`; calendar budgets fixed for multipliers | ok |
  | v2.4.0 (29 Oct) | **Relays** (Tavily etc. via `/relay/{name}/{path}`, VK `relay_grants`, budgets, Relay Logs); fallback-chain timeline in log UI; **npx checksum verification** | Optional Tavily-through-Bifrost |
  | v2.5.0 (6 Nov) | **#8712 fixed: message-level `cache_control` was dropped**; routing-rule fallbacks on 4xx (#3261); config.json routing-rule `id` optional | Must pin ≥ v2.5.0 |
  | v2.5.1 (10 Nov) | Crash/panic fixes | Pin this |

### 1.1 (a) Routing rules (CEL) in OSS — VERIFIED (docs + source), live test pending
- Config path `governance.routing_rules[]` (schema `$defs/routing_rule`, `transports/config.schema.json:1578, 6650`). Fields: `name`, `enabled`, `cel_expression`, `targets[{provider, model, key_id?, weight}]` (weights sum to 1), `fallbacks["prov/model"]`, `scope` (`global|customer|team|virtual_key`), `scope_id`, `priority` (unique per scope, 409 on clash), `chain_rule`. `id` is optional since v2.5.0. Rules load at startup; a change needs a restart. [docs/providers/routing-rules.mdx](https://github.com/maximhq/bifrost/blob/main/docs/providers/routing-rules.mdx)
- CEL variables include **`headers["x-…"]`** (case-insensitive), `request_type`, `budget_used`, `tokens_used`, team/VK names. Only load balancing level 1 is marked Enterprise; rules themselves are not gated.
- API: `GET/POST /api/routing/rules`, `GET/PUT /api/routing/rules/{rule_id}` (alias `/api/governance/routing-rules`) (`handlers/routing.go:119-122`).
- Example for the two-key story (scope = local VK id): `{"name":"local-only","enabled":true,"cel_expression":"true","targets":[{"provider":"ollama","weight":1}],"fallbacks":[],"scope":"virtual_key","scope_id":"<local-vk-id>","priority":1}`. **UNVERIFIED live:** that a rule with empty `fallbacks` cannot be overridden by the request's `fallbacks`.

### 1.2 (b) Governance API: VKs and budgets programmatically — VERIFIED (source)
- `POST /api/governance/virtual-keys` (also GET list, `GET/PUT/DELETE /api/governance/virtual-keys/{vk_id}`, `POST …/{vk_id}/rotate`, budget overrides `PUT/DELETE …/{vk_id}/budgets/{budget_id}/override`; `GET /api/governance/budgets`) (`handlers/governance.go:1820-1843`). In OSS; admin auth middleware applies.
- Body (`CreateVirtualKeyRequest`, `governance.go:371`):
  ```json
  {"name":"bob","description":"crocodile user bob",
   "provider_configs":[{"provider":"anthropic","allowed_models":["claude-haiku-5-5","claude-sonnet-5-5"],"weight":1}],
   "budgets":[{"max_limit":2.0,"reset_duration":"1d"}],
   "rate_limit":{"request_max_limit":120,"request_reset_duration":"1m"},
   "is_active":true,"metadata":{"owner":"bob"}}
  ```
  - `budgets[]` entries: `max_limit` in USD, `reset_duration` ∈ `30s,5m,1h,1d,1w,1M,1Q`; each must have a unique `reset_duration`. Budgets can also sit per provider (`provider_configs[].budgets`) and per model (`model_budgets`).
  - **`provider_configs` empty = deny-by-default.** `allow_all_providers: true` opens everything. Tavily relay access needs `relay_grants`.
- Auth on inference: `x-bf-vk: <vk>` (Bearer also accepted). Config key `client_config.enforce_auth_on_inference` (default true on new deployments); `enforce_governance_header` is **deprecated** (`config.schema.json:201-208`).
- Budget refusal: HTTP **402**, error type `policy_budget_exceeded` (`plugins/governance/main.go:936-991`). Unchanged since BR §2.1.

### 1.3 (c) Anthropic `count_tokens` via Bifrost — VERIFIED (source), live test pending
- Integration route `POST /anthropic/v1/messages/count_tokens` (Anthropic request/response shape), `integrations/anthropic.go:708-735, 1399`. Native route `POST /v1/responses/input_tokens` with model `anthropic/claude-haiku-5-5` (`handlers/inference.go:837, 899`).
- Anthropic: **free**; separate RPM limits (Start 5,000 / Build 10,000 / Scale 20,000); "the token count is an **estimate**"; doesn't use caching logic. [platform.claude.com token-counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)
- Ollama: `CountTokens` returns `UnsupportedOperationError` (`core/providers/ollama/ollama.go:528`), so use the heuristic.
- **UNVERIFIED:** whether governance counts a `count_tokens` request against VK rate limits. Cost is $0 anyway.

### 1.4 (d) Ollama provider + tool calling — VERIFIED (docs/source), live test pending
- Config ([docs/providers/supported-providers/ollama.mdx](https://github.com/maximhq/bifrost/blob/main/docs/providers/supported-providers/ollama.mdx)):
  ```json
  "providers":{"ollama":{"keys":[{"name":"ollama-local","value":"","models":["*"],"weight":1.0,
     "ollama_key_config":{"url":"http://localhost:11434"}}]}}
  ```
- Bifrost calls Ollama's **OpenAI-compatible `/v1/chat/completions`** (`ollama.go:213`); tools are supported. `prompt_cache_key` is not supported.
- **Context size cannot be set per request** on Ollama's OpenAI route: "The OpenAI API does not have a way of setting the context size." Set `OLLAMA_CONTEXT_LENGTH=32768` as a user env var (default is 4096!), or `ollama create` a Modelfile variant with `num_ctx 32768`. [Ollama OpenAI compat](https://docs.ollama.com/api/openai-compatibility), [Ollama FAQ](https://docs.ollama.com/faq). **This changes §10.1**: "num_ctx 32768" must be applied this way.
- Open issues that touch our path:
  - #6245: a multi-block `system` → several system messages → Ollama rejects (seen on the `/anthropic` route). Fix: send `system` to Ollama as **one string** (one block) and put no `cache_control` on the local path.
  - #8145: mid-conversation system messages are forwarded in place, and Qwen templates reject them. Don't use mid-conversation system messages on the local path.
  - #6508: Ollama timeout fires before the configured timeout. Set the provider `network_config` timeout generously and test.

### 1.5 (e) Fallback trigger conditions and routing headers — SOURCE-READ (HEAD)
- `shouldTryFallbacks` (`core/bifrost.go:5861-5897`):
  - no fallbacks on success, on `RequestCancelled`, when `AllowFallbacks == false`, or when the list is empty;
  - **inferred** (catalog) fallbacks are skipped when `ClassifyFailure` says caller fault;
  - otherwise **any error triggers explicit fallbacks, any status code included**.
- `AllowFallbacks=false` is set only by specific provider auth paths (Anthropic workload identity, Copilot, token cache, a stream util). Governance refusals leave it nil (`plugins/governance/main.go:936`).
- `ClassifyFailure` (`core/failureclass.go:224`) gives the class: transient (network, 5xx), quota (402 / `insufficient_quota`), rate-limit, caller-fault, timeout, cancelled. Use the same classes in our banner.
- Headers are set unconditionally on non-stream responses (`lib/responseheaders.go:315+`):
  - `x-bifrost-provider`, `-original-model`, `-resolved-model`, `-fallback-index`, `-request-type`
  - `x-bifrost-routing-info-{provider,model,key,alias-model-id,alias-model-name,alias-model-family,is-fallback,primary-provider,primary-model,server-side-fallback-model,requested-provider,requested-model}`
- Body `extra_fields` is kept by default (`client_config.extra_fields_placement: "body"`). On streams, headers carry the routing identity known before the first chunk.

### 1.6 (f) Windows — VERIFIED (source)
- `npx/bifrost/bin.js:194-199`: win32 x64 → `windows/amd64/bifrost-http.exe`, cached under `%LOCALAPPDATA%\bifrost\<ver>\bin`. Flags: `-host`, `-port`, `-app-dir`, `-log-level`, `-log-style` (`transports/bifrost-http/main.go:108-113`). Pin with `--transport-version v2.5.1`.
- Go dynamic plugins do not work on Windows (`docs/plugins/writing-go-plugin.mdx:16`), so the Gidorah-style DLP plugin is out. STDIO MCP fails on Windows (#5671); we don't use it.

### 1.7 (g) Open issues that could break the demo — VERIFIED (issue pages, 12 Nov)
| Issue | Effect | Mitigation |
|---|---|---|
| [#9810](https://github.com/maximhq/bifrost/issues/9810) config.json sync writes `is_active` NULL on VK update (v2.5.1) | Dashboard shows the key disabled; **enforcement still active** | Put `"is_active": true` on every VK; don't screenshot the VK list without checking |
| [#9219](https://github.com/maximhq/bifrost/issues/9219) cancelled streams logged/billed as 0 tokens | Bifrost under-books cancels | Supports our "charge input on cancel"; cite it as an attack class |
| [#6245](https://github.com/maximhq/bifrost/issues/6245) multi-block system → Ollama 400 | Local path breaks | Single-string system on Ollama |
| [#9296](https://github.com/maximhq/bifrost/issues?q=9296) Anthropic stream drops tool_use input when args arrive only at function-call-done | Missing tool args on streams | Use non-streaming calls for tool turns (not verified whether this hits chat completions or only Responses) |
| [#9888](https://github.com/maximhq/bifrost/issues/9888) empty content when a non-streamed Messages reply hits `max_tokens` during reasoning | Empty turn with Haiku 5.5 thinking | Treat empty + `max_tokens` stop as a retryable "raise max_tokens once" event, and journal it |
| #8145 mid-conversation system messages (Qwen templates) | Local path | Avoid on Ollama |
| #9889 calendar budget timezone; #9873 no Retry-After on governance 429 | Minor | Our own backoff |

---

## 2. Peer repos — VERIFIED (GitHub pages / API, 12 Nov)
- **StaleGuard** (`Shrinu14/staleguard-agent`): no commits after 5 Nov (`36dfab2`). Unchanged. [commits](https://github.com/Shrinu14/staleguard-agent/commits/main)
- **Gidorah** (`piyushdotcomm/gidorah`): no commits after 4 Nov (`2aa505f`). Two Windows path-canonicalisation fixes; no vkLocal, `&` or budget fix. [commits](https://github.com/piyushdotcomm/gidorah/commits/main)
- **Pinch**: last commit 8 Nov ("wait out per-minute rate limits; pace both agents alike"). No new features visible.
- **New or updated PS-01 entries:**

  | Repo | Licence | Budget | Undo | Taint / egress | Bench |
  |---|---|---|---|---|---|
  | [nemo-MV33/thrift-agent](https://github.com/nemo-MV33/thrift-agent) (TS) | **MIT now** | Per-user VK only (402 → stop + `--resume`) | none | none / Bifrost `/api/logs` | 17 Node tasks, naive baseline (gpt-oss-120b), `--runs 3`, 17/17, "71% fewer tokens", $0.00132/task |
  | [Ani07-05/slendertoken](https://github.com/Ani07-05/slendertoken) (Go) | none | VK daily budget | none | `--private` per-run flag; "best effort" network block | `bench/` with no numbers |
  | [Dhruv727876/Privacy-First-Token-Optimized-Coding-Agent](https://github.com/Dhruv727876/Privacy-First-Token-Optimized-Coding-Agent) (TS, created 11 Nov) | MIT (claimed) | daily/monthly/per-task config; no reservation | none | opt-in confidential paths | none |
  | [Shristi1611/tokenshield](https://github.com/Shristi1611/tokenshield) | none | none | — | Quarantined-LLM "typed facts" (closest to our taint idea, but not a coding agent) | 10 READMEs, bootstrap CIs |

- **None** implements atomic reservation, taint-labelled approvals, an egress ledger with canaries, shadow-git undo, or a CPST vs mini-swe-agent bench. thrift-agent and tokenshield report CIs or repeated runs, so our "1 seed" jab no longer applies to every peer. Keep peer critique as attack classes.

---

## 3. mini-swe-agent — VERIFIED (source @04d809c, PyPI)
- **Version 2.4.6** (PyPI latest; `requires_python >=3.10`). [PyPI](https://pypi.org/project/mini-swe-agent/)
- **Windows:** `LocalEnvironment._run` uses `subprocess.Popen(command, shell=True, …)` (`environments/local.py:70-90`), which means **cmd.exe** on Windows, while `mini.yaml` prompts assume bash. The model's bash commands (`cat <<EOF`, `sed -i`, `&&` chains) break or behave differently. The docs only mention `setx` for env vars. **Recommendation: run the baseline in WSL2 (Ubuntu, Python 3.12)** against Bifrost on the Windows host (`http://<host-ip>:8080`; Bifrost must then bind to the WSL vEthernet IP or `0.0.0.0` with a firewall rule, so keep auth on). Measure tokens and $; wall time is not compared across OSes. **UNVERIFIED live.**
- **Point it at Bifrost** (LiteLLM `model_kwargs` go straight to `litellm.completion`; `docs/models/local_models.md`):
  ```yaml
  model:
    model_name: "openai/anthropic/claude-haiku-5-5"
    model_kwargs:
      api_base: "http://<host>:8080/v1"
      api_key: "<bench VK>"            # or extra_headers: {"x-bf-vk": "<bench VK>"}
      drop_params: true
      extra_body: {"fallbacks": []}
    cost_tracking: "ignore_errors"     # or MSWEA_COST_TRACKING=ignore_errors
    set_cache_control: "default_end"   # same caching posture as ours; ablate if needed
  ```
  Run: `mini -c mini.yaml -c bench_bifrost.yaml -t "<task>" -y --exit-immediately -l 0`, or the batch runner with a custom task file.
- **Cost:** `litellm.cost_calculator.completion_cost(response, model=model_name)`; anything ≤ 0 raises unless `ignore_errors` is set (`litellm_model.py:108-126`). A custom price list loads from `LITELLM_MODEL_REGISTRY_PATH` / `litellm_model_registry` via `litellm.utils.register_model` (`:32, 61-62`). **Recommendation:** don't trust LiteLLM's price for a proxied id. Recompute both agents' $ from `usage` (or Bifrost `/api/logs` per VK) with our `prices.yaml`, so both use one pricing function. Note LiteLLM `cost_limit` defaults to $3 in `mini.yaml`.

---

## 4. Bench task set (Windows, ≈ 1 day)
- **Aider Polyglot Python — VERIFIED.** [`Aider-AI/polyglot-benchmark/python/exercises/practice`](https://github.com/Aider-AI/polyglot-benchmark) has **34** exercises (affine-cipher … zipper). The repo is about 1.1 MB with **no licence file**; the content comes from Exercism's python track (MIT), so fetch from `exercism/python` if attribution matters.
  - Layout: `<name>.py` stub, `<name>_test.py`, `.docs/instructions*.md`, `.meta/example.py` (the solution, which must be **removed** from the agent's copy).
  - Aider's harness (`benchmark/benchmark.py:981-1050`) re-copies the original test files before grading and runs plain `pytest` in the dir, with a 180 s timeout and 2 tries (`--tries 2`). Docker is recommended only because model code is executed.
  - On Windows: `git clone --depth 1`, copy each exercise to a temp dir without `.meta/`, and grade with `py -m pytest -q` after restoring `*_test.py`. Run on native Windows for our agent and in WSL for mini; the same tests either way.
- **Caveat that matters for our pitch:** these are implement-from-spec tasks. Tests fail at the start because the stub is empty, so "reproduce-first", localisation and the thrash ladder are lightly exercised. DESIGN's "each ships failing tests" is true, but none is a bug fix.
- **Add QuixBugs Python — VERIFIED.** [jkoppel/QuixBugs](https://github.com/jkoppel/QuixBugs): MIT, 40 programs each with a one-line bug, graded by `pytest python_testcases/test_<name>.py`. Use `--timeout=5` for bitcount (pytest-timeout); the slow knapsack case runs only with `--runslow`. No Docker, runs on Windows. Risk: it's well known (contamination), so report it as a secondary set.
- **SWE-bench Lite / Verified subsets:** they need the Docker harness with Linux images per repo. That is doable on Docker Desktop + WSL2 but costs many GB and hours, so **not feasible in ~1 day**. **UNVERIFIED** (not re-measured).
- **Recommendation:** use Polyglot-Python, 34 tasks (all, not 30), as the headline set, plus 20 QuixBugs as a "bug-fix" secondary set to show reproduce-first and localise. Same model, 2 seeds; restore tests before grading; delete `.meta/`.

---

## 5. Models, prices, caching — VERIFIED ([pricing](https://platform.claude.com/docs/en/about-claude/pricing), [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting), claude-api skill cached 2026-11-03)

| Model id | Input | 5m write | 1h write | Cache read | Output |
|---|---|---|---|---|---|
| `claude-haiku-5-5` (prompt ≤ 100K) | $0.10 | $0.125 | $0.20 | $0.01 (0.1×) | $0.50 |
| `claude-haiku-5-5` (prompt > 100K) | $0.50 | $0.625 | $1.00 | $0.05 | $2.50 |
| `claude-sonnet-5-5` | $2.00 | $2.50 | $4.00 | $0.10 (0.05×) | $10.00 |
| `claude-opus-5-5` | $4.00 | $5.00 | $8.00 | $0.20 (0.05×) | $20.00 |

Caching and other rules:
- Up to 4 breakpoints; minimum cacheable prefix **512 tokens** on Haiku/Sonnet/Opus 5.5; TTL 5 min (default) or `ttl:"1h"`; writes cost 1.25× (5 min) or 2× (1 h). A read refreshes the TTL. The TTL counts from the start of the request.
- `inference_geo:"us"` costs ×1.1.
- Haiku 5.5 runs adaptive thinking **on by default**, effort `medium`. Non-default `temperature`/`top_p`/`top_k` → 400, so "seeds" are repeated runs, not sampling seeds. Disabling thinking is allowed only at effort ≤ `high`.
- Claude 4.7+ tokenizer models (the 5.5 family included) produce about **30% more tokens** than older models. Anthropic says do not use tiktoken; o200k under-counts more than the old 15–20% figure.
- Bifrost sends `anthropic-version: 2023-06-01` upstream (`core/providers/anthropic/anthropic.go:122`). **UNVERIFIED:** whether the sampling-param 400 also applies on that version. Send none, so it doesn't matter.

**OpenAI cheap tier** — VERIFIED ([pricing](https://developers.openai.com/api/docs/pricing), Standard, per 1M in / cached / out):

| Model | Input | Cached | Output |
|---|---|---|---|
| `gpt-5-nano` | $0.05 | $0.005 | $0.40 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.50 |
| `gpt-5.4-nano` | $0.20 | $0.02 | $1.25 |
| `gpt-5-mini` | $0.25 | $0.025 | $2.00 |
| `gpt-4o-mini` | $0.15 | $0.075 | $0.60 |

OpenAI's automatic caching threshold (≥ 1,024 tokens) is not restated on the page; it is carried from EV #10.

**tiktoken vs count_tokens:**
- Claude routes: count via Bifrost `count_tokens` (free, an estimate), cached per prefix hash, × p95 calibration.
- OpenAI routes: tiktoken o200k.
- Ollama: `ceil(chars/2.5)` × calibration.

---

## 6. Tavily — VERIFIED
- `tavily-python` **0.8.5** (6 Oct 2026); the 0.8.x line started 24 Aug. We use raw REST, so the SDK version doesn't matter. [PyPI](https://pypi.org/project/tavily-python/)
- Credits: **1,000 free/month**. `basic`, `fast` and `ultra-fast` cost 1 credit; `advanced` costs 2. Extract: 1 credit per 5 URLs (basic). Map: 1 per 10 pages. Crawl = map + extract. [credits](https://docs.tavily.com/documentation/api-credits)
- `POST /search` with `Authorization: Bearer tvly-…`. Defaults: `max_results` **10** (set 3), `auto_parameters` false (it may upgrade to advanced), `include_usage` false (set true; the response has `usage.credits`), `chunks_per_source` 3.
- **New:** `include_domains_mode` (`restrict` default | `prefer`); send `restrict` explicitly. [search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- Bifrost Relays (v2.4.0, OSS) can front Tavily: `/relay/<name>/search` with `x-bf-vk`, per-call pricing, VK budgets and Relay Logs. [docs/relays/overview.mdx](https://github.com/maximhq/bifrost/blob/main/docs/relays/overview.mdx). **UNVERIFIED live.**

---

## 7. Still UNVERIFIED (live D0/D1 checks)
1. Explicit `fallbacks:[]` + local VK + routing rule → the Bifrost log shows only Ollama.
2. Is a VK-budget 402 on the primary retried on fallbacks, and is it refused per attempt?
3. Ollama tool call through Bifrost with `qwen3-coder:30b` / `gpt-oss:20b` and `OLLAMA_CONTEXT_LENGTH=32768`.
4. `count_tokens` via `/anthropic/v1/messages/count_tokens` with a VK: works, and is it governed?
5. Overshoot with 8 parallel calls at a $0.001 VK budget (race demo column 3).
6. mini-swe-agent 2.4.6 in WSL2 → Bifrost on the host: one Polyglot task end-to-end, with usage captured.
7. Haiku 5.5 through Bifrost's OpenAI route: are adaptive thinking tokens reported in `completion_tokens`, and is `reasoning_effort` mapped to `output_config.effort`?
8. Relay-fronted Tavily (if adopted).
