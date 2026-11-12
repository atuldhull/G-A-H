# 07 · Confidential mode (R3)

Goal: a confidential repo is processed only by a local model, whatever the prompt, config typo or approved command tries. Every item here is **P0** unless tagged.

## 1. Detection (`confidential.mode_for`)

```python
def mode_for(paths):                       # cwd, --repo, and later every path argument of every tool call
    for p in map(realpath_normcase, paths):
        root = repo_root(p)
        ids = {first_commit(root), realpath(root), remote_url(root)} - {None}
        if registry.matches_any(ids) or journal.ever_confidential(ids): return confidential(ids)
        if any((d / ".crocodile" / "confidential").exists() for d in upward(p, stop=fs_root)):
            return confidential(ids)       # registers every id part: sticky
    if scan_down(root, marker=".crocodile/confidential", cap=50_000) is CAPPED:
        raise Refuse("cannot prove no nested confidential subtree: use --confidential")
    return "public"
```

- **Upward** from the realpath of the cwd, `--repo` and any path argument; **downward** bounded scan at session start (skip `.git`, `node_modules`, `.venv`). A nested confidential subtree in a public session becomes a DENY zone for `read`, `search` results and edits.
- **Sticky:** once any id part (first commit, realpath, remote URL) is confidential, it stays confidential. Leaving the registry needs `crocodile init --public <repo>` typed at an interactive console. `crocodile` cannot be run through `run_cmd`.
- Re-checked every turn: a removed marker, branch switch or subfolder run stays confidential and shows a red alert.

## 2. Two-key enforcement (ADR-006)

| Key | Where enforced | What it guarantees |
|---|---|---|
| Client key | `secrets.py` loads **only** `vk_local` in confidential mode; the public VK and Tavily key are never read from Credential Manager; `web_docs` is not registered | Even a bug in routing has no cloud credential to use |
| Gateway key | Bifrost `vk-*-local` has `provider_configs = [ollama]` only (deny-by-default for everything else); P1: VK-scoped `local-only` routing rule with `fallbacks: []` | Even a stolen local VK cannot reach a cloud provider |

## 3. Local model allowlist (review 07 C3)

`check_local_model(model_id, ollama_host)` runs in the client before every confidential call **and** in `doctor`:
- The model id must be `ollama/<tag>` with `<tag>` exactly in `confidential.local_model_allowlist`.
- Reject any tag containing `:cloud`, `-cloud`, `/`, or `@`. Ollama cloud models are proxied to ollama.com by the **local** daemon after `ollama signin`, so a loopback address proves nothing.
- `OLLAMA_HOST` (env and config) must resolve to a loopback address; anything else → refuse.
- `doctor` also calls Ollama `/api/show` and refuses if the response names a remote host/model, checks the tag has a local blob in `/api/tags`, and checks `OLLAMA_NO_CLOUD=1` is set (warn if not).
- `OLLAMA_CONTEXT_LENGTH=32768` must be set (Ollama's default is 4096, and its OpenAI route ignores per-request `num_ctx`). Prompts are fitted to 0.7 × the context; if they cannot fit, the call is refused instead of being silently truncated from the front.
- Local path quirks: send `system` as one string, no `cache_control`, no mid-conversation system messages (Bifrost #6245, #8145).

## 4. Egress choke point and log

`egress.py` is the only network code. A `sys.addaudithook` socket guard allows `connect` only to `127.0.0.1:8080` (Bifrost), `127.0.0.1:11434` (doctor probe) and `api.tavily.com:443` (public mode only). Proxy env vars are ignored.

Asserts on every confidential request, before send: `vk_alias == "local"`; model passes `check_local_model`; `fallbacks == []`; no `x-bf-cache-key`; destination `127.0.0.1:8080`. After the response: `provider_actual == "ollama"`, else abort the session and flag the audit.

Every request (sent or blocked) writes an `egress` row: destination, VK alias, mode, requested and actual model/provider, fallbacks, payload sha256 and size, canary hit count, verdict. P1: hash-chain the rows.

## 5. Canary audit

- `crocodile init --confidential` writes `CANARY-<128-bit hex>` into `.crocodile/canary` and, opt-in, one source-file comment. Tokens are stored in `canaries`.
- Egress scans every **public-mode** and Tavily payload for all known canaries at send time; a hit → BLOCK.
- `crocodile audit [--all]` passes only if: every confidential row has `vk_alias=local`, an allowlisted `ollama/` model, `fallbacks=[]` and `provider_actual=ollama`; Bifrost `/api/logs` shows provider `ollama` for those request ids; there are zero Tavily rows in confidential sessions; there are zero canary hits in sent public payloads. Blocked attempts are listed.
- **Claim wording:** "zero canary hits in the agent's egress". Canaries do not detect paraphrase, child-process exfiltration or direct VK use.

## 6. Tavily off

Confidential mode: the Tavily key is not loaded, `web_docs` is not registered, egress blocks `api.tavily.com`, and a model asking for web search gets a DENY result. P1 option: route Tavily through a Bifrost Relay with grants only on public VKs, a third independent block.

## 7. Data at rest (P1)

Spills and blobs live in non-roaming `%LOCALAPPDATA%`. P1: DPAPI-encrypt blobs of confidential sessions, add a retention setting, and turn off Bifrost content logging for the local VK. Doctor checks that `/api/logs` needs auth **[verify D0]**.

## 8. Tests

`px1_use_gpt` (prompt asks for GPT → only `ollama/*` rows) · `px3_marker_deleted` · `px3_repo_flag` (run from another cwd) · `px3_nested` · `px4_tavily` (0 Tavily rows) · `px8_unprefixed` (blocked) · `px_ollama_cloud_tag` (blocked, doctor FAIL) · `px_remote_ollama_host` (refused) · `test_stepdown_fits_window` · `audit_canary`.
