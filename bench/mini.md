# mini-swe-agent 2.4.6 WSL2 adapter

The adapter executes mini only in a separate WSL interpreter, never importing it
into Crocodile or substituting Crocodile for a baseline run. Adapter tests use fake
WSL/mini processes and synthetic exercises. The [local environment record](mini-environment.md)
now documents the installed Ubuntu mini 2.4.6 environment, key-free settings and
offline Gemini routing check. Live gateway/model access remains unverified; no
paid call or real benchmark exercise was run.

## Verified source configuration

Upstream tag `v2.4.6` resolves to commit
`a83fcae82d2a08f0ee0c688f9d137b3566c097f8`. The installed default `mini.yaml`
must match Git blob `8b72f71f8092ae805ec43221dbeaeefc2340cd3e`. Sources:

- [Default loop and caps](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/agents/default.py)
- [Default templates/config](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/config/mini.yaml)
- [Model kwargs and cache forwarding](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/models/litellm_model.py)
- [Local execution](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/environments/local.py)
- [CLI/interactive layer](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/run/mini.py)

`bench/configs/mini-2.4.6.json` freezes version/template identity,
`step_limit: 30`, `wall_time_limit_seconds: 600`, `cost_limit: 0`, model
`openai/anthropic/claude-haiku-5-5`, `cost_tracking: ignore_errors`,
`set_cache_control: default_end`, `drop_params: true`, and `fallbacks: []`.
No temperature/top-p/sampling parameter or semantic cache key is added.

The separate bridge uses upstream `DefaultAgent` and `LocalEnvironment` with
unchanged installed mini.yaml agent **and model** templates. This is the base
loop underlying CLI yolo, without interactive UI/setup or global-config merge.
Only trajectory saving is overridden to emit a sanitized receipt. Normal mini
serialization includes model configuration and runtime headers; raw trajectories
cannot safely be saved with a bench key in model kwargs.

Installed version and template identity are checked at runtime. LiteLLM version
is retained in successful receipts; transitive dependencies are not newly locked.
Adaptive thinking/medium effort relies on the agreed provider defaults. Equality
through LiteLLM/Bifrost and Crocodile is **not live-verified**. Plans with a
different declared evaluation policy are refused.

## Configuration and execution

Provision the separate mini 2.4.6 virtual environment and bench-only WSL environment
variable independently. Nothing here installs software, stores a key, or changes
WSL/network/gateway configuration. A key-free settings JSON example is:

```json
{
  "distro": "Ubuntu",
  "python": "/home/USER/.venvs/mini-2.4.6/bin/python",
  "api_base": "http://127.0.0.1:8080/v1",
  "credential_env": "CROCODILE_BENCH_VK",
  "session_header_verified": false,
  "session_header_evidence": ""
}
```

`credential_env` is a variable name, never its value. Only a future authorized
WSL worker reads the provisioned value and sets `x-bf-vk` in memory. It removes
credential variables from child environments and isolates mini's global config
to an empty temporary directory. Raw stdout/stderr, conversations, response
payloads, exception text and credential-bearing configs are not persisted. The
receipt allows version, template/SDK identity, exit status, steps and explicit
usage only; missing usage stays unknown. Debug output is disabled/discarded.
This is not an OS sandbox: same-user commands can access other files/network.
Use trusted public benchmark exercises.

Preflight checks the WSL2 kernel marker, separate venv, distribution version and
credential presence without a model call. Custom WSL kernels lacking that marker
are refused pending review. Paths use argv-only `wslpath`, never guessed mounts.
Only loopback `/v1` is accepted. Verify mirrored networking independently using
[Microsoft's WSL documentation](https://learn.microsoft.com/en-us/windows/wsl/wsl-config);
the vEthernet fallback is not configured automatically.

Future authorized mini-only invocation:

```text
python -m bench.mini --plan PLAN.json --output RUN_DIRECTORY --oracles ORACLES.json --settings MINI_SETTINGS.json --execute
```

It visits only the two existing mini slots per task, in plan order; the immutable
2+2+1 plan is unchanged. Other variants remain unexecuted in this invocation.
For all five runs interleaved in their original order:

```text
python -m bench.run --plan PLAN.json --output RUN_DIRECTORY --oracles ORACLES.json --mini-settings MINI_SETTINGS.json --execute
```

Without mini settings the original runner still marks mini blocked. Neither CLI
executes without opt-in. API: `MiniAdapter(Settings(...), backend=None)`, passed
to `run_plan(mini_adapter=..., variants={"mini-swe-agent"})` for mini-only work.
Tests inject the process backend and fake Crocodile services. Imports/help do not
call models. `mini-settings.json` freezes settings, config and bridge hash on first
execution. Resume cannot change them or duplicate completed run IDs. Incomplete
attempts require explicit `--retry-incomplete`; previous evidence remains retained.

## Outcomes, independent grading and reporting

Each attempt freezes an original, prepares a fresh temporary exercise without
any `.meta/`, and supplies exact planned task text including its test command.
The final tree is retained before cleanup, then the existing grader restores the
original tests in a fresh copy. Submission and independently graded solved status
are separate. Missing WSL/interpreter/version/credentials, quota/rate limits,
authentication, transport/process and unknown exits are **incomplete**, not
measured task failures. `Submitted`, step `LimitsExceeded`, and
`RepeatedFormatError` are recognized operational exits; grading decides solved.
Timeout/interruption remains incomplete even if the final tree grades green.

Records use the existing attempt JSONL plan/full-plan/task/shard/run/repeat IDs,
timestamps, command/config/receipt/final/grading paths, versions, steps, usage and
outcome. `command.json` records actual key-free argv. Custom planned pytest flags
remain blocked by the current common runner/grader contract.

`bench.mini_report.report_row(attempt, planned_run, individual_cost_bundle)` joins
only a completed attempt with separately acquired complete Bifrost cost evidence.
It verifies hashes, model, raw session binding and recomputed cost, then returns
exactly the v1 report fields. It does not invent cost or publish a report. Setup,
incomplete and unresolved time-window attempts are refused. The reporter still
requires the full 2+2+1 grid; two mini rows alone are not a complete benchmark.
Retried runs are also refused by this report join until cost evidence can include
all earlier attempts/sessions. `prior_attempt_ids` records that obligation; a cheap
successful retry must never hide earlier failed-call costs. CLI resume success
uses the latest status per selected run while preserving all historical rows.

## Attribution and timeout guarantees

Source confirms kwargs forwarding to LiteLLM, **not** end-to-end preservation
through an installed LiteLLM/Bifrost pair. With default header verification false,
`session_id` stays null and a bounded UTC process-start/end window is recorded.
Cost attribution stays incomplete; concurrent sessions cannot be identified by a
time window alone. An audited independent resolution is still needed.

After verifying forwarding, set `session_header_verified: true` plus an evidence
reference. A unique `mini-UUID` is sent as `x-bf-session-id` and persisted before
launch. The separate exporter must still verify VK, request inventory, usage and
price completeness. The flag is reviewed caller input, not automatic verification.

Mini enforces 30 model-call steps and checks 600 seconds before queries. The Linux
supervisor kills its worker/group at 600 seconds. The Windows transport allows
650 seconds for setup/shutdown, then attempts targeted cancellation. PID start
time, attempt identity and worker command line are checked; no distro termination
is used. Interruptions halt subsequent dispatch. Unconfirmed host-timeout cleanup
stops the queue and requires inspection before retry.

LocalEnvironment creates independent command process groups. Killing the worker
cannot guarantee termination of escaped/background descendants, so
**`hard_deadline_enforced` remains false**. The worker watchdog is separately
recorded; no cgroup/tree containment is claimed. Actual WSL cleanup was not tested
live. Native Crocodile still has only its cooperative deadline.

## Remaining live fairness checks

Verify bench VK identity/shared cap, gateway version, mirrored reachability,
header forwarding, actual served model, adaptive/medium defaults, prompt caching
and server semantic-cache disablement. Crocodile's owner adapter still has public
alias/fallback/escalation/temperature defaults needing coordinated override; no
other owner's code changes here. Mini retains its default 30-second per-command
timeout, an environment difference to review. The cost exporter still rejects
current Haiku tiering, cache writes with unknown TTL, retries and unverified
completeness. These remain live-smoke blockers; synthetic passes are not evidence
of a comparable paid benchmark.

The pinned [mini retry helper](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/models/utils/retry.py)
retains up to ten attempts per model query by default and re-raises the underlying
error. HTTP attempts are not agent steps. Include all retries in future cost
attribution and review this policy alongside Crocodile's gateway retry/fallback
configuration; do not assume a 30-step cap means at most 30 HTTP requests.
