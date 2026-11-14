# Person 4 local mini environment — Gemini execution blocked

Prepared on 2026-11-14 from `person-4` runtime revision
`b62814c61e30a7ba6162fcb65eac6897cdcfe1ac`. No model call, benchmark task,
credential provisioning, gateway start/configuration change, or database access
was performed. This is environment and offline routing evidence, not live parity.

## Installed environment

| Item | Observed value |
|---|---|
| Distribution | Ubuntu, WSL2; kernel `6.6.87.2-microsoft-standard-WSL2` |
| Dedicated interpreter | `/home/gunda/venvs/crocodile-mini/bin/python` |
| Python | `3.12.3`; separate virtual environment verified |
| mini-swe-agent | Exactly `2.4.6`, installed from public PyPI |
| LiteLLM | `1.109.1` |
| pip | `26.3`; `pip check` exited 0 |
| Installed mini config | `/home/gunda/venvs/crocodile-mini/lib/python3.12/site-packages/minisweagent/config/mini.yaml` |
| mini.yaml Git blob | `8b72f71f8092ae805ec43221dbeaeefc2340cd3e`; matches the adapter pin |

Ubuntu's ordinary venv creation failed because `ensurepip` was unavailable.
The dedicated venv was completed with `python3 -m venv --without-pip`, then pip's
[supported get-pip.py bootstrap](https://pip.pypa.io/en/stable/installation/#get-pip-py)
and `pip install mini-swe-agent==2.4.6`, using the explicit public PyPI index.
No sudo, OS-package installation, or permissions change was used. The bootstrap
script was downloaded over HTTPS from `https://bootstrap.pypa.io/get-pip.py`;
its observed SHA-256 was
`356e0d0de21cdc348c3394084d90939b85e4246c4d14c76aee6ca4f46646ea98`.
That hash records the downloaded bytes, not an independently authenticated release.
Transitive dependencies were resolved at installation time, not fully locked.

Read-only version check from PowerShell:

```powershell
wsl.exe --distribution Ubuntu --exec /home/gunda/venvs/crocodile-mini/bin/python -I -c "import importlib.metadata as m; print(m.version('mini-swe-agent'))"
```

## Key-free settings and Gemini routing

[configs/mini-settings.ubuntu.json](configs/mini-settings.ubuntu.json) selects the
actual interpreter and documented loopback `/v1` endpoint. It contains only the
credential **variable name**, never its value. The non-login WSL environment
used for inspection did not have `CROCODILE_BENCH_VK` provisioned. Do not add a key
to this file, a command line, a committed `.env`, or evidence output.

**This settings file does not change the model.** `bench.mini.Settings` selects
the interpreter/endpoint; the executable model is frozen separately in
`configs/mini-2.4.6.json` and `bench.plan.EVALUATION_POLICY`. Both still pin Haiku.
The runner refuses a different policy. No working Gemini benchmark config is
claimed or enabled while the gateway checks below remain unresolved.

The installed mini source passes `self.config.model_name` to
`litellm.completion`. An offline call to the installed LiteLLM
`get_llm_provider` helper established this exact request-format mapping:

| Layer | Proposed identifier / value |
|---|---|
| mini model argument | `openai/gemini/gemini-3.5-flash-lite` |
| LiteLLM transport provider | `openai` (OpenAI-compatible Bifrost endpoint) |
| Model sent toward Bifrost | `gemini/gemini-3.5-flash-lite` |
| Documented API base | `http://127.0.0.1:8080/v1` |

The helper ran with socket connection/DNS functions blocked and the local model
cost map selected: zero network attempts occurred. This verifies prefix handling,
**not** that the Gemini model exists upstream, is enabled, or can be billed.
No `completion` call was made.

Sanitized inspection of the repository's `bifrost/config.json` found a Gemini
provider with a wildcard model list, not an explicit declaration of this model.
Its active `bench` VK allows only `anthropic/claude-haiku-5-5`; it does not allow
Gemini. This is a checked-in template, not a verified live configuration. No local
listeners were found on documented ports 8080 or 18080 at inspection time.
The endpoint is therefore configured but **live connectivity, binary v2.5.1,
Gemini model availability, and bench VK binding are unverified**. Gateway-owner
review/configuration is required; no Part 2 file was changed here.

## Policy mismatches and the next minimal probe

Crocodile's current defaults remain Haiku/public VK, model fallback/escalation,
and temperature 0.0 or 0.7. Mini requests no sampling parameters, uses
`set_cache_control: default_end`, and requests no Bifrost fallbacks; its upstream
retry helper can still retry model queries. Crocodile marks prompt-cache blocks
differently. The current Haiku adaptive/medium assumption is not a verified Gemini
thinking policy and must not be transferred automatically. Thirty steps and a
600-second policy are configured, but native Crocodile uses cooperative checks
and mini's watchdog does not contain escaped descendants. Live parity is pending.

Before a separately authorized single-request session-header probe:

1. Have the gateway owner confirm the running version, exact served Gemini ID,
   endpoint, bench VK's non-secret identity/model allowance/shared cap, and
   WSL-to-gateway reachability. Supply an authorized logging snapshot location.
2. Agree Gemini thinking/cache/retry/sampling/fallback policy with the agent and
   gateway owners. Then update the Person 4 model profile and frozen plan policy
   together, test them, and generate new manifests/full-plan identities. Existing
   Haiku plans must not be relabeled as Gemini runs.
3. Provision the bench credential through the WSL environment used by `wsl --exec`;
   a variable set only in a login-shell profile is not necessarily available there.
   Keep all values out of output/configuration. Do not substitute the public VK.
4. Use a dedicated non-benchmark probe with one unique `mini-probe-UUID` header,
   the verified mini/LiteLLM configuration, minimal supported output, and a
   reviewed retry bound. Persist only sanitized identity/version/time evidence.
   Do not launch the agent loop or exercise code merely to test one header.
5. Match the exact session and bench VK against request ID, actual model/status,
   and explicit input/output/cache categories in authorized read-only Bifrost
   evidence. Verify close/flush/completeness; never infer missing usage as zero.
   Keep schema/version, pricing, cache TTL and retry limitations explicit.
6. Only after successful reviewed forwarding evidence set
   `session_header_verified: true` and its evidence reference. Until then it stays
   false; a time window is not exact attribution. Real three-task smoke inputs,
   oracle/dependency review and benchmark authorization remain separate steps.
