# Part 2 state integrity, routing and evidence — 2026-11-15

## Protected writes

`BudgetManager(..., state_integrity=state)` uses Part 3's `StateIntegrity` under
each owner `BEGIN IMMEDIATE` lock: verify the existing seal, mutate, reseal, then
commit. Exceptions roll back the protected rows and seal together. Reservation,
reconciliation, cancellation, heartbeat and standalone lease expiry use this path.
Reservation's internal expiry shares its transaction. Without an injected manager,
the default is the real Credential Manager-backed `StateIntegrity`, not an opt-out.

Existing state must verify before a manager is opened. Creating a new database
bootstraps only its schema; the trusted initialization owner must create the other
protected owner tables and explicitly enroll once with `StateIntegrity.initialize`
inside a transaction. A missing/bad seal is never automatically repaired. Test
fixtures now enroll synthetic keys explicitly; production does not use them.
Inference admission requires an attached protected budget manager and an actually
held reservation verified against its sealed ledger; a fabricated nonempty ID
does not authorize a request. Diagnostic probes use their separate fixed-input API.

## Destination and socket policy

`NetworkPolicy` is trusted caller configuration. Defaults allow local Bifrost on
8080 and local Ollama on 11434, using 127.0.0.1, localhost or ::1. Custom pairs must
be configured explicitly. Confidential destinations must additionally be loopback.
Credentials, query strings, fragments and non-root base paths are rejected in base
URLs. The gateway URL is checked before confidential reservation and again directly
around each transport attempt. Redirects, proxy-environment discovery and hidden
HTTP transport retries are disabled.

Every request gets a scoped set of resolved IP-and-port pairs. The installed Python
audit hook checks connect/sendto/sendmsg; it does not authorize all loopback ports
or arbitrary HTTPS destinations. A public Tavily request is limited to the configured
api.tavily.com:443 origin and its resolved peers in that request's public scope.
Confidential requests cannot open a public-only scope. A changed DNS result cannot
extend an already active scope. Outside a scope, only the fixed local default pairs
are allowed. This is the client interpreter's guard, not a system firewall.

## Doctor evidence

The root `doctor` handler now calls Part 2's `collect_evidence`. The adapter probes
gateway health, inference authentication, validation of the local virtual key,
cloud-model refusal under that key, Ollama tags/show, the installed socket guard,
and the limits file ACL. It uses fixed synthetic diagnostic input, a local key from
Credential Manager, explicit local origins and bounded timeouts. No key, raw HTTP
error, model content, user task or ACL principal list is rendered.

Checks run independently. An unreachable/incorrect dependency is FAIL; a missing
key, unavailable ACL backend or absent independent refusal record is INCOMPLETE.
Either prevents a healthy exit status. A 4xx response alone does not prove zero
upstream provider calls. That assertion requires the correlated gateway record's
explicit `provider_calls: 0` and matching HTTP status. Windows ACL checks inspect
SIDs and conservatively reject ordinary-user write grants or non-admin ownership.

`CROCODILE_LIMITS` selects the trusted limits file. `CROCODILE_GATEWAY_LOG` selects
a gateway-owned normalized JSON/JSONL export outside the target repo; an active
exporter must include the newly generated diagnostic request ID. Missing or delayed
export evidence produces INCOMPLETE, never an invented zero-call attestation.

## Gateway correlation

Each HTTP attempt has a UUID client request ID, forwarded via `x-request-id` and
Crocodile correlation headers. The exact serialized bytes sent are hashed and
counted. Bifrost logging metadata receives ID, session, hash/length, key alias,
requested model and fallback list through `x-bf-lh-crocodile-*` headers. The checked-in
gateway template enables metadata logging and disables message-content logging.
Only non-secret correlation headers are configured; virtual keys are never logged.

The client stores the actual provider only from response routing evidence, never
by inferring it from the requested model. A response with missing/non-Ollama evidence
is refused in confidential mode. Requests that reached the transport remain `sent`
records even on provider breaches or malformed responses; unknown outcomes cannot
be hidden as pre-send blocks. Transport errors conservatively remain sent/unknown.

`read_gateway_records` accepts normalized exports, or projects a selected export
shape with `id`, actual `provider`, actual `model` and captured `metadata`. Projection
does not guess other vendor schemas. Actual provider/model come from the gateway's
routing record, never the requested model or a client metadata claim. Metadata
hash/length are the client's claims captured by the gateway; they do not constitute
independent re-hashing of the server's received body. `provider_calls` is retained
only when explicitly supplied by independent gateway instrumentation.

An operator can project a JSON array/JSONL export without retaining content/keys:

```powershell
python -m crocodile.gateway.records --input C:\trusted\bifrost-export.json --output C:\trusted\audit-export.json --repo C:\work\target
crocodile audit --all --allow-model qwen2.5-coder:7b --gateway-log C:\trusted\audit-export.json
```

The output must be a new file outside the target repo. Captured metadata keys are
`crocodile-request-id`, `crocodile-session`, `crocodile-payload-sha256`,
`crocodile-payload-bytes`, `crocodile-vk-alias`, `crocodile-model-requested` and
`crocodile-fallbacks` (a JSON string). A normalized sent record contains:
`request_id`, `gateway_request_id` when returned, `session`, actual `provider` and
`model`, `payload_sha256`, `payload_bytes`, `vk_alias`, `model_requested`, `fallbacks`.

Audit requires one gateway record per sent confidential client request. Missing
records in a supplied export, duplicates, mismatched fields and non-Ollama routing
fail. Missing correlation fields in old exports are INCOMPLETE rather than PASS;
omitting/downgrading `evidence_version` does not select a weaker correlation policy.
Keep raw log API/admin access outside the agent; supply the minimal trusted export.
The pinned gateway's logging/export schema must be verified when deployed.

The metadata headers and logging configuration follow Bifrost's primary
[observability documentation](https://github.com/maximhq/bifrost/blob/dev/docs/features/observability/default.mdx)
and [client configuration documentation](https://github.com/maximhq/bifrost/blob/dev/docs/deployment-guides/config-json/client.mdx).
No gateway process or admin settings were changed on this machine.

## Verification and remaining live check

Native Windows Python 3.12.10: the focused state/routing/gateway suite passed 60
tests, including concurrent writers without swallowed exceptions, reseal rollback,
real local HTTP sockets, exact wrong-port denial, public-only service denial,
zero-send URL rejection, changed-destination retry refusal, provider-breach logging,
export projection, healthy diagnostic output and one failed dependency at a time.
The Part 3 audit/doctor/integrity and normal CLI/adapter regression run passed 80
tests and 32 subtests before the final legacy-export tightening. Ruff and Python
compile checks passed on the changed code.
After that tightening the full Part 3 audit/doctor/integrity set passed again:
60 tests and 32 subtests. Independent-manager concurrency, mutating lease expiry
and the legacy-export downgrade check also passed their targeted rerun.
The final inference-admission/routing/adapter run passed 36 tests, and a separate
forged/cancelled-hold test passed with zero transport calls. Changed-file Ruff,
Python 3.12 compile/import checks and `git diff --check` passed after these changes.

Live probes on 2026-11-15 returned `ConnectError` for both approved local endpoints:
Bifrost 127.0.0.1:8080 and Ollama 127.0.0.1:11434. Thus a healthy real Bifrost/Ollama
deployment and gateway-record export remain unverified here. No live confidential
audit or healthy deployment is claimed; start/configure those services and the
trusted exporter, then run doctor and audit with the resulting actual records.
