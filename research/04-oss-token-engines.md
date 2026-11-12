# 04 · Token engines in open-source coding agents: source code, loopholes, fixes

Researched 2026-11-10 from source on `main`/`dev` (raw.githubusercontent.com), GitHub issues and papers. It feeds RESEARCH.md §3 (techniques #1–#6) and §8b.
Licences were checked through the GitHub licence API on 2026-11-10.

**Confidence tags:**
- **[src]** read in source today.
- **[issue]** from a GitHub issue or PR.
- **[2nd]** from a secondary blog or doc. Verify it before you quote it to judges.

**Hackathon rule reminder:** MIT, Apache-2.0 and BSD code may be copied with attribution. Apache-2.0 also needs a NOTICE line and a note that you changed it. No project below is GPL or AGPL. Even so, the plan is to **re-implement** the core during the hackathon and copy only small utilities or data such as tree-sitter `.scm` queries.

---

## 1. Aider (Apache-2.0)

### 1a. Repo map: [`aider/repomap.py`](https://github.com/Aider-AI/aider/blob/main/aider/repomap.py) [src]

**Tags.** Tree-sitter extracts definitions and references from `queries/*-tags.scm` (capture names `name.definition.*` and `name.reference.*`). When a language's query yields definitions only (C++, for example), Pygments tokens are back-filled as references.

**Cache.** Tags are stored in `diskcache` at `.aider.tags.cache.v{3|4}`. The key is the path and the cache is valid while the mtime matches. If SQLite fails, it falls back to a dict.

**Ranking.** It builds an `nx.MultiDiGraph` with an edge from each referencing file to the defining file, then runs `nx.pagerank` with personalization.
- **Personalization.** Each file in the chat, each mentioned file, and each file whose path matches a mentioned identifier gets `100/len(fnames)`.
- **Edge weight.** `mul × sqrt(num_refs)`.
- **`mul` multipliers:**

| Condition | Multiplier |
|---|---|
| Identifier is mentioned | ×10 |
| Identifier is long snake/camel case (≥8 chars) | ×10 |
| Identifier starts with `_` | ×0.1 |
| Identifier is defined in more than 5 files | ×0.1 |
| The referencing file is in the chat | ×50 |

- Rank flows over the out-edges to give a per-(file, identifier) rank.

**Budget fit.**
- `map_tokens` defaults to 1024.
- With no files in the chat, the budget becomes `min(map_tokens × map_mul_no_files (8), ctx − 4096)`.
- A binary search over how many ranked tags to include starts at `budget/25`. It accepts a result within 15% of the target (`ok_err=0.15`).
- Rendering uses `grep_ast.TreeContext`, which shows signatures plus their parents. Lines are cut at 100 chars.
- **Token counting** is sampled for long text: every (n/100)-th line, then extrapolated.
- **Refresh modes** are `auto | always | files | manual`. In `auto`, the cached map is used only if the last build took more than 1 s.

**Edge cases.**
- A `RecursionError` turns the map off ("git repo too large?").
- A `ZeroDivisionError` in PageRank triggers a retry without personalization (#1536).
- **Possible bug:** in `get_tags_raw`, the `captures_by_tag[...].append` sits outside the inner loop, so only the last node per capture name may be kept. Verify this before reusing the code.

### 1b. Prompt layout and caching: [`aider/coders/chat_chunks.py`](https://github.com/Aider-AI/aider/blob/main/aider/coders/chat_chunks.py) and [`base_coder.py`](https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py) [src]

**Order.** `system → examples → readonly_files → repo map → done (history) → chat_files → cur → reminder`.

**Breakpoints.** There are 3 `cache_control: ephemeral` breakpoints: on examples (or system), on the repo map (or read-only files), and on chat_files.

**Keepalive.**
- `warm_cache()` sends a ping with `max_tokens=1` every `5*60-5 = 295 s`. The interval can be overridden with `AIDER_CACHE_KEEPALIVE_DELAY`.
- It sends `--cache-keepalive-pings N` pings (default 0).

**History summarisation** ([`aider/history.py`](https://github.com/Aider-AI/aider/blob/main/aider/history.py)) runs in a background thread when `done_messages` grows past `max_chat_history_tokens`.
- The newest ½ of the budget is kept verbatim. The split is moved so the head ends on an assistant turn.
- The head is summarised by a weak model (the code tries the models in order). It recurses up to depth 3.

**Reflection.** Up to `max_reflections = 3` automatic retries on edit, lint or test errors.

### 1c. Edit formats: [`editblock_coder.py`](https://github.com/Aider-AI/aider/blob/main/aider/coders/editblock_coder.py) and udiff [src]

**SEARCH/REPLACE application tries, in order:**
1. An exact match.
2. A match that ignores leading whitespace (the indentation offset must be the same on every line).
3. Dropping a leading blank line from SEARCH.
4. `...` elision, where each piece must be unique in the file.
5. Every other file in the chat.

**Fuzzy matching is dead code.** `replace_closest_edit_distance` at threshold 0.8 is unreachable because of an early `return`.

**On failure**, the model gets `SearchReplaceNoExactMatch`.
- It includes a "Did you mean…" hint: the `SequenceMatcher` best chunk at ≥0.6 similarity, with ±5 lines of context.
- It adds "Are you sure you need this block?" when REPLACE text is already in the file.
- It asks the model to resend only the blocks that failed.

**Udiff claim.** On GPT-4 Turbo, "laziness" fell from 20% to 61% pass (3× fewer lazy comments) ([blog](https://aider.chat/2023/12/21/unified-diffs.html)).
- Hunks are applied as search/replace, with no line numbers.
- Turning off the flexible patching fallbacks caused **9× more edit errors**.

### Aider loopholes

| # | Loophole | Evidence |
|---|---|---|
| A1 | **Every chat file is re-sent in full on every turn.** `get_files_content()` re-reads them from disk, so token cost grows as files × turns. | [src] base_coder |
| A2 | **The map overshoots its budget.** With no chat files the multiplier is ×8, so a "1k" map becomes about 8k tokens. One user saw `--map-tokens 1024` produce a 16k map. | [src]; [issue #752](https://github.com/Aider-AI/aider/issues/752) |
| A3 | **The map changes and invalidates the cache.** In `auto` mode the map is rebuilt when mentions change. It sits *before* history, so each rebuild invalidates the history cache. v0.51 added `--map-refresh` as a workaround. | [src]; [v0.51 notes](https://newreleases.io/project/github/Aider-AI/aider/release/v0.51.0) [2nd] |
| A4 | **Cost and failure on big repos.** The first scan parses every file. PageRank over a monorepo can hit `RecursionError`, which silently turns the map off. The FAQ says Aider is "not optimized for very large repos". | [src]; [Meetsmore post](https://engineering.meetsmore.com/entry/2024/12/24/042333) [2nd] |
| A5 | **Summarisation loses data silently.** The head beyond about 3.5k tokens (`max_input − 512`) is *dropped*, not summarised. Tool output, file state and failed attempts are not modelled. | [src] history.py |
| A6 | **Edits fail with no fuzzy fallback.** That costs a full reflection round trip, up to 3 per message. | [src] |
| A7 | **Keepalive is opt-in, blind and capped.** It is off by default. When on, it pings even when the user has left, and it has no cost guard. | [src] |

---

## 2. mini-swe-agent (MIT) and SWE-agent (MIT)

### mini-swe-agent: [`agents/default.py`](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) and [`config/default.yaml`](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/config/default.yaml) [src]

- It has bash only and keeps the **full history**: no masking, summarising or windowing.
- **Observation template.** If the output is 10,000 chars or longer, the model sees the first 5,000 + a "{elided} characters elided" marker + the last 5,000, plus "try a different command".
- **Limits.** `cost_limit = 3.0` (yaml default 0), `step_limit = 0`, and it exits after 3 format errors in a row.

This is our **baseline**. History grows linearly, so total input grows about quadratically with the number of steps. The only thing that saves it is provider prefix caching, which helps because the history is append-only.

### SWE-agent: [`sweagent/agent/history_processors.py`](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/history_processors.py) and [`agents.py`](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py) [src]

**`LastNObservations(n, polling=1)`.**
- Observations older than the last n become `Old environment output: (N lines omitted)`.
- The first instance message is never removed.
- Tags `keep_output` and `remove_output` override this.
- The docstring says it **"will break prompt caching"**. The `polling` setting moves the window forward only every `polling` steps so that the cache survives between moves.

**`ClosedWindowHistoryProcessor`.** Older views of the same file (`[File: … (N lines total)]`) become `Outdated window with N lines omitted…`. This is SWE-agent's form of file-read dedup.

**`CacheControlHistoryProcessor(last_n_messages=2)`.** Places rolling Anthropic breakpoints on the last 2 user or tool messages. This is the default config.

**`max_observation_length = 100_000` chars.** Output is cut as `observation[:max]` + `<response clipped>` + a NOTE telling the model to use head, tail or grep.

**Windowed viewer.** `tools/windowed` provides `open`, `goto`, `scroll_up`, `scroll_down` and `create`, with a window of about 100 lines (the value is set in the tool, not the yaml).

**Context overflow** auto-submits the current patch (`exit_context`) instead of compacting.

### Loopholes

| # | Loophole | Evidence |
|---|---|---|
| S1 | **Truncation keeps only the head** (`[:max]`). The *tail*, where pytest summaries and tracebacks end up, is dropped. | [src] agents.py |
| S2 | **100k chars ≈ 25k tokens per observation** is far too generous as a token cap. | [src] |
| S3 | **LastN masking breaks the cache every step** unless `polling` > 1. The authors document this themselves. | [src] docstring |
| S4 | **mini-swe-agent has no history control**, so long tasks blow up linearly. | [src] |
| S5 | **Masking is blind.** A masked observation cannot be retrieved again; the agent must re-run the command, which costs more tokens and has side effects. | [src] |

---

## 3. OpenHands (MIT): condensers in [`software-agent-sdk/openhands-sdk/openhands/sdk/context/condenser/`](https://github.com/OpenHands/software-agent-sdk/tree/main/openhands-sdk/openhands/sdk/context/condenser)

**`LLMSummarizingCondenser`** [src].

| Parameter | Value |
|---|---|
| `max_size` (events) | 240 class default; `default_condenser()` uses `_DEFAULT_MAX_SIZE = 80` (docs say 120) [2nd] |
| `keep_first` | 2 class default; `default_condenser()` uses `_DEFAULT_KEEP_FIRST = 4` |
| `minimum_progress` | 0.1 |
| Optional `max_tokens` | Capped at the model's effective input limit |

- **Three triggers:**
  - EVENTS (soft) keeps `max_size//2` events.
  - TOKENS (hard) keeps a tail under `max_tokens//2`.
  - REQUEST (hard) keeps `len//2`.
- The forgotten range snaps to "manipulation indices", so tool call/result pairs are never split.
- The summary is inserted at `summary_offset`.
- On a hard reset that fails, it retries 5 times, scaling the maximum event string length by 0.8 each time.

**Other condensers in the folder** (from the docs; the folder holds more than this): observation masking, recent-events, amortized forgetting, LLM attention, and a pipeline. OpenHands' own benchmarks drove the move to a summarising default. JetBrains' *Complexity Trap* ([arXiv 2508.21433](https://arxiv.org/abs/2508.21433), NeurIPS'25) tested this on SWE-agent and saw early signs it carries over to OpenHands:
- **Masking with M=10 turns halves cost** compared with the raw agent and matches or beats summarisation. With Qwen3-Coder-480B, the solve rate went from 53.8% to 54.8%.
- **Summaries make trajectories 13–15% longer.** The agent "keeps going" because the summary hides the signal that it should stop.
- A **hybrid** (mask first, summarise rarely) costs **7% less than masking** and **11% less than summarisation**.

### Loopholes

| # | Loophole | Evidence |
|---|---|---|
| O1 | **Event-count trigger.** 80–240 events says nothing about tokens: one 50k-token observation counts as 1 event. | [src] |
| O2 | **Every condensation is a full cache miss**, plus an extra LLM call. The forget-half strategy means the prefix is rewritten from `keep_first` onward. | [src] design |
| O3 | **Summaries hide failure signals**, which makes trajectories 13–15% longer. | paper |
| O4 | **Summaries are lossy and cannot be recovered.** There is no pointer back to the forgotten events. | [src] |

---

## 4. OpenAI Codex CLI (Apache-2.0, Rust)

**Compaction: [`codex-rs/core/src/compact.rs`](https://github.com/openai/codex/blob/main/codex-rs/core/src/compact.rs)** [src].
- It runs `SUMMARIZATION_PROMPT`, which `compact_prompt` can override.
- History is rebuilt as **the real user messages only, newest first, up to `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000`**, followed by one `CompactionSummary` item.
- Earlier summaries, tool outputs and assistant turns are dropped. Media is dropped.
- The canonical initial context is re-inserted before the last user message.
- On `ContextWindowExceeded` during compaction, it drops the oldest item and retries.
- **Triggers.** `model_auto_compact_token_limit`. Reported defaults are about 90% of the window ([#5292](https://github.com/openai/codex/pull/5292)) [2nd]. There are remote and server-side compaction paths (`compact_remote_v2*.rs`). A newer "token-budget compaction" path (`compact_token_budget.rs`) *skips summarisation* and simply starts a fresh context window.

**Tool output truncation** [issue/2nd].
- Originally: `MODEL_FORMAT_MAX_BYTES = 10*1024` and `MAX_LINES = 256`, showing the model the first 128 and last 128 lines.
- Now: a per-model `TruncationPolicy::{Bytes, Tokens}` (exec: `EXEC_FORMAT_MAX_TOKENS = 2_500`). It can be configured with `tool_output_token_limit`, plus a per-tool `output_token_limit` in v0.152.

**Prompt caching** [2nd].
- `prompt_cache_key` is set to the conversation or thread id.
- History is strictly append-only.
- The Responses API is used over a persistent WebSocket. A third-party measurement reports about 97% cache hits with the WebSocket versus 15–45% for another client over stateless HTTP on the same backend.

### Loopholes

| # | Loophole | Evidence |
|---|---|---|
| C1 | **Compaction amnesia.** The model forgets it is mid-task and forgets the files it edited. Only user messages and a summary survive. | [issue #5957](https://github.com/openai/codex/issues/5957); [#29356](https://github.com/openai/codex/issues/29356) asks to keep the last 5 steps verbatim |
| C2 | **Compaction happens without consent** at about 220k tokens. | [#4106](https://github.com/openai/codex/issues/4106) |
| C3 | **The trigger fires too late.** The real usable window (258k) is smaller than the advertised one, and compaction itself can fail. | [#19409](https://github.com/openai/codex/issues/19409), [#21343](https://github.com/openai/codex/issues/21343) [2nd] |
| C4 | **Truncation-unit bug.** Byte and token conversion ×4 kept about 40 KiB instead of 10 KB. | [PR #6746](https://github.com/openai/codex/pull/6746) review |
| C5 | **Fixed 128+128 head/tail lines** hide errors in the middle, such as the first failing test in a long log. | [2nd] |
| C6 | **Session-scoped cache keys** can themselves cause misses on some backends. | [#35300](https://github.com/openai/codex/issues/35300) |

---

## 5. Gemini CLI (Apache-2.0): [`packages/core/src/context/`](https://github.com/google-gemini/gemini-cli/tree/main/packages/core/src/context)

### Compression: [`chatCompressionService.ts`](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/context/chatCompressionService.ts) [src]

- **Trigger:** `DEFAULT_COMPRESSION_TOKEN_THRESHOLD = 0.5` of the model limit.
- **Kept:** `COMPRESSION_PRESERVE_THRESHOLD = 0.3`, the newest 30% of history.
- **Split point:** only at a user turn with no function responses.
- **Before summarising**, function responses beyond a `50_000`-token budget (counted newest first) are **saved to a temp file** and replaced by a truncated stub.
- **Two LLM passes:**
  1. A `<state_snapshot>`.
  2. A "Critically evaluate… omitted technical details" self-verification.
- **Model:** a cheaper utility alias, `chat-compression-*-flash-lite`, for example.
- **Guards.** `COMPRESSION_FAILED_INFLATED_TOKEN_COUNT` discards a result that grew ([PR #7047](https://github.com/google-gemini/gemini-cli/pull/7047)). After an earlier failure, it falls back to truncation only.

### Tool output masking: [`toolOutputMaskingService.ts`](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/context/toolOutputMaskingService.ts) [src]

- The newest **50k** tool-output tokens are protected. Masking runs only if **≥30k** tokens are prunable.
- The latest turn is always protected.
- Full output goes to `tool-outputs/session-<id>/<tool>_<callId>_<rand>.txt`.
- **Placeholder.** A `<tool_output_masked>` block holds a preview plus "Full output available at: <path>".
  - For shell output, the preview is section-aware and **keeps errors and exit codes in full**.
  - Otherwise it keeps the first and last 250 chars, or the first and last 10 lines.
- Skill, ask-user and plan-mode tools are exempt.
- A replacement is kept only if it is actually smaller.

### Truncation: [`truncation.ts`](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/context/truncation.ts) [src]

- It truncates proportionally: `headRatio = 0.2`, so 20% of the kept text comes from the head and 80% from the tail.
- It adds the prefix `[Message Normalized: Tool output exceeded size limit]` and "Full output saved to: …".
- Only string fields are truncated, so the JSON shape is kept.

### Loopholes

| # | Loophole | Evidence |
|---|---|---|
| G1 | **Two summary calls per compression** (snapshot + verify) double the compression cost. | [src] |
| G2 | **A 0.5 threshold compacts early and often.** Each compaction is a full cache miss. | [src] |
| G3 | **Compression can increase tokens.** A guard was only added after the fact. | [#3533 / PR #7047](https://github.com/google-gemini/gemini-cli/pull/7047) |
| G4 | **Users report context loss** and advise starting new chats instead. | [2nd] |
| G5 | **Dead code:** the collapse constants (`RECENT_TURNS_PROTECTED = 3`, 2 KB stubs) are never called. | [src] |

**Best idea to steal:** a **recoverable mask**. Spill the full output to disk, put the path in the stub, and keep the error and exit code verbatim.

---

## 6. OpenCode (MIT): [`packages/core/src/session/compaction.ts`](https://github.com/sst/opencode/blob/dev/packages/core/src/session/compaction.ts) [src]

**Repo note.** The repo was restructured: `packages/opencode/src/session/compaction.ts` now returns 404. The older version pruned tool outputs (`PRUNE_PROTECT` / `PRUNE_MINIMUM`, "[Old tool result content cleared]") [2nd]. That code no longer exists on `dev`.

**Trigger.** It reserves `RESERVE_SHARE = 0.15` of the window for output, with a floor of `RESERVE_MIN = 16k`.

**Background pre-compute.** It starts a summary `PRECOMPUTE_LEAD = 60k` tokens *before* the ceiling, in the background, and gives up after 2 failures. So compaction costs no wall-clock time when it fires.

**Overflow from the provider.** If the provider rejects the context as too long, it retries with shrink steps of 0.85, 0.7, 0.5 and 0.35.

**Structured, anchored summary.** Sections: Objective, Requirements, Decisions, Work State (Completed, Active, Blocked), Next Move, Relevant Files (at most 15) and Important Context.
- It sets "Do not continue the task or call tools".
- Later checkpoints *update* the earlier one instead of re-summarising it.

**What is kept.** The last `keep = 15_000` tokens verbatim. The split happens at a user message, so tool pairs stay intact.

**When the summary input is itself too big**, older exchanges degrade in steps: whole → tool outputs clipped to 2,000 chars → tool outputs removed → user text only → omitted.

**Tool schemas** are small: about 2.5k system tokens versus about 12k for Claude Code [2nd, [edenai](https://www.edenai.co/post/claude-code-vs-opencode-the-33k-token-overhead-gap)]. MCP schemas are still sent on every turn (OpenCode issue #17482, reported [2nd]).

### Loopholes

| # | Loophole |
|---|---|
| OC1 | MCP and skill schemas are re-sent on every call. There is no lazy loading. |
| OC2 | A summary step is still lossy. It makes no pointer back to the raw history. |
| OC3 | The pre-computed summary goes stale if the tail is larger than 40% of the budget, so the work is wasted. |

---

## 7. Goose (Apache-2.0): [`crates/goose/src/context_mgmt/mod.rs`](https://github.com/block/goose/blob/main/crates/goose/src/context_mgmt/mod.rs) [src]

**Auto-compact.** Triggers when usage is above `GOOSE_AUTO_COMPACT_THRESHOLD` (0.8 per the tests). Separately, `DEFAULT_AUTO_COMPACT_TOKEN_LIMIT = 225_000`, chosen to keep the session "below OpenAI's long-context price tier". This **cost-aware ceiling** is a nice touch, but **`check_if_compaction_needed` never calls it**, which is a bug.

**Visibility metadata.** Every message carries agent-visible and user-visible flags.
- Originals become user-only.
- The summary is agent-only.
- The last user message is re-appended.

**Tool-pair summarisation** (`GOOSE_TOOL_PAIR_SUMMARIZATION`) is **off by default**.
- Each old call and result pair is replaced by a one-line summary from an LLM.
- Batches are 10 (`TOOLCALL_SUMMARIZATION_BATCH_SIZE`).
- The cutoff is `3·(ctx·thr)/20k`, clamped to 10–500.

### Loopholes

| # | Loophole |
|---|---|
| GO1 | The 225k price-tier cap is not wired into the trigger. |
| GO2 | Per-pair LLM summarisation adds cost and breaks the cache; it is off by default for that reason. |

---

## 8. Cline (Apache-2.0), Roo Code (Apache-2.0), Kilo Code (MIT)

### Roo: [`src/core/context-management/index.ts`](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/context-management/index.ts) and [`src/core/condense/index.ts`](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/condense/index.ts) [src]

**Thresholds.**
- `TOKEN_BUFFER_PERCENTAGE = 0.1`.
- Allowed tokens = `ctx·0.9 − maxTokens`.
- The condense threshold is a percentage between 5 and 100.

**Fallback.** A sliding window hides 50% of messages (always an even count) and keeps the first message.

**Non-destructive.** Hidden messages get a `condenseParent` or `truncationParent` tag, and a marker is inserted, so a rewind can restore them.

**Folded file context.** At condense time, the files read earlier are re-injected as folded code definitions (signatures), so the agent does not need to re-read them.

### Cline

**File-read dedup.** Older reads of the same file are replaced so that only the latest version stays ([Cline blog](https://cline.bot/blog/inside-clines-framework-for-optimizing-context-maintaining-narrative-integrity-and-enabling-smarter-ai)) [2nd]. The repo has since moved to `sdk/packages/core/src/extensions/context/{basic,agentic}-compaction.ts` [src]:
- **basic.** Typed user prompts are kept. Only each older turn's final assistant answer is kept, and the last 3 assistant texts are kept verbatim. Everything else becomes a `<SYSTEM_NOTICE>` tool-activity summary. This is deterministic and needs no LLM.
- **agentic.** An LLM continuation note with an enforced "files" section, folded in iteratively.

### Loopholes

| # | Loophole | Evidence |
|---|---|---|
| R1 | **Roo does not check whether the condensed context is smaller.** It computes `newContextTokens` but never compares it. | [src] |
| R2 | **Condensing uses the active, expensive model**; there is no separate cheap-model selector. | [v3.43 notes](https://docs.roocode.com/update-notes/v3.43.0) |
| R3 | **The original task was lost during condense.** | Fixed [#8298](https://docs.roocode.com/update-notes/v3.28.8) |
| R4 | **Read dedup rewrites old messages**, which is a cache miss at that point. | Reasoning |
| R5 | **`ReadFileTool` has no "unchanged since last read" check.** Each re-read costs the full file. | [src] |

---

## 9. Localisation pipelines: Agentless (MIT) and Moatless (MIT)

**Agentless: [`agentless/fl/FL.py`](https://github.com/OpenAutoCoder/Agentless/blob/main/agentless/fl/FL.py)** [src]. A three-stage funnel with **no agent loop**:
1. Repo tree → at most 5 files. An optional "irrelevant folders" prompt and embedding retrieval narrow it further.
2. **Compressed skeletons** (`get_skeleton`: class and function signatures, `compress_assign`) → relevant classes and functions.
3. Top-N context around those → edit lines.

Each call uses `max_tokens=300` and `temperature 0`. If the prompt is over 128k, files are dropped from the end.

**Reported results:** $0.34 per issue and 27.3% on SWE-bench Lite (GPT-4o). File-level localisation accuracy is 77.7% and line-level is 50.8% [paper].

**Moatless Tools:** semantic code index plus span-based `FileContext`. Reported as 39% on SWE-bench Lite with Claude 3.5 Sonnet, at 2.7 resolved per $ (about $0.37 per resolved task) [2nd].

### Loopholes

| # | Loophole |
|---|---|
| L1 | Stage 1 sees only file *names*. A badly named file is missed and cannot be recovered. |
| L2 | It drops files from the *end* of the list to fit, rather than by rank × size. |
| L3 | It has no feedback from test runs. |

---

## Best parts to adopt

| Component | Source file | Licence | Copy vs re-implement | Effort |
|---|---|---|---|---|
| Tree-sitter tag queries (`*-tags.scm`) | aider `aider/queries/` (from tree-sitter grammars) | Apache-2.0 / MIT | **Copy** the `.scm` data with attribution | 0.5h |
| Def/ref graph + personalised PageRank + binary-search budget fit | aider `repomap.py` | Apache-2.0 | **Re-implement** (about 150 LOC with `networkx`), using Aider's multipliers (×10 mentioned, ×50 chat file, ×0.1 private, `sqrt(refs)`) | 3h |
| Signature skeleton renderer | `grep_ast.TreeContext` (Apache-2.0) or Agentless `get_skeleton` (MIT) | Apache / MIT | **Use `grep-ast` as a pip dependency** (attributed) | 0.5h |
| SEARCH/REPLACE parser + staged matcher + "did you mean" error | aider `editblock_coder.py` | Apache-2.0 | **Re-implement**; turn fuzzy matching *on* behind a uniqueness check | 2h |
| Prefix order + ≤4 cache breakpoints | aider `chat_chunks.py`, SWE-agent `CacheControlHistoryProcessor` | Apache / MIT | Re-implement | 1h |
| Keepalive ping (295 s, `max_tokens=1`) | aider `base_coder.warm_cache` | Apache-2.0 | Re-implement, gated by the budget and an idle timeout | 0.5h |
| LastN masking with `polling` (batched for the cache) | SWE-agent `history_processors.py` | MIT | Re-implement | 1h |
| Closed-window and stale-read dedup | SWE-agent `ClosedWindowHistoryProcessor`, Cline | MIT / Apache | Re-implement as a hash-based read cache | 1h |
| Recoverable masking (spill to disk + path in the stub; keep errors and exit codes verbatim) | gemini-cli `toolOutputMaskingService.ts` | Apache-2.0 | Re-implement | 1h |
| Head/tail truncation (20/80, tail-biased) | gemini-cli `truncation.ts`, mini-swe-agent template | Apache / MIT | Re-implement | 0.5h |
| Structured anchored summary template + incremental update | opencode `session/compaction.ts` | MIT | **Copy** the section list (prompt text) with attribution | 0.5h |
| Background pre-compute of the summary (lead before the ceiling) | opencode `PRECOMPUTE_LEAD` | MIT | Re-implement (thread) | 1h |
| Inflated-token guard + cheap utility model for summaries | gemini-cli `chatCompressionService.ts` | Apache-2.0 | Re-implement | 0.3h |
| Price-tier compaction ceiling | goose `DEFAULT_AUTO_COMPACT_TOKEN_LIMIT` | Apache-2.0 | Re-implement (and actually wire it up) | 0.3h |
| 3-stage localisation (tree → skeleton → lines), `max_tokens=300` | Agentless `fl/FL.py` | MIT | Re-implement as the *first step* of code-mode | 2h |
| Folded file context at compaction | Roo `condense/foldedFileContext.ts` | Apache-2.0 | Re-implement with our skeleton renderer | 0.5h |

## Loopholes → our fix

| Loophole (source) | Best fix (why) | Adopt? |
|---|---|---|
| A1: whole files re-sent every turn (Aider) | Never keep whole files in the prefix. Expose `read(path, range)` and `read_symbol`. The read cache answers "unchanged since turn N (hash)" or returns a **diff** from the last version seen. | **Yes**: §3 #5 |
| A2/A4: map overshoots and costs too much on big repos | Make the budget a **hard cap**: binary search with *no* overshoot, and no ×8 multiplier. Cap the graph at the top-K files by `git ls-files` + recency. Run the parse in a background thread and use `rg`-only mode when there are more than 5k files. | Yes |
| A3: map rebuild breaks the cache (Aider) | **Freeze the map once per session** inside the cached prefix. Send query-specific ranking as a *tail* message (a "focus list" of about 200 tokens), never in the prefix. | **Yes**: key insight |
| A5/C1/O4: lossy, unrecoverable summaries; amnesia | Make compaction **rare and structured**. Use the OpenCode sections plus a **deterministic "Work State" built from our event journal**: files edited (with hashes), tests run and their status, commands that failed. Keep the last 5 steps verbatim (Codex #29356). Store raw history on disk and give the model a `recall(turn)` tool. | **Yes** |
| O3: summaries lengthen trajectories by 13–15% | Mask first and summarise only at the hard ceiling (the *Complexity Trap* hybrid: −7% vs masking). Always keep the latest test failure verbatim. | Yes |
| S3/O2/G2: masking or condensing busts the cache | **Batch masking.** Mask only when the *uncached* tail exceeds X tokens or every `polling = 5–10` turns, so the prefix moves in jumps and stays cached between them. The cost model: mask only if `saved_tokens × remaining_turns × price_in > rewritten_tokens × cache_write_price`. | **Yes**: demoable |
| S1/C5: head-only or fixed truncation hides errors | **Semantic truncation.** Strip ANSI. For known tools (pytest, tsc, ruff, cargo), parse and return *only failures + a summary line*. Otherwise use a 20/80 head/tail split and **always keep lines matching `error\|Traceback\|FAIL\|exit code`**. Spill the full output to `.agent/out/<id>.txt`. | **Yes** |
| S5: masked output cannot be retrieved | The stub carries `(full: .agent/out/42.txt, 3,120 lines)`, and `read` can page through it. | Yes |
| C4: unit bugs in truncation | Count with one tokenizer function (tiktoken or `len/4` as the fallback) and unit-test the boundaries. | Yes |
| C2/C3: surprise or late compaction | Trigger on **real usage** (the usage field returned by the API through Bifrost), at `min(0.8·window, price-tier cap)`. Warn at 70%. Our budget ledger already pre-reserves spend. | Yes |
| G1/R2: expensive summaries | Summarise with the **cheap or local model** (our ladder). One pass only, plus the inflated-token guard. | Yes |
| G3/R1: compression that grows the context | Reject any compaction where `new ≥ 0.9·old`, and fall back to masking. | Yes (one line) |
| OC1: tool and MCP schemas on every call | Use **at most 6 terse tools**, sorted and frozen in the prefix, with no MCP by default. Code-mode (§8b pillar 2) folds exploration into one tool. Report the schema size in the meter. | Yes |
| A6: edit failures cost round trips | Staged matcher: exact → whitespace → `...` → **unique fuzzy ≥0.9** (apply only if exactly one candidate) → a "did you mean" error that asks for the failed blocks only. | Yes |
| A7: keepalive cost and staleness | Ping only while a turn is pending (for example, while tests run for more than 4.5 min). Stop after N pings and charge them to the ledger. Prefer Anthropic's 1h TTL cache when the session will clearly be long. | Optional |
| C6: cache key or affinity misses | Send one `x-bf-session-id` and `prompt_cache_key` per session, give the gateway sticky routing, and log the cache-read share per turn. | Yes |
| R4: dedup that rewrites history busts the cache | Dedup **at read time** (return "unchanged" or a diff) instead of rewriting old messages. Rewrite old reads only during a batched mask event. | **Yes** |
| L1/L2: localisation misses | Run `rg` on issue keywords together with the repo map to choose stage-1 candidates. Drop files by rank ÷ size. Feed failing-test stack frames into stage 1. | Yes (code-mode) |

---

## Recommended token-engine composition for our agent

Each layer sits behind a flag so the §4 ablation table can switch it on or off. Layers are ordered by payoff per hour.

1. **Frozen, cache-first prompt** (Aider order, minus whole files).
   - Order: `tools (≤6, sorted) → system → repo map (frozen per session, ≤1.5k tok, hard cap) → [BP1]`, then `append-only history [rolling BP2/BP3 on the last 2 user/tool msgs] → focus-list tail`.
   - No timestamps in the prefix. One session key. Keepalive only while a long tool is running.
2. **Tool-output gate** (runs before anything enters history).
   - Strip ANSI and apply parsers for test and lint tools so that only failures are returned.
   - Otherwise cap at 256 lines / 10KB with a 20/80 head/tail split, error lines always kept, and the full output spilled to disk with its path in the stub.
3. **Read cache.** Files are hashed on read.
   - A re-read of an unchanged file returns "unchanged since turn N".
   - A re-read of a changed file returns a unified diff.
   - Reads default to a symbol or a 100-line window, not the whole file.
4. **SEARCH/REPLACE edits** with the staged matcher (unique-fuzzy ≥0.9) and errors that ask only for the failed blocks.
5. **Batched observation masking.** Window M=10 turns, moved in batches (polling 5–10 or an uncached-tail threshold), so cache hits stay high. Stubs are recoverable.
6. **Rare structured compaction** at `min(0.8·ctx, price-tier cap)`:
   - It uses the cheap model and the OpenCode section template.
   - A **deterministic Work State from the event journal** is merged in.
   - The last 5 steps are kept verbatim, plus folded skeletons of edited files.
   - The inflated-token guard applies.
   - The summary is pre-computed in the background about 30k tokens before the ceiling.
7. **Localisation-first code-mode** (Agentless funnel). Tree + `rg` → skeletons → lines, with `max_tokens=300` and on the cheap model. Only the result enters the main context. Count "tokens avoided".
8. **Metering.** Every layer logs the tokens it saved: uncached, cache-write, cache-read and output. That turns "proves its savings" (§8b) into a per-layer table.

**Expected effect** (literature, not yet measured by us): caching −41–80% of cost ([2601.06007](https://arxiv.org/abs/2601.06007)); masking about −50% vs raw ([2508.21433](https://arxiv.org/abs/2508.21433)); hybrid a further −7%; truncation and read cache cut the largest share of per-turn tokens. **Measure every one against mini-swe-agent before claiming it.**

### Attribution block for our README
> Repo-map ranking approach and tree-sitter tag queries adapted from Aider (Apache-2.0, © Paul Gauthier); `grep-ast` used as a dependency (Apache-2.0). Masking design informed by SWE-agent (MIT) and gemini-cli (Apache-2.0). Compaction template adapted from OpenCode (MIT). Localisation funnel after Agentless (MIT). Modified files carry a "modified from" header per Apache-2.0 §4.
