# Architecture changelog

## v5 (12 Nov 2026): review fixes + restructure
- **Restructure.** `DESIGN.md`, `TEAM-BRIEF.md`, `PLAYBOOK.md` split into `docs/` (team brief, playbook, build plan, claims) and `docs/architecture/` (11 files + 10 ADRs). `RESEARCH.md` → `research/00-round1.md`. Peer mapping → `docs/internal/peer-notes.md`.
- **Scope.** P0/P1/P2 tiers on every module and lever. P0 = minimum winning slice for 14 Nov evening; shadow-git undo of command side effects, hash chains, tree-sitter explainer, compaction, localisation funnel, FIDES-lite taint and wallet, hostile stub and the 45-case suite moved to P1/P2.
- **Critical fixes (review 07).** C1: anything that executes repo code needs approval; per-session test consent; static quote (ADR-004). C2: state integrity (HMAC key in Credential Manager, watch-set, scratch child profile, job object, admin-only limits, VK cap; residual risk stated). C3: local model allowlist, `:cloud`/`-cloud` rejected, loopback `OLLAMA_HOST`, in client and doctor.
- **High fixes (07).** Edit approval ≠ run approval (exec surface, green defaults to N); repo names untrusted for provenance; search/secret redaction + content scanner; confidential detection via realpath of every path + downward scan; per-call git config check; rev validation; tiered pricing, leases, hold-on-timeout, egress requires reservation, never above remaining; admin-only limits; user doctor without admin creds; `OLLAMA_CONTEXT_LENGTH` + fit-or-refuse; oracle freeze, test edits red, id-set baseline; ruff `--isolated`, no writes; bench run count fixed.
- **Medium fixes (07, cheap ones).** Grantable allowlist (only consented test argv); wider red/redact lists; `tool_started` + OUTCOME UNKNOWN on resume; must-keep grouping by signature; thrash false-positive guards; spill handle int-only; "SOLVED (partial suite)"; "hash-chained", never "tamper-proof"; "independent runs", not seeds.
- **Strategy (review 08).** Own loop, mini-swe-agent baseline only (ADR-002); paired design with non-inferiority; all-off twin; pitch leads with tokens/CPST, security second; claims only for built features; re-plan 12–15 Nov.
- **Facts (review 09).** Bifrost pin via `--transport-version v2.5.1`; `enforce_auth_on_inference`; explicit `provider_configs`, `is_active: true`; fallbacks fire on any error → banner shows error class; `count_tokens` via `/anthropic/v1/messages/count_tokens`; Haiku 5.5 tiered pricing and default thinking; OpenAI fallback `gpt-5-mini` (verified price); Polyglot Python = 34 + QuixBugs; mini-swe-agent in WSL2; Ollama context via env var.

## v4.1 (10 Nov): product named Crocodile
CLI `crocodile` (alias `crock`), package `crocodile/`, data `%APPDATA%\crocodile\`, marker `.crocodile/`, shadow refs `refs/crocodile/`.

## v4 (10 Nov): more correct work per token
CPST headline, ablation rule, accuracy-per-token section (localise, reproduce, verification ladder, stop-on-green, thrash detector, evidence-based escalation, pinned task state, lossless-on-errors).

## v3 (10 Nov): source-code reviews
shlex classifier removed, argv-only commands, hardened git + config audit, Windows path/exe hardening, FIDES-lite taint, LiteLLM-style reserve-max, Bifrost facts verified in source, red-team RT/PX plan.

## v1–v2 (10 Nov): first research round
Architecture sketch: Python CLI → policy layer → context engine → Bifrost → Anthropic/OpenAI/Ollama; Tavily as a gated tool (now `research/00-round1.md`).
