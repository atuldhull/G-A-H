# Gemini benchmark policy and blocked live readiness

Static/synthetic inspection on 2026-11-14 incorporated `origin/main`
`4feb2dbee4363801556c678570edb12f5a52b70e`,
the bench VK's Gemini allowlist change.
The user's approved Gemini policy supersedes the older Haiku model/port text in
architecture/10 for this experiment. No benchmark or paid request was executed.

## Person 4 configuration

| Setting | Current declaration |
|---|---|
| Planned starting/billed model | `gemini/gemini-3.5-flash-lite` |
| Mini OpenAI-compatible route | `openai/gemini/gemini-3.5-flash-lite` |
| Windows gateway / WSL mini API base | `http://127.0.0.1:18080` / `http://127.0.0.1:18080/v1` |
| Required logical VK | ID `vk-bench`, name `bench`, for both agents |
| Thinking/effort | Provider defaults; no explicit request override |
| Measured-model fallbacks | Empty |
| Measured escalation | Disabled in this supported single-model policy |
| Runs/caps | Unchanged: Crocodile 2, mini 2, twin 1; 30 steps; 600-second policy |
| Cache declaration | Prompt caching requested; semantic cache off; live behavior unverified |

`bench.plan.EVALUATION_POLICY` is the planner's configuration constant. It now
records the model, endpoint, non-secret VK identity and model-change policy in
new manifests and their full-plan identity. `configs/mini-2.4.6.json` sets the
matching mini model and provider-default thinking metadata; outbound kwargs have
no sampling/thinking override, and Bifrost fallbacks remain `[]`. Static inspection
of the installed mini template found only `drop_params` in its model kwargs, so
that merge adds no inherited sampling/thinking overrides either.
[configs/mini-settings.ubuntu.json](configs/mini-settings.ubuntu.json) selects the
installed `/home/gunda/venvs/crocodile-mini/bin/python` and the new endpoint.
Its only credential input is the environment-variable **name**
`CROCODILE_BENCH_VK`; header verification remains false with no evidence reference.

[configs/crocodile-gemini-bench.json](configs/crocodile-gemini-bench.json) contains
only the model-chain and endpoint fields the merged native user-settings reader
understands. It is a reviewable profile, not automatically loaded by the runner.
No user settings, credential store, gateway configuration or other owner's module
was edited. Both cheap and strong chains contain only Flash-Lite: each has no
fallback tail. The profile does not invent a VK selector the native API ignores.

Main's repository gateway allowlist now explicitly permits both
`gemini-3.5-flash-lite` and `gemini-3.5-flash` on `vk-bench`. Permission to route
Flash is not sufficient to support measuring escalation: the current offline
report and exporter require every actual request model to equal the planned
session model. Enabling Flash would create unsupported mixed-model evidence.
Do not silently flatten those costs, discard escalation, or call it comparable.
Preserve the potential Flash policy for an owner-reviewed runner/report/export
extension; no measured Flash escalation is enabled by this change.

Old Haiku manifests are historical inputs. Regenerate manifests from the verified
54-task index into **new output files**; do not rewrite old manifests or resume
an old run directory under a different policy. The mini runner rejects a legacy
policy before dispatch. The dataset task/oracle JSON files do not need changing
merely because the experiment's model/endpoint policy changed.

## Readiness observations

| Check | Status | Evidence |
|---|---|---|
| Branch/source | Verified | Clean `person-4` matched origin before integrating the latest main allowlist. |
| Installed mini | Verified | Ubuntu WSL2; mini 2.4.6, LiteLLM 1.109.1; previously verified template blob matches the pin. |
| Static routing | Verified | Installed mini forwards its configured model to LiteLLM; offline helper strips `openai/`, preserving the Gemini provider prefix. No inference occurred. |
| Main bench allowlist | Verified statically | Logical ID/name `vk-bench`/`bench`, active; both Gemini models explicitly listed. Live VK binding is not established. |
| Windows connectivity | Blocked | TCP connection to 127.0.0.1:18080 failed; no listener found. |
| Ubuntu WSL connectivity | Blocked | TCP connection to 127.0.0.1:18080 failed. |
| Credential provisioning | Blocked | Required bench environment/keyring locations were not provisioned. No values were printed or stored. Owner confirmed provisioning is pending. |
| Native policy binding | Mismatched | Current process has no user model/endpoint settings; native defaults remain Haiku/8080/public VK. Profile is not an activation API. |
| Native sampling | Mismatched | Agent still supplies temperature 0.0 or 0.7; mini profile supplies none. |
| Cache/thinking parity | Unverified | Static declarations cannot establish Gemini caching/default-thinking behavior through the live gateway. |
| Hard deadline parity | Unverified | Native 600 s is cooperative; mini's worker watchdog does not contain all descendants. |
| Live header and usage | Blocked | No request sent; session ID, request ID, served/billed model, status and token counts are unobserved, not zero. |
| Physical log schema/version | Unverified | No authorized logs.db location or flush interval supplied; no database opened. |

The gateway owner confirmed the missing local service, credential provisioning and
approved log location. Work then remained limited to static configuration and
synthetic tests. No endpoint, credential or database path was guessed. These
findings do not establish live Gemini availability, a $15-cap binding or parity.

## Exporter comparison still required

There is no observed physical schema to compare yet. The current exporter expects
table `logs` and the conversation-supplied mapping: `session_id`, `id`,
`parent_request_id`, `virtual_key_name`, `virtual_key_id`, `provider`, `model`,
`served_model`, `prompt_tokens`, `completion_tokens`, `total_tokens`,
`cached_read_tokens`, `token_usage`, `cost`, `status`, `timestamp`.
Nested usage paths and fail-closed semantics remain in
[bifrost-export.md](bifrost-export.md). Nothing in this change relaxes them.

Once the owner provides an authorized, consistent source, inspect actual DDL and
types read-only, then match the exact probe session and bench VK to request IDs,
actual model/status and explicit token/cache categories after the documented
flush delay. Never select prompts, raw payloads, headers or credential tables.
The existing exporter requires a reviewed standalone quiescent snapshot; it
refuses active WAL/SHM stores. Do not checkpoint, migrate, delete or change journal
mode to make it work. Cache-write TTL, retries, missing/failure usage and complete
request inventory still require review; missing counts cannot become zero.

## Remaining steps before one probe and the three-task smoke

1. Gateway owner: make v2.5.1 available on port 18080; confirm approved model
   availability, same bench VK ID/name/shared cap and both Windows/WSL access.
   Provision keys securely in the execution environments, not in configs or chat.
   Supply the authorized log location and flush/completeness procedure.
2. Native owner: support the bench VK binding and omission of sampling overrides
   for official runs, using this reviewed endpoint/model profile. Keep Flash
   escalation disabled unless mixed-model runner/report/cost support is agreed.
   Agree cache/thinking/retry semantics and resolve hard deadline/cleanup gaps.
3. With setup confirmed, send only one separately authorized non-benchmark mini
   request under a unique `mini-probe-UUID`, provider-default thinking, no model
   fallbacks and a strict one-attempt transport bound. Mini's ordinary `query`
   helper can retry up to ten times; do not use that loop unmodified for the probe.
   Never execute a returned tool call. Save only sanitized metadata.
4. Wait the owner's flush interval; establish read-only row/schema evidence and
   request completeness. Only reviewed successful forwarding evidence can set
   `session_header_verified` true. Receipt/SDK cost is not authoritative.
5. Regenerate all Gemini manifests from the verified dataset inputs, verify their
   shared full-plan identity and 2+2+1 ordering, then obtain authorization for the
   three-task smoke. No live-smoke readiness is claimed until the blockers above
   are resolved. No benchmark exercises have been run by this readiness work.
