# 06 · Budget and reliability

## 1. Identity and limits (P0)

- `principal = sha256(public VK)[:16]`. The VK comes from Credential Manager, never from an env var.
- The daily limit comes from admin-only `%PROGRAMDATA%\crocodile\limits.yaml`. The admin sets the same number on the user's VK budget in the Bifrost UI (P1: `crocodile admin set-limit` also calls `PUT /api/governance/virtual-keys/{id}`). There is no user-runnable `budget set`; `crocodile admin set-limit` refuses without elevation.
- The Bifrost VK budget (`budgets[].max_limit`, `reset_duration: 1d`) is the independent server-side cap. Exhaustion returns HTTP 402 `policy_budget_exceeded`.
- **Deployment profiles (stated in the README):**
  - *Shared gateway* (the real R2 claim): Bifrost and provider keys run under an account the user cannot read; users hold only VKs.
  - *Single-machine demo*: Atul is the Bifrost admin; Bob is a separate VK with $0.05. Bob cannot raise his limit through Crocodile, but someone holding the provider keys could bypass everything. We say so.
- Ledger window = UTC date. If the local clock is behind the newest ledger row, reserve refuses ("clock skew").

## 2. Reserve → reconcile → cancel (ADR-005)

```python
def reserve(principal, route, prompt, s):
    integrity.verify_state()                                   # tamper → fail closed
    raw = count_in(prompt, route)          # Anthropic: /anthropic/v1/messages/count_tokens (cached per prefix hash)
                                           # OpenAI: tiktoken o200k; Ollama: ceil(chars/2.5)
    est_in = ceil(raw * calib.q95(route.chain[0], default=1.35))
    bound_in = utf8_bytes(serialized_body)                     # BPE tokens <= bytes: a provable ceiling
    tier_in = est_in if raw is not None else HIGHEST_TIER      # unknown count → highest tier
    def worst(m, n_in, n_out):
        p = price(m, tier_for(m, n_in))                        # KeyError / TBD → Denied("unpriced")
        return max(p.in_, p.cache_write_5m or p.in_) * n_in + p.out * n_out
    with db_immediate():                                       # BEGIN IMMEDIATE; OperationalError → Denied (fail closed)
        expire_dead_leases()                                   # only rows whose owner process is gone
        remaining = limit(principal) - spent(principal) - held(principal)
        n_in = bound_in if remaining < 3 * worst_any(est_in) else est_in   # near the limit: hard-bounded mode
        max_out = min(cfg.max_out_cap, min(m.max_out for m in route.chain))
        while worst_chain(route.chain, n_in, max_out) > remaining and max_out > cfg.max_out_floor:
            max_out //= 2                                      # shrink output before refusing
        usd = worst_chain(route.chain, n_in, max_out)          # max over every chain member
        if usd > remaining: raise Denied(remaining, usd)       # a reservation can never exceed remaining
        insert(status='held', reserved_usd=usd, max_out=max_out, owner_pid=os.getpid(), heartbeat=now)
    return res                                                  # max_out is the value we SEND as max_tokens
```

- **Reconcile:** reprice at the model that answered and at its tier: `uncached = prompt_tokens − cache_read − cache_write` (Bifrost's `prompt_tokens` includes cached tokens), then `in·uncached + cache_read·r + cache_write·w + out·completion`. Record `overshoot_usd = max(0, actual − reserved)`; any non-zero overshoot is a test failure in the bench.
- **Cancel:** before any byte was sent → release. After send (timeout, network error) → the row **stays held at the full amount** until `crocodile budget reconcile` finds the request id in Bifrost `/api/logs`, or 15 min pass → settle at the full amount.
- **Lease, not TTL:** each held row stores owner pid, process start time and a heartbeat (every 20 s while the call is in flight). Only rows whose owner is dead, or whose heartbeat is > 60 s old after the call returned, expire. A laptop sleep cannot free money mid-call.
- **Every model call reserves:** `egress.post_bifrost` refuses without a held `reservation_id`. That covers compaction, probes and repro stubs structurally.
- **Retries:** Bifrost `max_retries: 0`; each client retry is a new reservation.
- **Warning:** at `warn_frac` (80%) the status line turns amber and the banner shows the next reservation size.

**Hard-cap semantics.** The local gate guarantees `Σ settled + Σ held ≤ limit` at all times. In hard-bounded mode (near the limit, input bounded by bytes, output by `max_tokens`) every settled call is ≤ its reservation, so the local ledger cannot overshoot. Away from the limit the p95 estimate can under-reserve input on ~5% of calls; reconcile records it, and the headroom (≥ 3× a call) absorbs it before the limit. The VK budget is the second wall.

**Tests:** `test_concurrency_50` (50 threads, $0.01 limit, exactly floor(limit/cost) succeed), `test_tier_reserve_haiku_150k`, `test_unpriced_denied`, `test_ledger_locked_denies`, `test_timeout_keeps_hold`, `test_inflight_not_expired_by_peer`, `test_egress_requires_reservation`, `test_clock_rollback`.

**Race demo** (`crocodile bench race --procs 8 --calls 10 --limit 0.02`): 8 OS processes against a mock Bifrost with fixed latency. Columns: ours (Σ ≤ limit, overshoot $0.0000) vs `--naive` check-then-record (overshoots by about (procs − 1) × call cost). A third column (real Bifrost VK at $0.01, 8 parallel calls) is P1 and labelled with its date.

## 3. Degradation ladder (P0)

```
rungs: strong -> cheap -> local -> pause            confidential: local -> pause only
on Denied or gateway 402:
    shrink max_tokens to the floor; still denied -> next rung whose cost fits remaining
    local needs a healthy Ollama and context.fit(0.7 * ctx_window); otherwise pause
    pause -> journal(paused, reason), print "crocodile run --resume <sid>", exit 0
new UTC window -> --resume restarts at the start rung
```

The prefix is rebuilt for the new model (an expected cache miss, shown on screen). History is kept, then fitted. Escalation (cheap → strong) uses the same ladder upward and is driven only by evidence ([08 §10](08-token-and-accuracy-engine.md)).

## 4. Failover (R1, P0)

- Every request sends a **provider-prefixed** model and an **explicit** `fallbacks` list. Egress refuses unprefixed ids, because Bifrost infers cross-provider fallbacks for them.
- Calls are non-streaming (Bifrost does not fail over after the first streamed token).
- Detection: `x-bifrost-routing-info-is-fallback`, `-primary-model`, `-model`, `-provider`, `x-bifrost-fallback-index`, or `extra_fields.routing_info` in the body.
- **Explicit fallbacks fire on any primary error, 4xx included** (09 §1.5). The banner therefore shows the primary's **error class**, using Bifrost's own classes: `auth`, `rate-limit`, `quota`, `transient`, `timeout`, `caller-fault`. The class comes from the Bifrost log entry for the request id; if that is unavailable, the banner says "reason unknown". `caller-fault` is journaled as our bug.
- The reservation was priced at the chain maximum, so a takeover cannot overshoot. Reconcile reprices at the answering model.
- All providers down: client backoff 1, 2, 4 … 60 s honouring `Retry-After`, 5 attempts, then pause. P1: a circuit breaker (3 consecutive fallbacks → primary open 120 s) and a local last-resort tail in public mode (fitted, with a banner).
- Empty content with `stop_reason = max_tokens` (Haiku thinking, Bifrost #9888) → retry once with a larger `max_tokens`, under a new reservation.

## 5. Journal and idempotent resume (P0)

- Events are written **before** every model call (`model_request`) and **before** every spawn (`tool_started`), and after each result. A crash loses at most the in-flight call.
- `crocodile run --resume <sid>`:
  1. Replay events; check the policy SHA; the mode may only stay or tighten.
  2. Pending reservations → settle from Bifrost logs by request id, else keep held.
  3. `tool_started` without `tool_result` → **OUTCOME UNKNOWN**: show the worktree diff against the snapshot; the model gets `{"status":"unknown","diff":…}`; the call is never re-offered.
  4. `tool_proposed` without `tool_started` → ask again.
  5. Rebuild the same frozen prefix, so the prompt cache still hits.
- P1: hash-chain the events table (`prev_hash`, `hash`). The wording is "hash-chained", never "tamper-proof".

**Tests:** `crash_resume` (kill after a model call; resume hits the cache), `crash_resume_mid_cmd` (no second prompt for the same call id), `outage_badkey` (banner shows `auth`).
