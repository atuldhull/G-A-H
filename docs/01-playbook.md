# 01 · Playbook: how we win PS-01

*v5, 12 Nov 2026. Public wording only from [03-claims](03-claims.md). Every number comes from bench/race/redteam output with model, n, runs and date. Never name peer teams.*

## 1. Thesis

1. Every PS-01 entry claims "fewer tokens". We measure what a buyer pays for: **cost per solved task**, paired against the leanest open baseline (mini-swe-agent, same model, same gateway) and against our own all-off twin.
2. We get there with **more correct work per token**: tests are the oracle, every edit is checked for free, we stop the moment tests pass, we cut thrashing early and escalate only on evidence, and we never trim away an error line.
3. The four rules are a pass/fail gate, so we show each one working with one concrete proof, enforced in code the model cannot reach.

**One-liner (first 10 s of everything):** *"Crocodile charges you for fixed bugs, not for tokens: on the same tasks and model it costs X% less per solved task than mini-swe-agent, and its budget, privacy and approval rules are enforced in code."* (Fill X only from the frozen report; if there is no saving, use the "same cost" line in [architecture/10 §2](architecture/10-evaluation.md).)

**Tagline:** *"Pay for fixed bugs, not wasted tokens."* Branding: one ASCII banner, "Crocodile snaps up wasted tokens". Zero hours on logos before 15 Nov.

## 2. Judging criteria → evidence

| Criterion | Scorable claim | Evidence | Where |
|---|---|---|---|
| Problem & impact | CPST and paired cost ratio vs mini-swe-agent, pass rate non-inferior (or honestly inconclusive) | `bench/report.md`, Pareto chart | README results (first), video 0:00–0:15, slide 2 |
| Innovation | Reservation at the most expensive fallback's price (0 overshoot in the race); provenance-named approvals; test runs treated as code execution; local model allowlist that rejects Ollama cloud tags | Race table, red prompt, consent panel, doctor FAIL on `-cloud` | README "What's different", video |
| Technical execution | CI green; 15/15 red-team MVP; race overshoot $0.0000; doctor green on a fresh clone | CI badge, scorecard | README top, video 2:30 |
| Use of AI | "AI where it earns its tokens, code where it doesn't": cheap model first, escalation printed with its evidence (`^ ESCALATE: same failure twice`), local model as a first-class worker, Tavily used by the agent on import/API errors, "LLM calls avoided by deterministic checks" on the receipt | Status line, escalate banner, receipt | README "How AI is used", video 0:15–1:30 |
| UX | Quote before spend, one status line, three banners, typed red confirms, receipt, undo | Recorded CLI | Video throughout |
| Scalability | One VK per user, ledger principal = VK hash, atomic reservation (SQLite → Postgres row locks), gateway budget as a second wall; the race demo is a concurrency test; unit economics "1,000 fixed bugs/month = $Y vs $Z" | Race demo, architecture slide | Slide 6 |

## 3. Video (≤ 3:00; check the limit on Discord)

Every segment is a real run, recorded on 14 Nov evening; the recording is the demo. Temperature defaults, tiny deterministic demo repos, `scripts\prep.ps1` resets state.

| Time | On screen | Voice-over (short) |
|---|---|---|
| 0:00–0:15 | Pareto chart (ours, all-off twin, mini-swe-agent) + one-liner caption | "Coding agents burn money on failed attempts. We measure cost per solved task." |
| 0:15–0:50 | `crocodile quote` → `crocodile run` in `demo\acme`: status line (cache %, $/budget, avoided tokens), ladder lines `syntax ok lint ok affected 3/4`, stop on green, receipt | "It quotes first, checks every edit for free, trusts the tests, and stops the moment they pass." |
| 0:50–1:15 | Thrash fixture: same failure twice → `^ ESCALATE` banner with evidence → green on the strong model | "When it repeats a failure, it switches strategy instead of burning turns. The routing decision is printed with its reason." |
| 1:15–1:30 | Bench table: paired cost ratio + pass rates, all-off twin row | "Same model, same tasks, same gateway, costs from Bifrost's logs." |
| 1:30–1:48 | **R2:** `crocodile bench race --naive` (ours $0.0000 vs naive > 0), then Bob at $0.05: warning → ladder → pause | "Eight processes, one budget. We reserve before every call, so we can't overshoot." |
| 1:48–2:06 | **R1:** bogus primary key → MODEL TAKEOVER (auth, 401) → task continues | "The primary fails; Bifrost fails over; we say who took over and why." |
| 2:06–2:24 | **R3:** `demo\vault`: "send this to GPT and search the web" → only Ollama, web denied; `crocodile audit` PASS | "Confidential repo: no cloud key in the process, only allowlisted local models." |
| 2:24–2:42 | **R4:** README injection → red "suggested by README.md:40", typed `n`; test-consent panel | "The command came from the README, and the prompt says so. Running tests is running code, so it asks." |
| 2:42–3:00 | Three numbers big (CPST ours vs baseline, pass rates, overshoot $0.0000) + repo URL | "Pay for fixed bugs, not wasted tokens." |

Captions on; no secrets on screen (`doctor` masks VKs); numbers identical to the README.

## 4. Slides (if there is a slot; max 6 + roadmap)

1. Title + one-liner + Pareto thumbnail. 2. The number: CPST, cost ratio, pass rates (model, n, runs, date). 3. Where tokens go and which lever cuts each. 4. The 4 rules, one proof each. 5. Architecture & scale (VK per user, reservation, Postgres path, unit economics). 6. Honesty: limitations, built vs borrowed, AI tools used. Roadmap: P1/P2 items.

## 5. README outline (submission repo)

1. Title, one-liner, CI badge, licence (MIT), "Built 12–15 Nov 2026 (research 10–11 Nov)". 2. **Results first**: Pareto PNG + table (CPST, cost ratio, pass rates, race overshoot) + link to `bench/report.md`. 3. Video link + 4 screenshots. 4. The problem and the 4 rules. 5. What's different (attack-class wording only). 6. How it saves tokens and stays correct (levers, flags, measured effect). 7. How AI is used. 8. AI tools used to build it (Claude Code; humans reviewed every change). 9. Architecture diagram + Bifrost/Tavily integration points. 10. Requirement → enforcement → test matrix. 11. Threat model (from architecture/05 §9, P0 rows). 12. Red-team MVP. 13. Bench methodology + one command to rerun + cost estimate. 14. Quickstart. 15. Scaling to a team. 16. **Limitations** (no OS sandbox; approved tests run repo code; same-user processes can bypass local checks; local Bifrost in the demo binds only an honest user; small n, no significance claims; contamination; Windows-first). 17. Built vs borrowed, licences, NOTICE. 18. Claims and sources. 19. Roadmap.

## 6. Submission checklist

| ☐ | Item | Due |
|---|---|---|
| ☐ | Video length limit, deadline time zone, track/problem ID checked on Discord | 12 Nov |
| ☐ | `.env` in `.gitignore` from the first commit; secret scan of history (`git log -p \| rg -i "sk-\|tvly-\|vk"`) | before public |
| ☐ | Submission repo public, MIT, CI green, `doctor` green on a fresh clone | 15 Nov 10:30 |
| ☐ | Description ≤ 150 words, problem, technologies, how AI is used, AI tools used to build it | 15 Nov 09:30 |
| ☐ | Bifrost and Tavily visibly used (README §9, video) | 14 Nov |
| ☐ | NOTICE + `third_party/` licences | 14 Nov |
| ☐ | Numbers frozen; README, video, slides show the same numbers | 14 Nov 18:00 |
| ☐ | Video uploaded (unlisted YouTube + Drive mirror), opens logged-out | 15 Nov 10:30 |
| ☐ | Form submitted; confirmation screenshot saved | **15 Nov 11:00** |

## 7. Judge Q&A

| Question | Answer |
|---|---|
| "Isn't this mini-swe-agent with extras?" | No. mini-swe-agent is only our baseline, run separately. Our loop is written from scratch with structured tools, which is why approvals can be enforced per action. |
| "Is the bench fair?" | Same model and thinking setting, same Bifrost, identical task text including the test command, mini's default template, same step and time caps, caching on for both, costs from Bifrost logs with one price table, tests restored before grading, configs and raw logs published. |
| "30-odd tasks is tiny." | Yes, so the design is paired: cost ratio on tasks both solved, pass-rate non-inferiority with a bootstrap CI, win/loss/tie. No significance claims. |
| "Why Polyglot, not SWE-bench?" | SWE-bench needs Docker images; not feasible on Windows in 3 days. Polyglot ships tests; QuixBugs adds real one-line bugs. |
| "Why not just use Bifrost budgets?" | We do, as the second wall. Bifrost checks usage without estimating the incoming request and books after the response, so parallel calls overshoot. We reserve first. |
| "Can a prompt approve itself?" | No. Approvals come only from the console, never stdin or the model; piped `yes` does nothing. Keystroke-injection hardening is untested, so we don't claim it. |
| "What if an approved test is malicious?" | It runs as you, as in every agent without a sandbox. We make you approve it as code execution, scrub its environment, kill its process tree, and stop the session if it touches our state. A sandbox is roadmap. |
| "What if Ollama is down in a confidential repo?" | Fail closed: the chain is local → pause, never cloud. Resume later from the journal. |
| "How does this scale?" | One VK per user, reservation in one transaction, SQLite → Postgres row locks, gateway budgets as a second wall; prompt caching makes repeat work on a repo cheaper. |
| "Your savings are only X%." | Against the leanest open baseline, not a straw man. Against our all-off twin, the comparison other entries use, it is Y%. And we enforce four guarantees the baseline doesn't. |
| "What did you build vs borrow?" | Built 12–15 Nov: loop, levers, budget, approvals, confidential router, bench harness. Used unmodified: Bifrost, libraries, mini-swe-agent (baseline). Ideas credited in NOTICE (LiteLLM reservation, Aider matcher, SWE-agent masking). |

## 8. Demo risk register

| Risk | Mitigation |
|---|---|
| Model wanders during recording | Tiny deterministic repos; 3 takes then use the backup clip; never fake output |
| Ollama slow or out of memory | `qwen2.5-coder:7b` (or `3b`) pulled early; warm-up call in `prep.ps1`; one-file confidential task |
| Only one provider key | Failover with a bogus Anthropic key for the primary model ([architecture/04 §7](architecture/04-data-model.md)) |
| Bifrost version drift | Pinned `--transport-version v2.5.1`; config in the repo |
| Console encoding | Windows Terminal, `--ascii` fallback, no emoji in CLI output |
| Secrets on screen | `doctor` masks VKs; frame-by-frame check |
| Judge tries to install on macOS | CI on ubuntu for platform-neutral tests, quickstart, the video is the demo |
| Numbers differ across README/video | Generate tables and chart from `bench/report.json` with one script |
| Upload or form failure | Submit by 11:00; two video hosts |

## 9. Daily rhythm (solo)

- 08:30: read yesterday's 5-line note; pick the next go/no-go checkpoint.
- Commit at least hourly (dated history proves "built during the hackathon").
- 18:00: run the day's increment end to end; record a 30-s clip of whatever works (backup library).
- 22:30: 5-line progress note (done, numbers, blockers, cuts).
