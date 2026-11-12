# 08 · Token and accuracy engine

Two halves: the **token engine** makes each turn cheaper; the **accuracy engine** makes each turn count and stops turns that cannot help. Every lever sits behind a `layers:` flag, logs the tokens it saved, and stays on only if the bench shows pass rate does not drop ([10-evaluation](10-evaluation.md)). All deterministic steps cost zero LLM tokens.

| # | Lever | Tier | Flag |
|---|---|---|---|
| 1 | Cache-stable prefix | P0 | `cache` |
| 2 | Output gate (head + tail + failures + spill + secret scan) | P0 | `gate` |
| 3 | Read cache | P0 | `readcache` |
| 4 | Staged SEARCH/REPLACE matcher | P0 | `matcher` |
| 5 | Batched masking | P0 | `mask` |
| 6 | Compaction | P1 | `compact` |
| 7 | Pinned task state | P0 | always on |
| 8 | Localisation | P1 | `localize` |
| 9 | Reproduce-first | P0 existing tests · P1 agent-written repro | `ladder` |
| 10 | Verification ladder | P0 | `ladder` |
| 11 | Stop-on-green | P0 | `stop_green` |
| 12 | Thrash detector | P0 simple | `thrash` |
| 13 | Cheap-first escalation | P0 | `escalate` |
| 14 | Early termination (hopeless stop) | P1 | `early_stop` |

## 1. Cache-stable prefix (P0)

- Order: `tools (sorted, terse) → system (static: no dates, paths or names) → [BP1]`, then append-only history with rolling breakpoints on the last two tool/user messages, then pinned task state last.
- Anthropic `cache_control` passes through Bifrost chat completions (requires Bifrost ≥ v2.5.0, fix #8712); ≤ 4 breakpoints; minimum cacheable prefix 512 tokens on the 5.5 models. OpenAI: `prompt_cache_key = session id`. One `x-bf-session-id` per session.
- Nothing in the prefix changes mid-session. The status line shows cache hit %.

## 2. Output gate (P0)

```python
def gate(kind, raw, exit_code, s):
    text = secret_scan(strip_ansi(raw)); h = spill.put(s, text)       # out:N, session-scoped, int-only handle
    shown = PARSERS[kind](text) if kind in PARSERS else head_tail(text, 256, 10_240, head=0.2)
    keep = group_by_signature(must_keep(text))   # error lines, failing ids, assertions, in-repo frames, exit code
    shown = merge(shown, keep, cap=10_240)       # "x412 AssertionError in test_x[...]; first 3 shown; rest in out:N"
    return shown + f"\n[exit {exit_code}; full output: {h} ({n} lines) -> read('{h}', start, end)]"
```

Tail-biased (20/80) so tracebacks survive. The must-keep set is grouped by error signature, so 1,000 failures still fit the cap (review 07 M8). `read("out:N")` parses `N` as an int scoped to the session dir.

## 3. Read cache (P0)

`path → (sha, turn, visible)`. Unchanged and still visible → `unchanged since turn N (sha 9f3a…)`. Changed → unified diff if smaller than 40% of the window, else the new window. Masked → sent again. Old messages are never rewritten outside a batched mask.

## 4. Staged SEARCH/REPLACE matcher (P0)

1. Exact. 2. Whitespace-normalised (same indent offset on every line). 3. Drop a leading blank line. 4. `...` elision, each piece unique. 5. Fuzzy (`SequenceMatcher` ≥ 0.9) **only if exactly one** candidate reaches it; the approval diff shows "fuzzy match 0.93". 6. Otherwise "did you mean" (best chunk ≥ 0.6, ±5 lines) and a request to resend only the failed blocks. Edits ask for ≤ 60-line blocks so `max_tokens` truncation is rare.

## 5. Batched masking (P0) and compaction (P1)

```python
def maybe_mask(s, p):
    old = [m for m in s.history if m.role == "tool" and s.turn - m.turn > 10 and not m.masked]
    gain = sum(m.tokens for m in old) - STUB * len(old)
    if gain < 6000: return False                                   # batch, never per turn
    if gain * p.cache_read * turns_left <= tokens_after(old[0]) * (p.cache_write - p.cache_read): return False
    for m in old: m.content = f"[{m.tool} output masked (turn {m.turn}); exit {m.exit}; {m.must_keep_summary}; full: {m.spill}]"
```

Masking breaks the cache once per batch, so it only fires when the saving beats the rewrite cost. **Compaction (P1)** triggers on tokens (≥ 0.8 × the window or the price-tier boundary, e.g. Haiku's 100k), runs on the cheap model with a fixed section template, must shrink by ≥ 10% and must keep every must-keep line, else it is rejected. The pinned task state is never compacted. **Fit** (P0, separate): before every call, `context.fit(0.7 × ctx_window)` masks, then falls back to a hand-off capsule, then refuses.

## 6. Pinned task state (P0)

Rendered last in every prompt (≤ 600 tokens; oldest decisions truncated first, never the task or failing tests): task verbatim, oracle ids, plan/TODOs (from the model's `PLAN:` block), decisions, current failing tests in `format_failure` form, phase, strategy switches so far. It survives masking, fitting and compaction.

## 7. Localisation (P1)

Candidates (0 LLM tokens) = `rg` over identifiers in the task ∪ stack frames of the oracle failure ∪ (P1) an `ast` file/def list → ≤ 5 files; then a ±30-line window per chosen symbol into the context. Rule (P0, cheap): an edit is accepted only on a location that `read` has shown. Polyglot tasks barely exercise this; QuixBugs does.

## 8. Reproduce-first (P0 existing tests)

At session start, under test consent: run the tests named in the task (Polyglot/QuixBugs ship them) once to confirm they fail, and run the full suite once to record the **baseline passed-id set**. Freeze `OracleSpec{test_ids, file_shas of the test files, every conftest, pytest config}`. Any later edit to those paths is red ("modifies the success criterion") and, if applied, voids green until the user re-confirms. **P1:** if no failing test exists, the model writes one minimal repro test (amber "defines success"), which must fail on an assertion (not ImportError/SyntaxError); the receipt then says **PASSES AGENT TEST**, never SOLVED.

## 9. Verification ladder and stop-on-green (P0)

| Rung | Check | Execution |
|---|---|---|
| 1 syntax | in-process `compile(src, path, "exec")` on touched files, no `.pyc` | none |
| 2 lint | `ruff check --isolated --no-cache --select F821,F822,F823,E9 --output-format json`, no writes | our pinned exe, no repo config |
| 3 affected | oracle + name-mapped tests (`foo.py → test_foo.py`, tests importing the module) | under test consent |
| 4 full | full suite once, only when rung 3 is green | under test consent |

The model sees only `format_failure` output: per failing test the id, the assertion with expected vs actual, ≤ 3 in-repo frames, ≤ 10 lines of captured stdout; then "N passed, M failed" and the spill handle (target 150–400 tokens).

**Green** = every oracle id passes **and** `baseline_passed − passed_now = ∅` (compared by id set, not count) **and** no new `skip`/`xfail`/deselect in the diff **and** oracle files unchanged since freeze. The oracle is rerun once on first green (flake guard). Then the task finishes with a template message: no "double-check" turn; the model's opinion is never asked. A full suite that timed out → receipt "SOLVED (partial suite)".

## 10. Thrash detector and cheap-first escalation (P0)

- Signature `sig = sha1(exc_type, message with numbers/paths stripped, failing test id, top in-repo frame)`.
- Triggers (refined per review 07 M9): same `sig` twice **and** the two edits touched overlapping hunks; the same edit hash proposed twice; (P1) no test delta for 4 turns, counted only after the first applied edit.
- Strategy ladder: switch 1 → **escalate** cheap → strong with a hand-off capsule (pinned state + diff so far ≤ 40 lines + last `format_failure` + names of files read); switch 2 → **stop_report** (localised files, failing tests, last diff, spend). P1 adds "relocalise" before escalate.
- Escalation is driven only by evidence (ladder failures, thrash triggers, an edit spanning > 3 files), never by how hard the task text sounds. The banner prints the reason: `▲ ESCALATE: same failure twice → sonnet-5-5`.
- Every trigger is journaled, so the bench can count triggers that fired on tasks later solved.

## 11. Early termination (P1)

Stop as "hopeless" when the signature is unchanged for 4 turns after an escalation, or the task's spend passes the quote's high end with no test delta. Logged; the bench treats it as unsolved.
