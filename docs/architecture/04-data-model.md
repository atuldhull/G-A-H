# 04 · Data model

## 1. File locations

| Path | Contents | Writable by | Tier |
|---|---|---|---|
| `%APPDATA%\crocodile\config.yaml` | Non-secret settings, model chains, layer flags | user (integrity-watched) | P0 |
| `%APPDATA%\crocodile\policy.yaml` | Protected/red paths, redact list, output limits | user (integrity-watched, SHA pinned per session) | P0 |
| `%APPDATA%\crocodile\prices.yaml` | Price table incl. tiers | user (integrity-watched) | P0 |
| `%APPDATA%\crocodile\state.db` | SQLite WAL: ledger, journal, egress, registry, grants | agent (HMAC-protected) | P0 |
| `%PROGRAMDATA%\crocodile\limits.yaml` | Per-user daily limits | **Administrators only** (users read) | P0 |
| `%LOCALAPPDATA%\crocodile\{blobs,out,shadow,sbx}\` | Tool-output blobs, spills, shadow git, per-call child scratch | agent | P0 |
| Windows Credential Manager (`keyring`, service `crocodile`) | `vk_public`, `vk_local`, `tavily_key`, `hmac_key` | user | P0 |
| `<repo>\.crocodile\confidential`, `.crocodile\canary` | Marker and canary | user via `crocodile init` | P0 |

The repo is **never** a config source. There is no dotenv. Spills and blobs go to non-roaming `%LOCALAPPDATA%` so confidential output is not synced off the machine.

## 2. Labels (provenance-lite, P0)

| Source | Untrusted for provenance? |
|---|---|
| User task text, `--issue FILE --trust-issue` | no |
| System prompt, tool schemas, policy | no |
| File contents, search lines, **file and symbol names**, `list` output | **yes** (repo data, review 07 H2) |
| Command and test stdout/stderr, spills | yes |
| `web_docs` results; issue text by default | yes |

Session mode `confidential` labels every value read in that session. Files matching `read_redact` are redacted in every mode, and the output gate's secret scanner applies to every tool result (§5).

## 3. SQLite schema (`state.db`, WAL, `busy_timeout=5000`)

```sql
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);              -- 'hmac' = HMAC(key, digest of ledger window + registry + grants)
CREATE TABLE ledger (                                         -- money (P0)
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, session TEXT, task TEXT,
  window TEXT NOT NULL,                                       -- 'YYYY-MM-DD' UTC, same as VK reset_duration 1d
  status TEXT CHECK(status IN ('held','settled','cancelled','expired')),
  reserved_usd REAL NOT NULL, actual_usd REAL, overshoot_usd REAL DEFAULT 0,
  model_ceiling TEXT, model_actual TEXT, tier TEXT, rung TEXT, est_in INT, bound_in INT, max_out INT,
  in_uncached INT, in_cache_read INT, in_cache_write INT, out_tokens INT,
  request_id TEXT, owner_pid INT, owner_start REAL, heartbeat REAL, sent INT DEFAULT 0,
  created_at REAL, settled_at REAL);
CREATE INDEX ledger_pw ON ledger(principal, window, status);
CREATE TABLE calib (model TEXT, ratio REAL, ts REAL);         -- actual prompt_tokens / estimate
CREATE TABLE events (session TEXT, seq INT, ts REAL, type TEXT, payload TEXT,
  prev_hash TEXT, hash TEXT,                                  -- chain columns filled in P1
  PRIMARY KEY(session, seq));
CREATE TABLE egress (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, session TEXT, request_id TEXT,
  dest TEXT, vk_alias TEXT CHECK(vk_alias IN ('public','local','none')), mode TEXT,
  model_requested TEXT, fallbacks TEXT, model_actual TEXT, provider_actual TEXT,
  payload_sha256 TEXT, payload_bytes INT, canary_hits INT,
  verdict TEXT CHECK(verdict IN ('sent','blocked')), block_reason TEXT);
CREATE TABLE canaries (token TEXT PRIMARY KEY, repo_id TEXT, path TEXT, created_at REAL);
CREATE TABLE confidential_repos (                             -- sticky; matched on ANY column
  first_commit TEXT, realpath TEXT, remote TEXT, since REAL);
CREATE TABLE grants (session TEXT, kind TEXT CHECK(kind IN ('test_consent','argv')),
  argv_json TEXT, interpreter_sha TEXT, cfg_hashes TEXT, expires_at REAL);
CREATE TABLE oracle (session TEXT PRIMARY KEY, test_ids TEXT, file_shas TEXT, created_by TEXT,
  baseline_passed TEXT);                                      -- JSON id sets
```

The local ledger is the pre-call gate for one machine. The Bifrost VK budget is the independent server-side cap. Team scale = swap SQLite for Postgres `SELECT … FOR UPDATE` (P2).

## 4. Journal events

Envelope `{session, seq, ts, type, payload}`. Tool outputs are stored by content address in `blobs\<sha256>`, so replay is byte-exact.

| type | payload |
|---|---|
| `session_started` | task, repo_root, repo_id parts, mode, policy_sha, principal, rung, prefix seg hashes, exe pins (git, rg, ruff, python), ignored repo config |
| `task_state` | pinned state + its token size |
| `oracle_frozen` | test ids, file shas, created_by, baseline passed-id set |
| `test_consent` | argv, interpreter sha, config files + hashes, granted / refused |
| `model_request` / `model_response` / `model_error` | rid, reservation_id, chain, fallbacks, vk_alias, est_in, max_tokens / routing info, usage, cost / status, error class, retry_after |
| `tool_proposed` | call_id, name, args, decision (level, reasons, steered_by, token) |
| `approval` | call_id, approved, by (`console`/`consent`/`grant`/`bench`), typed_ok |
| `tool_started` | call_id, snapshot commit (written **before** spawn) |
| `tool_result` | call_id, ok, blob_sha, spill, tokens_shown, tokens_avoided |
| `verify_result` | stage, ok, failing ids, sig, ms |
| `thrash` / `strategy` | trigger, evidence / action |
| `mask_applied` | upto_msg, masked_tokens |
| `rung_changed` / `failover` | from, to, reason / primary, actual, error class, price delta |
| `budget_warning` / `budget_denied` | spent, held, limit, needed |
| `integrity_violation` | path or table, expected, found → session aborted |
| `paused` / `resumed` / `task_done` | reason / from_seq / outcome, usd, receipt |

## 5. Config and policy

```yaml
# %APPDATA%\crocodile\config.yaml   (no secrets: VKs and Tavily key live in Credential Manager)
principal_display: atul
bifrost: {base_url: "http://127.0.0.1:8080"}
tavily: {enabled: true, max_calls_per_task: 3}             # never loaded in confidential mode
budget: {warn_frac: 0.8, lease_heartbeat_s: 20, lease_stale_s: 60, calib_q: 0.95, calib_default: 1.35,
         max_out_cap: 4096, max_out_floor: 1024}
models:
  strong: {chain: ["anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5"], ctx_window: 200000}
  cheap:  {chain: ["anthropic/claude-haiku-5-5", "openai/gpt-5-mini"], ctx_window: 200000}  # drop openai if no key
  local:  {chain: ["ollama/qwen2.5-coder:7b"], ctx_window: 32768}
  start_rung: cheap
confidential:
  local_model_allowlist: ["qwen2.5-coder:7b", "qwen3-coder:30b"]   # exact tags; :cloud / -cloud always rejected
  ollama_host: "http://127.0.0.1:11434"
context: {mask_window: 10, mask_min_batch_tokens: 6000, fit_frac: 0.7}
verify:  {test_timeout_s: 120, full_suite_at_end: true}
thrash:  {same_sig: 2, same_edit: 2, max_switches: 2}
loop:    {step_cap: 30}
layers:  {cache: on, gate: on, readcache: on, matcher: on, mask: on, ladder: on, stop_green: on,
          thrash: on, escalate: on, compact: off, localize: off, repomap: off}   # ablation flags
```

```yaml
# %APPDATA%\crocodile\policy.yaml
protected: [".git/**", ".crocodile/**", ".env*", ".vscode/**", "*.code-workspace", ".idea/**", ".claude/**",
            ".cursor/**", "**/mcp.json"]                                   # hard deny write
red_paths: ["**/test_*.py", "**/*_test.py", "**/tests/**", "**/conftest.py", ".github/workflows/**",
            ".gitattributes", ".gitmodules", "pyproject.toml", "setup.py", "setup.cfg", "pytest.ini", "tox.ini",
            "noxfile.py", "Makefile", ".pre-commit-config.yaml", "sitecustomize.py", "usercustomize.py", "*.pth",
            "requirements*.txt", "Dockerfile", ".devcontainer/**"]
read_redact: [".env*", "**/*.pem", "**/*.key", "**/id_rsa*", "**/id_ed25519*", "**/*.ppk", "**/*.p12", "**/*.pfx",
              "**/*.jks", "**/*.kdbx", ".npmrc", ".pypirc", ".netrc", "_netrc", "**/credentials*.json",
              "**/*service-account*.json", "**/secrets.y*ml", "**/*.tfstate", ".docker/config.json"]
grantable: []            # inverted list: only the consented test argv is ever prompt-free (review 07 M1)
output: {max_lines: 256, max_bytes: 10240, head_frac: 0.2}
```

```yaml
# %PROGRAMDATA%\crocodile\limits.yaml   (admin-only write; `crocodile admin set-limit` from an elevated shell)
principals:
  "3f1c9a…": {display: atul, daily_usd: 5.00}
  "a77b02…": {display: bob,  daily_usd: 0.05}
```

`principal = sha256(public VK)[:16]`. Changing `USER`/`USERNAME` changes nothing. A missing or unparseable config/limits file → refuse to start ("run `crocodile init`"), never default to cloud.

## 6. Price table (`prices.yaml`, USD per 1M tokens, verified 12 Nov, research/09 §5)

```yaml
anthropic/claude-haiku-5-5:
  tiers:                                         # chosen by counted prompt tokens; unknown count → highest tier
    - {upto: 100000, in: 0.10, cache_write_5m: 0.125, cache_write_1h: 0.20, cache_read: 0.01, out: 0.50}
    - {upto: null,   in: 0.50, cache_write_5m: 0.625, cache_write_1h: 1.00, cache_read: 0.05, out: 2.50}
  max_out: 64000
anthropic/claude-sonnet-5-5: {tiers: [{upto: null, in: 2.00, cache_write_5m: 2.50, cache_write_1h: 4.00, cache_read: 0.10, out: 10.00}], max_out: 64000}
anthropic/claude-opus-5-5:   {tiers: [{upto: null, in: 4.00, cache_write_5m: 5.00, cache_write_1h: 8.00, cache_read: 0.20, out: 20.00}]}  # reference only
openai/gpt-5-mini:           {tiers: [{upto: null, in: 0.25, cache_read: 0.025, out: 2.00}]}   # cache_write = in
ollama/*:                    {tiers: [{upto: null, in: 0, cache_read: 0, out: 0}]}
```

Rules: a pydantic schema validates required keys per provider. A model with no price, or a `TBD`, is refused by `reserve` and fails `doctor`. Haiku 5.5 thinking tokens bill as output, so the output reserve is the full `max_tokens`.

## 7. Bifrost `config.json` (v2.5.1 schema; validate against `transports/config.schema.json` on day 0)

```json
{
  "client_config": {
    "enable_logging": true,
    "enforce_auth_on_inference": true,
    "allow_direct_keys": false
  },
  "providers": {
    "anthropic": {
      "keys": [
        {"name": "anth-primary", "value": "env.ANTHROPIC_API_KEY", "models": ["claude-sonnet-5-5", "claude-haiku-5-5"], "weight": 1.0}
      ],
      "network_config": {"max_retries": 0, "default_request_timeout_in_seconds": 120}
    },
    "openai": {
      "keys": [{"name": "oai-1", "value": "env.OPENAI_API_KEY", "models": ["gpt-5-mini"], "weight": 1.0}],
      "network_config": {"max_retries": 0}
    },
    "ollama": {
      "keys": [{"name": "ollama-local", "value": "", "models": ["qwen2.5-coder:7b"], "weight": 1.0,
                "ollama_key_config": {"url": "http://127.0.0.1:11434"}}],
      "network_config": {"max_retries": 0, "default_request_timeout_in_seconds": 300}
    }
  },
  "governance": {
    "virtual_keys": [
      {"id": "vk-atul-public", "name": "atul-public", "value": "env.BF_VK_ATUL_PUBLIC", "is_active": true,
       "provider_configs": [
         {"provider": "anthropic", "allowed_models": ["claude-sonnet-5-5", "claude-haiku-5-5"], "weight": 1},
         {"provider": "openai", "allowed_models": ["gpt-5-mini"], "weight": 1}],
       "budgets": [{"max_limit": 5.00, "reset_duration": "1d"}]},
      {"id": "vk-atul-local", "name": "atul-local", "value": "env.BF_VK_ATUL_LOCAL", "is_active": true,
       "provider_configs": [{"provider": "ollama", "allowed_models": ["qwen2.5-coder:7b"], "weight": 1}]},
      {"id": "vk-bob-public", "name": "bob-public", "value": "env.BF_VK_BOB_PUBLIC", "is_active": true,
       "provider_configs": [{"provider": "anthropic", "allowed_models": ["claude-haiku-5-5"], "weight": 1}],
       "budgets": [{"max_limit": 0.05, "reset_duration": "1d"}]},
      {"id": "vk-bench", "name": "bench", "value": "env.BF_VK_BENCH", "is_active": true,
       "provider_configs": [{"provider": "anthropic", "allowed_models": ["claude-haiku-5-5"], "weight": 1}],
       "budgets": [{"max_limit": 15.00, "reset_duration": "1d"}]}
    ],
    "routing_rules": [
      {"name": "local-only", "enabled": true, "cel_expression": "true",
       "targets": [{"provider": "ollama", "model": "qwen2.5-coder:7b", "weight": 1}], "fallbacks": [],
       "scope": "virtual_key", "scope_id": "vk-atul-local", "priority": 1}
    ]
  }
}
```

Notes:
- `enforce_auth_on_inference` replaces the deprecated `enforce_governance_header`. Every VK lists `provider_configs` explicitly: an empty list is deny-all, and nothing uses `allow_all_providers`. `"is_active": true` on every VK avoids open bug #9810.
- `max_retries: 0`: the client owns retries, and each retry has its own reservation (review 07 H7). Bifrost fallbacks still provide R1.
- No semantic cache plugin, no Code Mode, no `default_cache_key`. Admin auth on. Bifrost binds to `127.0.0.1` (`-host`).
- The `local-only` routing rule is the optional second half of the gateway check (P1); the VK `provider_configs` alone already deny cloud.
- **Failover demo without OpenAI:** add a second Anthropic key `anth-bogus` with a wrong value and `models: ["claude-sonnet-5-5"]`, and remove sonnet from `anth-primary`. A sonnet request then gets 401 and falls back to haiku **[verify D0: key selection by model]**.
