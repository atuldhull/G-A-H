# Internal: peer mapping (NOT for README, pitch, slides or video)

Sources: research/06 §1 (cloned 10 Nov), research/08 §1.J and research/09 §2 (checked 12 Nov). Public material refers only to attack classes (PX-n). Re-check on 14 Nov.

## 1. Attack classes and peer evidence

| PX | Attack class | Peer evidence | Our control |
|---|---|---|---|
| PX-1 | Confidential repo, but the process holds/uses the cloud key | Gidorah: client always built with `vkCloud` (`apps/cli/src/main.ts:613`); TUI alias overrides the confidential alias (`runtime.ts:197`); DLP plugin not loaded, and Go plugins don't load on Windows; DLP checks only `body.model`, not `fallbacks` | Only `vk_local` loaded; egress asserts ([07](../architecture/07-confidential-mode.md)) |
| PX-2 | Lone `&` / newline treated as ordinary → "read-only" auto-approve | Gidorah: tokenizer keeps `&` (`packages/policy/src/shell.ts:145-165`), `shell:true` (`core/src/tools.ts:387`); `git diff --output` auto-allowed. slendertoken: "read-only shell" allowlist | Argv-only, no classification (ADR-003) |
| PX-3 | Missing marker/policy defaults to cloud; per-run flag | StaleGuard: `if not path.exists(): return RepoPolicy()` (`policy.py:68`), no parent walk. thrift-agent and slendertoken: `--private` per-run flag | Realpath walk up + scan down, sticky registry |
| PX-4 | Tavily on in confidential mode | StaleGuard: Tavily built regardless of `local_only` (`cli.py:370-374`) | Key not loaded, tool unregistered, socket guard |
| PX-5 | Child inherits gateway admin creds / VKs / API keys | Pinch: `.env` loaded into `os.environ` incl. Bifrost admin auth, both VKs, Tavily key (`config.py:104`); subprocess without `env=` (`vendor/coding_mcp_server.py:171`). StaleGuard: `shell=True` + full env | Env allowlist, secrets in Credential Manager |
| PX-6 | Budget race: check-then-record | StaleGuard: check (`policy.py:231`) then record (`:253`), no `max_tokens` (`loop.py:196-199`). Gidorah: in-memory precheck, restart resets. Pinch, LeanCoder post-hoc. thrift-agent, slendertoken: gateway VK budget only | Reservation (ADR-005) |
| PX-7 | Per-user identity from an env var | StaleGuard: `STALEGUARD_USER` / OS login (`config.py:55, 79`); one shared VK | Principal = VK hash |
| PX-8 | Unprefixed model → gateway-inferred cloud fallbacks | Bifrost behaviour; affects every peer sending unprefixed aliases | Egress refuses unprefixed ids |
| PX-9 | Approval via piped stdin | LeanCoder: `input()` on stdin | CONIN$ only |
| PX-10 | Ollama cloud tag passes "local only" (new, review 07 C3) | Not yet seen in a peer; any Ollama-only mode is exposed | Local model allowlist |

## 2. Peer table (12 Nov)

| Repo | Licence | Budget | Confidential | Bench | Notes |
|---|---|---|---|---|---|
| Gidorah (`piyushdotcomm/gidorah`) | Apache-2.0 | in-memory precheck | vkCloud always built | — | No commits after 4 Nov; Bifrost on `0.0.0.0`, unpinned. Routing-header idea credited in NOTICE if reused |
| StaleGuard (`Shrinu14/staleguard-agent`) | none (learn only) | check-then-record | no parent walk | — | No commits after 5 Nov |
| Pinch | AGPL-3.0 (ideas only, clean-room) | post-hoc | — | strongest rigour: real OSS bugs, containers, vs mini-swe-agent | Last commit 8 Nov (rate-limit pacing) |
| LeanCoder | none | post-hoc token budget | — | — | stdin approvals |
| thrift-agent (`nemo-MV33/thrift-agent`, TS) | **MIT now** | VK only (402 → stop + `--resume`) | `--private` flag | 17 Node tasks, naive baseline, 3 runs, "71% fewer tokens", $0.00132/task | No reservation, undo, taint or egress log |
| slendertoken (`Ani07-05/slendertoken`, Go) | none | VK daily budget | `--private` per-run; "best effort" network block | "54% fewer tokens than naive, 4/4 pass"; `bench/` without numbers | Best UX: one-line installer, website, TUI with mascots, energy/carbon report. Small-model-first with escalation |
| Privacy-First-Token-Optimized-Coding-Agent (`Dhruv727876`, TS, 11 Nov) | MIT (claimed) | config limits, no reservation | opt-in confidential paths | none | — |
| tokenshield (`Shristi1611`) | none | none | quarantined-LLM "typed facts" (closest to taint) | 10 READMEs, bootstrap CIs | Not a coding agent |
| TokenWise | none | — | — | — | `startswith` workspace check (sibling `workspace2`) |

## 3. Implications

- No peer implements atomic reservation, provenance-named approvals, test-execution consent, a local model allowlist, an egress log with canaries, or a paired CPST bench vs mini-swe-agent. These are our differentiators, but only once built.
- thrift-agent and tokenshield report repeated runs or CIs, so "1 seed" is no longer a fair jab at every peer. Compete on the real baseline and the paired design.
- slendertoken wins on polish. Don't compete on cuteness; compete on trustworthy numbers on screen (quote, live $/budget line, receipt "solved by tests").
- Match Pinch's rigour (real baseline, repeated runs) and lead with the guarantees it lacks.
