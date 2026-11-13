# GaH: Crocodile (internal)

Private working repo for our Global AI Hackathon PS-01 entry (sponsors: Bifrost, Tavily).

**Crocodile** (`crocodile`, alias `crock`) is a Python terminal coding agent that does more correct work per token.
We measure it as **cost per solved task**, paired against mini-swe-agent on the same model and gateway.
Its budget, privacy and approval rules are enforced by deterministic code outside the model.

**Status (12 Nov 2026):** design complete (v5), build starts 12 Nov. Build closes 15 Nov 12:00 (we submit by 11:00); judging 29 Nov.

## Doc map (reading order)

| # | Doc | What it is |
|---|---|---|
| 1 | [docs/00-team-brief.md](docs/00-team-brief.md) | 5-minute brief: problem, pitch, P0 slice, timeline, rules, risks |
| 2 | [docs/02-build-plan.md](docs/02-build-plan.md) | 12–15 Nov plan, P0/P1/P2, cut list, go/no-go, day-0 checklist |
| 2b | [docs/04-team-split.md](docs/04-team-split.md) | **4-part team split**: ownership, interfaces, milestones |
| 3 | [docs/architecture/README.md](docs/architecture/README.md) | Architecture index (single source of truth) + system context |
| 4 | [docs/architecture/](docs/architecture/) 01–11 | Overview, components, flows, data model, security, budget, confidential, token/accuracy engine, Bifrost/Tavily, evaluation, CLI |
| 5 | [docs/architecture/adr/](docs/architecture/adr/) | ADR-001 … ADR-010 |
| 6 | [docs/01-playbook.md](docs/01-playbook.md) | How we win: criteria map, video script, README outline, submission, Q&A |
| 7 | [docs/03-claims.md](docs/03-claims.md) | The only wording allowed in public material |
| 8 | [docs/architecture/CHANGELOG.md](docs/architecture/CHANGELOG.md) | v1 → v5 |
| — | [docs/internal/peer-notes.md](docs/internal/peer-notes.md) | Peer mapping. **Internal only** |
| — | [research/](research/) 00–09 | Point-in-time research and reviews (background; superseded where the architecture differs) |

## Who reads what

| Reader | Read |
|---|---|
| Builder (any task) | 02-build-plan + only the architecture section for that task (saves tokens) |
| New teammate | 00-team-brief → 02-build-plan → architecture/01 |
| Bench owner | architecture/10, 09 §6, 04 §6 |
| Security / confidential owner | architecture/05, 07, 10 §3 |
| README / video / submission | 01-playbook, 03-claims |

Rules: no secrets in the repo (`.env` is git-ignored; keys live in Windows Credential Manager); public material never names peer teams.
