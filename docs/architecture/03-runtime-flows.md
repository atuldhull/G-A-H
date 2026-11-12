# 03 · Runtime flows

All diagrams are P0 unless marked. Participants: `L` loop, `C` context, `P` policy, `B` budget, `R` router, `E` egress, `J` journal, `BF` Bifrost.

## 1. One model call, end to end

```mermaid
sequenceDiagram
  participant L as loop
  participant C as context
  participant R as router
  participant B as budget
  participant J as journal
  participant E as egress
  participant BF as Bifrost
  L->>C: build(session) - prefix, history, pinned state
  C->>C: fit(route.ctx_window x 0.7) - mask, else capsule, else refuse
  L->>R: plan(session, phase)
  R-->>L: Route(chain, fallbacks, vk_alias, max_tokens, ctx_window)
  L->>B: reserve(principal, route, prompt)
  B->>B: integrity.verify_state()
  B->>B: BEGIN IMMEDIATE - price at chain max and tier, clamp to remaining
  B-->>L: Reservation(held)
  L->>J: model_request(rid, reservation_id, chain, est_in, max_tokens)
  L->>E: post_bifrost(body, route, reservation_id)
  E->>E: asserts - prefixed ids, explicit fallbacks, held reservation, canary scan
  E->>J: egress row
  E->>BF: POST /v1/chat/completions (x-bf-vk, x-bf-session-id)
  BF-->>E: 200 + usage + x-bifrost-routing-info headers
  E-->>L: response
  L->>B: reconcile(res, usage, actual_model)
  L->>J: model_response(routing, usage, cost)
```

## 2. Tool call with approval

```mermaid
sequenceDiagram
  participant L as loop
  participant P as policy.decide
  participant U as console (CONIN$)
  participant I as integrity
  participant S as shadow git
  participant T as tool
  participant J as journal
  L->>P: decide(call)
  P->>P: schema, hard deny, confidential, provenance, free read, consent/grant
  P-->>L: Decision(ask, red, steered_by README.md:40)
  L->>J: tool_proposed(call, decision, token)
  L->>U: render panel (escaped argv, source file:line)
  U-->>L: typed "run 47"
  L->>P: recompute token - must match
  L->>S: snapshot(call_id)
  L->>J: tool_started(call_id, snapshot)
  L->>I: watch(call_id) begins - hash watch-set
  L->>T: run(args) via procs.run (job object, scratch profile)
  T-->>L: raw output
  L->>I: watch ends - any foreign change means abort, fail closed
  L->>L: output gate - must-keep, secret scan, spill out:N
  L->>J: tool_result(blob_sha, spill, tokens_shown)
```

Edits follow the same path but the panel shows the diff. An edit approval never authorises running code: if the edit touched `.py` code under a test consent and has a non-empty exec surface, the next test run asks again ([05 §4](05-security-model.md)).

## 3. Failover

```mermaid
sequenceDiagram
  participant E as egress
  participant BF as Bifrost
  participant A1 as primary (anthropic/claude-sonnet-5-5)
  participant A2 as fallback (anthropic/claude-haiku-5-5)
  participant F as failover
  participant U as ui
  E->>BF: model=anthropic/claude-sonnet-5-5, fallbacks=[anthropic/claude-haiku-5-5]
  BF->>A1: request
  A1-->>BF: 401 (bad key)
  BF->>A2: same request
  A2-->>BF: 200
  BF-->>E: 200 + is-fallback=true, primary-model, routing-info-model
  E->>F: parse(headers, body)
  F->>F: error class of primary from Bifrost logs - auth, rate-limit, quota, transient, caller-fault
  F-->>U: MODEL TAKEOVER banner (class, new model, cost delta)
  F->>F: journal failover event
```

Bifrost fires explicit fallbacks on **any** primary error, 4xx included (09 §1.5). So the banner always names the class. A `caller-fault` class (bad request) is shown as "request rejected, fallback answered" and is counted as a bug, not an outage. The reservation already covered the most expensive chain member, so a takeover cannot overspend.

## 4. Budget limit hit and the ladder

```mermaid
sequenceDiagram
  participant L as loop
  participant B as budget
  participant R as router
  participant U as ui
  participant J as journal
  L->>B: reserve(route rung=cheap)
  B-->>L: Denied(remaining 0.004, needed 0.011)
  L->>B: try smaller max_tokens (floor 1024)
  B-->>L: Denied
  L->>R: ladder.step_down - cheap to local
  R-->>L: Route(ollama/qwen2.5-coder:7b, fallbacks [], ctx 32768)
  L->>L: context.fit(0.7 x 32768) before first local call
  L->>U: LADDER banner
  L->>J: rung_changed
  Note over L,B: local costs 0 and is journaled as a free reservation
  L->>B: next call - if Ollama unhealthy, rung = pause
  L->>J: paused(reason=budget)
  L->>U: resume hint - crocodile run --resume SID
```

A gateway HTTP 402 `policy_budget_exceeded` takes the same path (the VK budget is the independent server-side cap).

## 5. Confidential session

```mermaid
sequenceDiagram
  participant CLI as cli
  participant CF as confidential
  participant SE as secrets
  participant R as router
  participant E as egress
  participant BF as Bifrost
  CLI->>CF: mode_for(realpath of cwd, --repo, every path arg)
  CF->>CF: walk up + bounded scan down for .crocodile/confidential, registry by any repo-id part
  CF-->>CLI: confidential (sticky)
  CLI->>SE: load vk_local only - public VK and Tavily key never loaded
  CLI->>CLI: web_docs not registered
  CLI->>CF: check_local_model(model, OLLAMA_HOST)
  CF-->>CLI: ok - exact allowlist id, no cloud tag, loopback host
  R->>E: ollama/qwen2.5-coder:7b, fallbacks [], vk local
  E->>E: assert vk local, ollama prefix, allowlisted, fallbacks empty, no cache key
  E->>BF: POST (local VK permits only ollama)
  BF-->>E: 200 routing-info-provider=ollama
  E->>E: assert provider == ollama, else abort and flag
```

## 6. Resume from the journal

```mermaid
sequenceDiagram
  participant CLI as cli
  participant J as journal
  participant B as budget
  participant U as console
  CLI->>J: replay(SID)
  J-->>CLI: state, pending requests, started-without-result tools
  CLI->>CLI: policy sha and mode check - mode may only tighten
  CLI->>B: settle pending reservations from Bifrost logs by request id, else keep held
  CLI->>U: OUTCOME UNKNOWN for started tools - show diff vs snapshot, never re-run
  CLI->>U: re-ask proposed-but-not-started calls
  CLI->>J: resumed(from_seq)
```

The model receives `{"status":"unknown","diff":...}` for a started-without-result call, so it cannot be tricked into repeating a side effect.

## 7. Verification ladder loop

```mermaid
sequenceDiagram
  participant L as loop
  participant V as verify
  participant T as tools.tests
  participant TH as thrash
  L->>L: edit applied (approved)
  L->>V: ladder(touched)
  V->>V: rung 1 syntax - in-process compile, no pyc
  V->>V: rung 2 lint - ruff --isolated --no-cache F821 F822 F823 E9, no fix
  V->>T: rung 3 affected tests (oracle + name-mapped) under test consent
  T-->>V: report by test id
  V-->>L: VerifyResult(stage, ok, sig)
  alt green
    L->>V: final full suite once, compare by id set with baseline
    V-->>L: is_green - finish, no extra model turn
  else failing
    L->>TH: check(sig, edit hash)
    TH-->>L: none, escalate, or stop_report
  end
```

No consent → the ladder stops at rung 2 and the receipt says "tests not run: no consent".
