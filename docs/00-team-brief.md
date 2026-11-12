# 00 · Team brief: Crocodile

*Global AI Hackathon, PS-01 (sponsors: Bifrost by Maxim AI, Tavily). Build closes **15 Nov 2026 12:00**; judging **29 Nov**. Brief v5, 12 Nov. Read time: 5 minutes.*

**Crocodile snaps up wasted tokens.** CLI `crocodile` (alias `crock`; never `croc`, which is taken).

## 1. The problem

Build a coding agent that finishes real coding tasks on the **fewest tokens without compromising correctness**. Our reading: **more correct work per token**. A cheap agent that fails, or thrashes before it succeeds, loses. It must also meet 4 mandatory rules:

1. **Reliability:** keep working through outages and rate limits, and tell the user when another model takes over.
2. **Budget:** each user's limit is enforced **before** every model call, with defined behaviour at the limit.
3. **Privacy:** confidential repos are processed **only by local models**, whatever the prompt says.
4. **Approval:** reads are free; writes, commands and git need approval that prompts cannot override.

Judging: innovation, technical execution, problem and impact, use of AI, UX, scalability (no weights published).

## 2. Our pitch (10 seconds)

> **"Crocodile is a coding agent that charges you for fixed bugs, not for tokens. On the same tasks and model, we measure its cost per solved task against mini-swe-agent, and its budget, privacy and approval rules are enforced in code, so a prompt can't talk its way past them."**

Tagline: **"Pay for fixed bugs, not wasted tokens."** Secondary: "measured, not claimed".

Order of the story: **tokens and cost per solved task first, the four rules second.**

## 3. What we build (P0 slice, by 14 Nov evening)

| Area | What |
|---|---|
| Loop | Our own ~400-line loop with structured tools; mini-swe-agent is only the baseline |
| Tokens | Cache-stable prompt prefix; output trimmed to the failure with full output saved to disk; read cache; staged edit matcher; batched masking of old output |
| Accuracy | Tests are the oracle; verification ladder after every edit (syntax → lint → affected tests → full suite); stop on green; thrash detector; cheap model first, escalate only on evidence |
| R1 | Bifrost fallbacks + "MODEL TAKEOVER" banner with the error class; journal + resume that never repeats a side effect |
| R2 | Atomic reservation before every call at the most expensive fallback's price; admin-only limits; ladder strong → cheap → local → pause; 8-process race demo |
| R3 | Confidential marker + sticky registry; only the local key is loaded; only allowlisted local Ollama models (cloud tags rejected); web search off; egress log + canary audit |
| R4 | Console-only approvals; commands as argv lists; running the repo's tests counts as running its code and needs approval; hardened git; red prompt naming the file and line that suggested a command; file-edit undo |
| Proof | Paired bench (Polyglot Python 34 + QuixBugs 20) vs mini-swe-agent and our all-off twin; 15-case red-team MVP |

P1 (if time) and P2 (roadmap) are listed in [02-build-plan](02-build-plan.md). Nothing P1/P2 is claimed in public material.

## 4. Why it can win

- Other entries already ship the basics (estimate, 80% warning, local key, banner). Their source shows real holes: budgets overshoot in parallel, "local mode" holding the cloud key, web search left on, shell allowlists bypassed by `&` or a newline, `git status` running code from a repo's config.
- Peers report "% fewer tokens" against a naive twin on 4–17 tasks, often without pass rate. We report **cost per solved task with pass rate, paired, against a real open baseline**, plus the naive-twin comparison they use.
- Bifrost passes Anthropic prompt-cache markers through (v2.5.0+), so our largest saving works through the gateway.

## 5. Timeline

| Day | Goal |
|---|---|
| 12 Nov | Day-0 checks, baseline smoke, core loop, bench harness, R4, R3, R2 |
| 13 Nov | Race demo, integrity, failover + resume; levers and verification; UX; red-team; bench run 1 overnight |
| 14 Nov | Run 2 + twin; 12:00 feature freeze; report; 18:00 numbers frozen; record video |
| 15 Nov | Video edit, README, repo public, **submit by 11:00** |

Hour-level plan and go/no-go checkpoints: [02-build-plan](02-build-plan.md).

## 6. Roles

Likely solo: the builder owns everything in the order of the build plan. If people join:

| Owner | Area | Read |
|---|---|---|
| Builder | Loop, budget, token and accuracy levers | architecture 02, 06, 08 |
| #2 | Bench + report (from 12 Nov 15:00) | architecture 10 |
| #3 | Confidential mode, approvals, red-team tests | architecture 05, 07 |
| #4 | README, video, submission (from 14 Nov) | 01-playbook, 03-claims |

## 7. Rules we follow

- The core (loop, budget, approvals, confidential router, levers, bench harness) is written 12–15 Nov. Research and design happened 10–11 Nov. Libraries, Bifrost and mini-swe-agent (baseline only) are used unmodified.
- Borrowed code only under MIT/Apache, with attribution in `NOTICE`. GPL/AGPL/unlicensed code is read only.
- Disclose every AI tool used to build it (Claude Code) in the submission.
- Public wording only from [03-claims](03-claims.md). Never name peer teams ([internal/peer-notes](internal/peer-notes.md) stays internal).
- Watch the official Discord daily.

## 8. Top risks

1. mini-swe-agent baseline does not run (WSL2 networking) → all-off twin only, disclosed.
2. Polyglot tasks are implement-from-spec, so localisation and reproduce-first barely show; QuixBugs covers bug-fixing.
3. mini-swe-agent is lean: realistic savings may be 10–35%, or none. The narrative for each outcome is pre-agreed ([architecture/10](architecture/10-evaluation.md)).
4. 34 + 20 tasks cannot separate pass rates: we claim non-inferiority at most.
5. Local model slow or out of memory → `qwen2.5-coder:7b` or `3b`, small demo repo, pre-recorded clips.
6. Solo time: P1 only after P0 is green; every cut goes to the roadmap slide.
