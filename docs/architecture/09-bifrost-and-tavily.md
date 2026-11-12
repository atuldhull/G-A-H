# 09 · Bifrost and Tavily

## 1. Bifrost: how we run it (P0)

- **Pin v2.5.1 or later** (v2.5.0 fixed #8712: message-level `cache_control` was dropped). The npm wrapper takes the gateway version as a flag:
  ```powershell
  npx -y @maximhq/bifrost --transport-version v2.5.1 -app-dir D:\bifrost -host 127.0.0.1 -port 8080
  ```
  Not `@maximhq/bifrost@<ver>`. Windows x64 is supported (`bifrost-http.exe`, cached under `%LOCALAPPDATA%\bifrost\<ver>\bin`); the launcher verifies the binary checksum.
- `config.json` lives in the repo at `bifrost/config.json` (env-var references only, no secrets) and is copied to `D:\bifrost\` by `scripts\prep.ps1`. Example: [04 §7](04-data-model.md).
- Bound to `127.0.0.1`, admin auth on. Admin credentials live in the admin's shell only, never in Crocodile's process or config.
- Go dynamic plugins do not load on Windows, so we use no Bifrost plugin. No semantic cache, no Code Mode.

## 2. Endpoints we call

| Endpoint | Used by | Notes |
|---|---|---|
| `POST /v1/chat/completions` | `egress.post_bifrost` | Non-streaming. Body: provider-prefixed `model`, explicit `fallbacks`, `max_tokens`, `cache_control` blocks (Anthropic), `prompt_cache_key` (OpenAI) |
| `POST /anthropic/v1/messages/count_tokens` | `egress.count_tokens` | Anthropic request shape; free on Anthropic (own RPM limits); an estimate. Alternative: `POST /v1/responses/input_tokens`. Ollama: unsupported → `chars/2.5` |
| `GET /api/logs` | `audit`, `budget reconcile`, failover error class | Filter by request id/VK; fields provider, model, status, usage **[verify D0]** |
| `GET /v1/models` | `doctor` | Lists what the VK can see |
| `POST/PUT /api/governance/virtual-keys` | `crocodile admin` (P1) | Admin auth; P0 creates VKs in the Bifrost UI |

## 3. Headers

| Direction | Header | Purpose |
|---|---|---|
| request | `x-bf-vk` | Virtual key (identity, budget, allowed providers); `enforce_auth_on_inference: true` makes it mandatory |
| request | `x-bf-session-id` | One per Crocodile session (log grouping) |
| request | never `x-bf-cache-key` | Semantic cache stays off |
| response | `x-bifrost-routing-info-{provider,model,is-fallback,primary-provider,primary-model,requested-provider,requested-model,server-side-fallback-model}` | Who answered; drives the takeover banner |
| response | `x-bifrost-fallback-index`, `x-bifrost-resolved-model` | Same, plus index into our chain |
| response body | `extra_fields.routing_info` | Same data, kept by default (`extra_fields_placement: body`) |

## 4. Virtual keys

| VK | Providers (`provider_configs`, explicit) | Budget | Used when |
|---|---|---|---|
| `<user>-public` | anthropic (+ openai if keyed) | daily, = `limits.yaml` | public mode |
| `<user>-local` | ollama only | none ($0) | confidential mode, local rung |
| `bench` | anthropic haiku only | $15/day | `crocodile bench` (keeps the bench out of user ledgers) |

`provider_configs: []` means deny-all; `"is_active": true` on every VK (bug #9810).

## 5. Fallbacks and routing facts

- Explicit `fallbacks` fire on **any** primary error, any status code, except a cancel or `AllowFallbacks=false` (set only by a few provider auth paths). Governance 402/429 do not block fallbacks. So the banner must classify the error.
- Unprefixed model ids get **inferred** cross-provider fallbacks; egress forbids them.
- No failover after the first streamed token; we do not stream.
- `max_retries: 0` per provider; the client owns retries (each with its own reservation).
- Bifrost's budget pre-check compares current usage with the limit without estimating the incoming request and books usage after the response, so parallel calls can overshoot. That is why our reservation exists; the VK budget is the second wall.

## 6. Verified vs unverified (as of 12 Nov)

| Fact | Status | Source |
|---|---|---|
| `--transport-version` pin, Windows binary, checksum | VERIFIED | npm wrapper `bin.js:194-199`; 09 §1.0, §1.6 |
| `enforce_auth_on_inference` replaces `enforce_governance_header` | VERIFIED (schema) | `config.schema.json:201-208` |
| Empty `provider_configs` = deny-all | VERIFIED (source) | 09 §1.2 |
| Fallbacks on any error, incl. 4xx | SOURCE-READ | `core/bifrost.go:5861-5897` |
| Routing headers on non-stream responses | SOURCE-READ | `lib/responseheaders.go:315+` |
| `cache_control` passthrough + cached tokens in usage (≥ v2.5.0) | VERIFIED (source + changelog) | 09 §1.0; BR §2.6 |
| `count_tokens` via `/anthropic/v1/messages/count_tokens` | SOURCE-READ | `integrations/anthropic.go:708-735` |
| 402 `policy_budget_exceeded` | SOURCE-READ | `plugins/governance/main.go:936-991` |
| Routing rules (CEL, `headers[...]`, VK scope) in OSS | VERIFIED (docs + source) | 09 §1.1 |
| `fallbacks: []` + local VK → only Ollama attempted | **UNVERIFIED** | D0 check |
| Request `fallbacks` cannot override a VK-scoped rule with empty fallbacks | **UNVERIFIED** | D0 check (P1) |
| VK-budget 402 on primary also refused on fallbacks | **UNVERIFIED** | D0 check |
| Ollama tool calls via Bifrost with `OLLAMA_CONTEXT_LENGTH=32768` | **UNVERIFIED** | D0 check |
| Key selection by model (failover demo with a bogus key) | **UNVERIFIED** | D0 check |
| `/api/logs` fields and auth | **UNVERIFIED** | D0 check |
| Haiku thinking tokens reported in `completion_tokens` | **UNVERIFIED** | D0 check |

## 7. Tavily (`tools/web_docs.py`, P0, gated)

- Raw REST through egress (no SDK): `POST https://api.tavily.com/search`, `Authorization: Bearer tvly-…` from Credential Manager.
- Lean params: `search_depth: "basic"` (1 credit), `max_results: 3`, `include_answer: false`, `include_raw_content: false`, `auto_parameters: false` (it may upgrade to advanced), `include_usage: true`, `include_domains` when the model names a library's docs site with `include_domains_mode: "restrict"`.
- Gate: public mode only; amber approval the first time per session (it is a NET sink); ≤ 3 calls per task; query checked by provenance (steered query → DENY); results are untrusted and pass through the output gate (snippets only, ≤ 1,500 tokens total).
- Typical trigger: `ImportError`/`AttributeError` on a third-party API. Tokens and credits are shown in the receipt.
- Confidential mode: key not loaded, tool not registered, socket guard blocks the host.
- Free tier: 1,000 credits/month. P1: front Tavily with a Bifrost Relay (`/relay/<name>/search`) so it shares VK budgets and logs **[UNVERIFIED live]**.
